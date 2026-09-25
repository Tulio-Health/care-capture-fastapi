"""Per-worker admission, request deadlines and shared model-call budgets."""
import asyncio
import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import wraps
from src.app.services.document_extraction import DocumentProcessingError

logger = logging.getLogger(__name__)


@dataclass
class WorkBudget:
    max_model_calls: int = 64
    # Two counters, one ceiling (max_model_calls). `model_calls` is the authoritative
    # per-call counter, incremented by model_call itself; it is the ONLY enforcement for
    # clients that install no httpx hook (the LangChain paths: the fhir_analysis and
    # transcript_summarization chains). `provider_requests` is owned by the per-HTTP-request
    # hook (reserve_provider_request) and additionally sees SDK-internal retries on hooked
    # clients. Audit R5 originally merged both onto the hook counter; round-2 red-team
    # (MAJOR-1) measured that merge silently uncapping every unhooked call (200 completed
    # where develop refused at #65) -- do not re-merge unless every client is hooked.
    model_calls: int = 0
    provider_requests: int = 0
    # Byte-measured bounds (UTF-8 byte length is a conservative bound for text BPE tokens).
    input_upper_bound_bytes: int = 0
    # Fix 1 (round9-revision.md section 4.6): bytes held by an in-flight synchronous
    # reservation (reserve_input_bytes/release_input_bytes below) -- pre-charged before
    # dispatch, converted to a real input_upper_bound_bytes charge as it is spent, refunded
    # in `finally` for whatever a call never spent. Present but always zero until
    # verify_grounding starts calling reserve_input_bytes (Step 2).
    reserved_input_bytes: int = 0
    max_call_input_bytes: int = 160_000
    max_input_bytes_per_job: int = 4_000_000
    max_output_tokens: int = 4096
    max_images_per_call: int = 1
    clients: list = field(default_factory=list)
    # R11: the one hooked AsyncOpenAI shared by every model constructed under this budget
    # (llm_factory caches it here lazily); closed with the rest of `clients` at job end.
    ai_client: object = None
    deadline: float = 0.0
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


request_started = ContextVar("summary_request_started", default=None)

_current_budget = ContextVar("summary_work_budget", default=None)
# Fix 1 (round9-revision.md section 4.6): the carrier for a synchronous byte reservation.
# `_prepaid`'s payload is a MUTABLE LIST deliberately: contextvars copy the reference (not a
# snapshot) into child tasks, so a request dispatched from a pydantic_ai child task decrements
# the parent's bucket. `_UNBUDGETED` is a distinct sentinel (truthy, not None) so
# `if token is None:` is the caller's only failure test -- `token is _UNBUDGETED` means
# "budget is None: no hook, no wall, nothing reserved" (round-4 MAJOR-4).
_prepaid = ContextVar("summary_prepaid_request_bytes", default=None)
_UNBUDGETED = object()
_active_summary_tasks = set()
SUMMARY_CAPACITY_PER_WORKER = 4
MODEL_CAPACITY_PER_WORKER = 8
_slots = asyncio.Semaphore(SUMMARY_CAPACITY_PER_WORKER)
_model_slots = asyncio.Semaphore(MODEL_CAPACITY_PER_WORKER)
MAX_TRANSIENT_RETRIES = 1
# The one authoritative per-call ceiling: every LLM/provider call is bounded by this timer in
# model_call below, and the hooked AsyncOpenAI/httpx clients (llm_factory.py) use the same
# number so the transport can never outlive the wrapper. The judge (clinical_grounding.py,
# timeout=30) and consolidation (consolidation.py, timeout=15.0) keep deliberately TIGHTER
# sub-ceilings below this value. Queue wait for _model_slots is deliberately NOT under this
# timer: it is owned by the per-job deadline in bounded_summary (SUMMARY_DEADLINE_EXCEEDED),
# so saturation surfaces as the per-job contract, not a spurious per-call MODEL_TIMEOUT.
MODEL_CALL_TIMEOUT_S = 45


async def model_call(operation, *args, **kwargs):
    budget = _current_budget.get()
    for attempt in range(MAX_TRANSIENT_RETRIES + 1):
        if budget is not None:
            # Authoritative per-call check-then-increment (restored, round-2 MAJOR-1): the
            # only ceiling on unhooked clients. The provider_requests read is a cheap
            # fast-fail for hooked clients whose transport counter is already exhausted.
            if (budget.model_calls >= budget.max_model_calls
                    or budget.provider_requests >= budget.max_model_calls):
                raise DocumentProcessingError("MODEL_CALL_BUDGET_EXCEEDED")
            budget.model_calls += 1
        try:
            # Acquire the shared concurrency gate FIRST; the timer bounds only the call itself.
            async with _model_slots:
                async with asyncio.timeout(MODEL_CALL_TIMEOUT_S):
                    return await operation(*args, **kwargs)
        except DocumentProcessingError:
            raise
        except Exception as exc:
            code = model_error_code(exc)
            if code not in {"MODEL_TIMEOUT", "MODEL_RATE_LIMITED"} or attempt >= MAX_TRANSIENT_RETRIES:
                raise DocumentProcessingError(code) from exc
            delay = retry_delay(exc, attempt)
            if delay > MODEL_CALL_TIMEOUT_S:
                raise DocumentProcessingError(code) from exc
            if budget and budget.deadline and time.monotonic() + delay >= budget.deadline:
                raise DocumentProcessingError(code) from exc
            await asyncio.sleep(delay)


def retry_delay(exc, attempt):
    delay = min(2 ** attempt * 0.25, 5)
    current, seen = exc, set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        response = getattr(current, "response", None)
        headers = getattr(response, "headers", {})
        value = headers.get("retry-after")
        if value:
            try:
                requested = float(value)
                if requested >= 0:
                    return max(delay, requested)
            except (TypeError, ValueError):
                pass
        current = current.__cause__ or current.__context__
    return delay


def model_error_code(exc):
    """Classify SDK/wrapper failures without exposing prompts or provider bodies."""
    seen = set()
    current = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, DocumentProcessingError):
            return current.code
        name = type(current).__name__
        status = getattr(current, "status_code", None)
        if isinstance(current, TimeoutError) or name in {"APITimeoutError", "ReadTimeout", "ConnectTimeout", "PoolTimeout"}:
            return "MODEL_TIMEOUT"
        if status == 429 or name == "RateLimitError":
            return "MODEL_RATE_LIMITED"
        if status in {401, 403} or name in {"AuthenticationError", "PermissionDeniedError"}:
            return "MODEL_AUTH_FAILED"
        if isinstance(status, int) and status >= 400:
            return "MODEL_UNAVAILABLE"
        if name in {"UnexpectedModelBehavior", "ValidationError", "ModelRetry", "ToolRetryError"}:
            return "MODEL_OUTPUT_INVALID"
        if name == "BudgetExceeded":
            return "RESOURCE_LIMIT_EXCEEDED"
        current = current.__cause__ or current.__context__
    return "MODEL_UNAVAILABLE"


def bounded_summary(operation):
    @wraps(operation)
    async def wrapped(self, request, *args, **kwargs):
        if _current_budget.get() is not None:
            return await operation(self, request, *args, **kwargs)
        if _slots.locked():
            raise DocumentProcessingError("SUMMARY_BUSY")
        async with _slots:
            duration = min(getattr(request, "timeout_seconds", 120), 300)
            job_started = request_started.get() or time.monotonic()
            deadline = job_started + duration
            token = _current_budget.set(WorkBudget(deadline=deadline))
            task = asyncio.current_task()
            _active_summary_tasks.add(task)
            try:
                async with asyncio.timeout(max(0, deadline - time.monotonic())):
                    return await operation(self, request, *args, **kwargs)
            except TimeoutError as exc:
                raise DocumentProcessingError("SUMMARY_DEADLINE_EXCEEDED") from exc
            finally:
                budget = _current_budget.get()
                try:
                    async with asyncio.timeout(5):
                        await asyncio.gather(*(client.close() for client in budget.clients), return_exceptions=True)
                except TimeoutError:
                    pass
                finally:
                    # Step 0 (grounding-check size-gate design, round9-revision.md section 10):
                    # job-end observability only -- read before reset, since
                    # model_call_headroom() and the fields below depend on _current_budget
                    # still pointing at this job's WorkBudget. Never gates, never raises.
                    logger.info(
                        "budget.job_end input_upper_bound_bytes=%d provider_requests=%d "
                        "model_calls=%d model_call_headroom=%s wall_seconds=%.3f",
                        budget.input_upper_bound_bytes, budget.provider_requests,
                        budget.model_calls, model_call_headroom(),
                        time.monotonic() - job_started,
                    )
                    _current_budget.reset(token)
                    _active_summary_tasks.discard(task)
    return wrapped


async def reserve_provider_request(request):
    budget = _current_budget.get()
    if budget is not None:
        if budget.provider_requests >= budget.max_model_calls:
            raise DocumentProcessingError("MODEL_CALL_BUDGET_EXCEEDED")
        import json
        try:
            body = json.loads(request.content)
        except (ValueError, AttributeError) as exc:
            raise DocumentProcessingError("MODEL_OUTPUT_INVALID") from exc
        images = 0
        def text_only(item):
            nonlocal images
            if isinstance(item, dict):
                if item.get("type") == "image_url":
                    images += 1
                    return {"type": "image_url"}
                return {key: text_only(value) for key, value in item.items()}
            if isinstance(item, list):
                return [text_only(value) for value in item]
            return item
        # UTF-8 byte length is a conservative bound for text BPE tokens. Image
        # requests have a separate count/pixel budget; do not count base64 as text.
        text_bound = len(json.dumps(text_only(body), ensure_ascii=False).encode())
        output_limit = body.get("max_completion_tokens", body.get("max_tokens"))
        # Fix 1 (round9-revision.md section 4.6): a judge call pre-reserved its bytes via
        # reserve_input_bytes before dispatch (verify_grounding). Convert that reservation into
        # the real charge instead of double-charging against a second, independent job-wall
        # test. Deferred import: clinical_grounding imports summary_runtime at module scope, so
        # a top-level import here would be a circular import.
        prepaid = _prepaid.get()
        if prepaid is not None:
            from src.app.services.clinical_grounding import _judge_call_limit
            take = min(prepaid[0], text_bound)
            # Check BEFORE mutating, exactly as the non-prepaid leg below does. The job-wall
            # leg is RETAINED (round-6 MINOR-5), not dropped: it can only fire when
            # text_bound > take, i.e. when the real wire body exceeded its prepayment. Judge
            # request_bytes is never optimistic (section 11 test 1) and
            # create_document_ai_client sets max_retries=0 (llm_factory.py) so one dispatch ==
            # one hook invocation today -- but if either invariant ever changes, the job wall
            # must still be enforced rather than silently uncapped for judge calls.
            if (images > budget.max_images_per_call
                    or text_bound > _judge_call_limit(budget)
                    or budget.input_upper_bound_bytes + text_bound + budget.reserved_input_bytes - take
                       > budget.max_input_bytes_per_job
                    or not isinstance(output_limit, int) or output_limit > budget.max_output_tokens):
                raise DocumentProcessingError("MODEL_CALL_BUDGET_EXCEEDED")
            prepaid[0] -= take                       # synchronous; single-threaded
            budget.reserved_input_bytes -= take
            budget.input_upper_bound_bytes += text_bound
            budget.provider_requests += 1
            return
        if (images > budget.max_images_per_call or text_bound > budget.max_call_input_bytes
                or budget.input_upper_bound_bytes + text_bound > budget.max_input_bytes_per_job
                or not isinstance(output_limit, int) or output_limit > budget.max_output_tokens):
            raise DocumentProcessingError("MODEL_CALL_BUDGET_EXCEEDED")
        budget.input_upper_bound_bytes += text_bound
        budget.provider_requests += 1


def reserve_input_bytes(budget, body_bytes, dispatches):
    """Fix 1 (round9-revision.md section 4.6): THE canonical reservation, used by every call
    site. Synchronous take: no `await` between the check and the charge (mirrors
    chain.py's `retry_slots` synchronous take at its own headroom guard).

    Returns:
      _UNBUDGETED -- budget is None: no hook, no wall, nothing reserved (round-4 MAJOR-4).
      a ContextVar token -- reservation held; caller MUST pass it to release_input_bytes.
      None -- the job wall cannot fund this request; caller must raise.

    The three returns are distinguishable: `token is None` is the only failure, and
    `_UNBUDGETED` is truthy, so `if token is None:` is the correct and only caller-side test.

    round-6 MAJOR-2: the `budget is None` guard lives INSIDE this pair, not around each call
    site's own try/finally -- that is what makes it impossible for a future call site to
    reintroduce the crash a prior draft shipped (a bare release on an unguarded reserve raised
    TypeError on every unbudgeted grounding call).
    """
    if budget is None:
        return _UNBUDGETED
    want = body_bytes * dispatches
    if (budget.input_upper_bound_bytes + budget.reserved_input_bytes + want
            > budget.max_input_bytes_per_job):
        return None
    budget.reserved_input_bytes += want
    return _prepaid.set([want])


def release_input_bytes(budget, token):
    """Total and idempotent: safe for _UNBUDGETED, safe for None, safe on any exit path.
    Refunds whatever the dispatch(es) never spent."""
    if token is None or token is _UNBUDGETED:
        return
    remaining = _prepaid.get()
    budget.reserved_input_bytes -= max(0, remaining[0] if remaining else 0)
    _prepaid.reset(token)


def model_call_headroom():
    """Remaining model calls under the current budget, or None outside a bounded job."""
    budget = _current_budget.get()
    if budget is None:
        return None
    # Count whichever counter is further along: provider_requests can exceed model_calls
    # (SDK-internal retries on hooked clients); model_calls covers unhooked-client spend
    # the hook never sees (round-2 MINOR-4).
    return budget.max_model_calls - max(budget.model_calls, budget.provider_requests)


def register_client(client):
    budget = _current_budget.get()
    if budget is not None:
        budget.clients.append(client)


def remaining_seconds(default):
    budget = _current_budget.get()
    if budget is None or not budget.deadline:
        return default
    return max(0, min(default, budget.deadline - time.monotonic() - 1))


async def shutdown_summary_work(timeout=5):
    """Cancel admitted requests and give parser/client cleanup a bounded drain time."""
    current = asyncio.current_task()
    tasks = [task for task in tuple(_active_summary_tasks) if task is not current and not task.done()]
    for task in tasks:
        task.cancel()
    if not tasks:
        return True
    _, pending = await asyncio.wait(tasks, timeout=timeout)
    return not pending
