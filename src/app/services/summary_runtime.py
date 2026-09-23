"""Per-worker admission, request deadlines and shared model-call budgets."""
import asyncio
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import wraps
from src.app.services.document_extraction import DocumentProcessingError


@dataclass
class WorkBudget:
    max_model_calls: int = 64
    # The one model-call counter, owned by the per-HTTP-request hook
    # (reserve_provider_request). Within a bounded job every model call routes through a
    # hooked client, so this is strictly the stronger boundary (it also sees SDK-internal
    # retries); the former twin `model_calls` check-then-increment in model_call was the
    # weaker duplicate and was merged onto this counter (audit R5).
    provider_requests: int = 0
    # Byte-measured bounds (UTF-8 byte length is a conservative bound for text BPE tokens).
    input_upper_bound_bytes: int = 0
    max_call_input_bytes: int = 160_000
    max_input_bytes_per_job: int = 4_000_000
    max_output_tokens: int = 4096
    max_images_per_call: int = 1
    clients: list = field(default_factory=list)
    deadline: float = 0.0
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


request_started = ContextVar("summary_request_started", default=None)

_current_budget = ContextVar("summary_work_budget", default=None)
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
        if budget is not None and budget.provider_requests >= budget.max_model_calls:
            # Cheap fast-fail on the shared counter; the authoritative increment lives in
            # reserve_provider_request (the httpx request hook).
            raise DocumentProcessingError("MODEL_CALL_BUDGET_EXCEEDED")
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
            deadline = (request_started.get() or time.monotonic()) + duration
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
        if (images > budget.max_images_per_call or text_bound > budget.max_call_input_bytes
                or budget.input_upper_bound_bytes + text_bound > budget.max_input_bytes_per_job
                or not isinstance(output_limit, int) or output_limit > budget.max_output_tokens):
            raise DocumentProcessingError("MODEL_CALL_BUDGET_EXCEEDED")
        budget.input_upper_bound_bytes += text_bound
        budget.provider_requests += 1


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
