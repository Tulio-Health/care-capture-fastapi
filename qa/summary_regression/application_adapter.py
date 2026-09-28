"""Real FastAPI extraction and clinical-chain adapter. No DB, SSM, Redis or app startup.

Unwired scenarios are explicitly BLOCKED. This adapter never reads case expectations.
Mock mode replaces only the OpenAI HTTP boundary; application prompts and validators run.
"""
import asyncio
from contextlib import ExitStack
from contextvars import ContextVar
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace
from unittest.mock import patch
import sys

PERSISTENCE_MODE = "memory"
SUPPORTED_MODES = {"mock", "live"}
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Configurations requiring orchestration/storage/transport simulators must not be ignored.
SUPPORTED_CONFIG = {"overlap_crops", "chunk_chars", "repeat_documents", "repository_mode", "max_call_input_tokens", "max_input_tokens_per_job", "max_output_tokens", "max_images_per_call", "max_decoded_pixels", "declared_mime", "filename", "vision_enabled", "vision_response", "max_pages", "max_expanded_bytes", "max_archive_entries"}
SUPPORTED_CONFIG |= {"enabled_image_adapters", "text_without_mime_policy", "registered_rtf_aliases", "registered_aliases", "malformed_parameter_policy", "allow_unknown_text", "legacy_conversion_enabled", "disabled_adapters", "format_policy", "supported_text_encodings"}
SUPPORTED_CONFIG |= {"transport_adapter_enabled", "approved_container_profile", "max_archive_depth"}
SUPPORTED_CONFIG |= {"parameter_conflict_policy", "encoding_conflict_policy", "quality_profile"}
SUPPORTED_CONFIG |= {"source", "retry_limit", "correction_limit", "max_vision_attempts", "strict_gate_rollback_requested"}
SUPPORTED_INJECT = {"one_model_batch_fails", "postprocess_attempts_add_claim", "legacy_error_field", "http_content_encoding", "wrap_fixture_in_gzip", "append_validated_text", "parent_resource_id", "same_parent_distinct_events", "narrative_append", "evidence_offset_shift", "model_omit_fact", "parser", "model_response_key", "repeat_on_correction", "model_error", "vision", "vision_response_key", "repeat_on_retry", "model_batch_ordinal", "model_chunk_ordinal", "all_model_batches", "model_omit_document_id", "model_duplicate_document_id", "model_add_document_id", "all_downloads", "missing_path_document_id", "fact_source_id", "model_claim", "model_quote", "vision_coordinates", "vision_omit_page"}
SUPPORT_DATA = {"scan_gold.json", "clinical_gold.json", "model_responses.json"}
_RUNNER = None


def close():
    global _RUNNER
    if _RUNNER is not None:
        _RUNNER.close()
        _RUNNER = None


def run_case(case, fixture_dir, context):
    global _RUNNER
    import routing_adapter
    if case["id"] in routing_adapter.CASES:
        return routing_adapter.run_case(case)
    import control_adapter
    if control_adapter.supports(case):
        return control_adapter.run_case(case, fixture_dir, context)
    if set(case.get("fixtures", [])) & {"prior_state.json", "rich_prior_state.json", "transcript.json", "translation_adversarial.json", "conflicting_procedure_reports.json"}:
        raise NotImplementedError("Scenario fixture needs its service/repository dependency harness")
    unsupported = (set(case.get("config", {})) - SUPPORTED_CONFIG) | (set(case.get("inject", {})) - SUPPORTED_INJECT)
    if unsupported:
        raise NotImplementedError("Unwired dependency controls: " + ", ".join(sorted(unsupported)))
    with patch.dict(os.environ, {"LANGSMITH_TRACING": "false", "LANGCHAIN_TRACING_V2": "false", "OTEL_SDK_DISABLED": "true"}):
        if _RUNNER is None:
            _RUNNER = asyncio.Runner()
        return _RUNNER.run(_run(case, fixture_dir, context))


async def _run(case, fixture_dir, context):
    import httpx
    from openai import AsyncOpenAI
    from src.app.services.document_extraction import DocumentTextExtractor, DocumentProcessingError
    from src.app.services.document_ingestion import mark_parsed, require_parsed
    from src.app.models.attachment_summarization import DocumentAttachment
    from src.app.services.summary_runtime import WorkBudget, _current_budget
    import src.app.core.settings as settings_module
    import src.app.common.llm_factory as factory
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    config, inject = case.get("config", {}), dict(case.get("inject", {}))
    if inject.pop("one_model_batch_fails", False):
        inject.update(model_batch_ordinal=1, model_error="timeout")
    from src.app.services.processing_metrics import snapshot
    initial_metrics = snapshot()
    if config.get("repository_mode", "memory") != "memory":
        raise NotImplementedError("Only in-memory persistence is allowed")
    if config.get("source") not in {None, "attachment_summary", "procedure_summary"}:
        raise NotImplementedError("Source service path not wired")
    policies = {"enabled_image_adapters": ["png", "jpeg", "tiff", "webp"], "text_without_mime_policy": "strict_readability_detection", "malformed_parameter_policy": "reject", "allow_unknown_text": False, "legacy_conversion_enabled": False, "format_policy": "unsupported_before_conversion"}
    policies.update(parameter_conflict_policy="reject", encoding_conflict_policy="reject", quality_profile="strict_qa")
    for key, value in policies.items():
        if key in config and config[key] != value:
            raise NotImplementedError("Unsupported parser policy: " + key)
    for alias in config.get("registered_rtf_aliases", []):
        if DocumentTextExtractor.normalize_mime(alias)[0] != "application/rtf":
            raise NotImplementedError("RTF alias is not registered in the application")
    for alias, adapter in config.get("registered_aliases", {}).items():
        normalized = DocumentTextExtractor.normalize_mime(alias)[0]
        if normalized not in {"application/xml", "application/pdf", "image/jpeg", "image/tiff"}:
            raise NotImplementedError("Alias is not registered in the application")
    catalog = json.loads((Path(__file__).resolve().parent / "fixture_catalog.json").read_text())["fixtures"]
    canned = json.loads((fixture_dir / "model_responses.json").read_text())
    clinical_stubs = json.loads((Path(__file__).resolve().parent / "mock_clinical_responses.json").read_text())
    observations = {"calls": {"summarization": 0, "vision": 0, "model_total": 0, "database": 0, "docx_parser": 0, "final_synthesis": 0, "unvalidated_content_model": 0},
                    "boundary": {"raw_content_forwarded": False}, "error_codes": [],
                    "manual_review_completed": False, "harness": {"same_application_entrypoint": True, "replacement_summarizer_used": False}}
    capture = {"documents": [], "output": None, "prompts": [], "adapter": None, "extractions": [], "vision_pages": 0, "failed_batches": set(), "extraction_attempts": {}, "model_missing_ids": set(), "duplicate_ids": False, "unexpected_ids": False, "parsed_ocr_ids": set(), "ocr_gate_checks": []}
    batch_input = ContextVar("qa_batch_input", default=())
    procedure_input = ContextVar("qa_procedure_input", default=None)

    async def transport(request):
        body = json.loads(request.content)
        observations["calls"]["model_total"] += 1
        messages = body.get("messages", [])
        if any(isinstance(message.get("content"), list) and any(item.get("type") == "image_url" for item in message["content"]) for message in messages):
            observations["calls"]["vision"] += 1
            if inject.get("vision") == "timeout_always":
                raise httpx.ReadTimeout("Synthetic OCR timeout", request=request)
            capture.setdefault("vision_requests", []).append(messages)
            if "You verify a transcription" in str(messages[0].get("content", "")):
                missing = inject.get("vision_omit_page") == capture["vision_pages"]
                response = {"matches": not missing, "issues": [{"kind": "missing_text", "region": "page", "candidate_line": None, "candidate_quote": None, "source_quote": capture.get("last_ocr_gold", "Page text"), "reason": "Page text omitted"}] if missing else []}
            elif inject.get("vision_response_key"):
                response = canned[inject["vision_response_key"]]
            else:
                # Only explicit mock transcription fixtures may supply OCR text.
                gold = json.loads((fixture_dir / "scan_gold.json").read_text())
                pages = gold.get("pages", []) if isinstance(gold, dict) else gold
                is_region = any("region" in item.get("text", "") for message in messages for item in (message.get("content", []) if isinstance(message.get("content"), list) else []) if isinstance(item, dict))
                page_prompt = " ".join(item.get("text", "") for message in messages for item in (message.get("content", []) if isinstance(message.get("content"), list) else []) if isinstance(item, dict))
                page_match = re.search(r"Transcribe page (\d+)", page_prompt)
                ordinal = (int(page_match.group(1)) - 1 if page_match else capture.get("fixture_ocr_page", 0)) + (1 if capture.get("active_fixture") == "scan_page2.jpg" else 0)
                if is_region:
                    capture["region_calls"] = capture.get("region_calls", 0) + 1
                    text = capture.get("last_ocr_gold", "")
                else:
                    capture["vision_pages"] += 1
                    capture["fixture_ocr_page"] = capture.get("fixture_ocr_page", 0) + 1
                    page = pages[ordinal] if ordinal < len(pages) else {}
                    text = page.get("text", "") if isinstance(page, dict) else str(page)
                    capture["last_ocr_gold"] = text
                response = {"text": text, "unreadable_regions": [], "complete": inject.get("vision") != "unreadable"}
            if inject.get("vision_coordinates"):
                response["coordinates"] = [{"x": 999999, "y": -1}]
            if inject.get("vision_omit_page") == capture["vision_pages"] and "text" in response:
                response["text"] = ""
            message = {"role": "assistant", "content": json.dumps(response)}
        else:
            observations["calls"]["summarization"] += 1
            capture["prompts"].append(messages)
            active = batch_input.get()
            target = inject.get("model_batch_ordinal", inject.get("model_chunk_ordinal"))
            target_failure = bool(active) and (target is None or capture["batch_ordinals"].get(active[0].resource_id) == target)
            if (inject.get("model_error") and target_failure) or (inject.get("all_model_batches") and active):
                raise httpx.ReadTimeout("Synthetic model timeout", request=request)
            tool = body["tools"][0]["function"]
            props = tool.get("parameters", {}).get("properties", {})
            if "supported" in props:
                response = {"supported": True, "issues": []}
            elif "procedures" in props and "evidence_quotes" in props:
                document = procedure_input.get()
                events = list(clinical_stubs.get(document.title, {}).get("procedures", []))
                if inject.get("append_validated_text"):
                    events.append({"description":"Biopsy","status":"performed","source_quote":inject["append_validated_text"]})
                response = {"procedures": [{"source_document_title": document.title, "event_source_quote": event["source_quote"], "procedure_type": event["description"], "reason": "Not documented in this procedure report.", "procedure_details": event["source_quote"], "outcome": "Not documented in this procedure report.", "follow_up": "Not documented in this procedure report."} for event in events if event["status"] == "performed" and event["source_quote"] in document.extracted_text], "evidence_quotes": [document.extracted_text]}
            elif "clinical_summary" in props:
                observations["calls"]["final_synthesis"] += 1
                records = json.JSONDecoder().raw_decode(messages[-1]["content"])[0]["validated_source_records"]
                response = {"clinical_summary": "\n\n".join(r.get("narrative_summary", r.get("clinical_summary", "")) for r in records), "documents_analyzed": len(records)}
                # Synthetic long-input fixtures contain repeated administrative
                # filler. The mock reduce response compresses that fixture noise;
                # real source chunks still go through the production map stage.
                response["clinical_summary"] = re.sub(r"(?:Administrative filler\.\s*)+", "", response["clinical_summary"])
                for target, source in (("diagnoses_mentioned", "diagnoses"), ("medications_mentioned", "medications"), ("procedures_mentioned", "procedures_performed"), ("lab_results", "lab_results")):
                    response[target] = [value for record in records for value in record.get(source, [])]
            else:
                # Boundary stub emits one object per actual batch input, including chunks.
                # It does not consult expected outcomes or claim clinical accuracy.
                response = {"response": [{"source_document_id": doc.resource_id, "source_document_title": doc.title or "Synthetic QA document", "source_document_type": "Clinical note", "evidence_quotes": [doc.extracted_text], "narrative_summary": doc.extracted_text} for doc in batch_input.get()]}
                for value, doc in zip(response["response"], batch_input.get()):
                    value.update(clinical_stubs.get(doc.title, {}))
                if inject.get("narrative_append"):
                    for item in response["response"]:
                        item["narrative_summary"] += "\n" + inject["narrative_append"]
                if inject.get("evidence_offset_shift"):
                    for item in response["response"]:
                        item["evidence_offsets"] = [{"start":inject["evidence_offset_shift"],"end":20}]
                if inject.get("model_omit_fact"):
                    for item in response["response"]:
                        item["diagnoses"] = []
                        item["narrative_summary"] = item["narrative_summary"].replace(inject["model_omit_fact"], "")
                if inject.get("fact_source_id") and response["response"]:
                    response["response"][0]["source_document_id"] = inject["fact_source_id"]
                if inject.get("model_claim") and response["response"]:
                    response["response"][0]["procedures"] = [{"description": inject["model_claim"], "status": "performed", "source_quote": inject["model_quote"]}]
                if inject.get("model_omit_document_id"):
                    wanted = inject["model_omit_document_id"].replace("doc-b", "doc-1").replace("doc-a", "doc-0")
                    removed = [v["source_document_id"] for v in response["response"] if v["source_document_id"].split(":chunk:")[0] == wanted]
                    response["response"] = [v for v in response["response"] if v["source_document_id"] not in removed]
                    capture["model_missing_ids"].update(removed)
                if inject.get("model_duplicate_document_id") and response["response"]:
                    response["response"].append(dict(response["response"][0])); capture["duplicate_ids"] = True
                if inject.get("model_add_document_id") and response["response"]:
                    response["response"].append({**response["response"][0], "source_document_id": inject["model_add_document_id"]}); capture["unexpected_ids"] = True
                if inject.get("model_response_key"):
                    injected = canned[inject["model_response_key"]]
                    if inject["model_response_key"] in {"fabricated_procedure", "same_count_wrong_identity"}:
                        response["response"][0]["procedures"] = [{"description": p["name"], "status": p["status"], "source_quote": p.get("quote", "Ultrasound was performed.")} for p in injected["procedures"]]
                    elif inject["model_response_key"] == "missing_quote":
                        response["response"][0]["evidence_quotes"] = [injected["facts"][0]["quote"]]
                    else:
                        response = injected
            message = {"role": "assistant", "content": None, "tool_calls": [{"id": "qa-call", "type": "function", "function": {"name": tool["name"], "arguments": json.dumps(response)}}]}
        return httpx.Response(200, json={"id": "qa-response", "object": "chat.completion", "created": 0, "model": body["model"], "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}], "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})

    from src.app.services.summary_runtime import reserve_provider_request
    async def budget_hook(request):
        await reserve_provider_request(request)
        capture.setdefault("provider_bodies", []).append(json.loads(request.content))
    client = context.ai.make_async_client() if context.uses_live_ai else AsyncOpenAI(api_key="regression-mock", base_url="https://api.openai.com/v1", max_retries=0, http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport), trust_env=False))
    client._client.event_hooks.setdefault("request", []).append(budget_hook)
    def model_factory(*args, **kwargs):
        name = (context.ai.config.vision_model if args and args[0] == settings.DOCUMENT_VERIFICATION_MODEL else context.ai.config.model) if context.uses_live_ai else "gpt-4o-mini"
        return OpenAIChatModel(name, provider=OpenAIProvider(openai_client=client))
    settings = SimpleNamespace(ENABLE_DOCUMENT_OCR=config.get("vision_enabled", True), DOCUMENT_OCR_MODEL=context.ai.config.vision_model if context.uses_live_ai else "gpt-4o-mini", OPENAI_API_KEY="", LANGSMITH_TRACING="false", DOCUMENT_VERIFICATION_MODEL=context.ai.config.vision_model if context.uses_live_ai else "gpt-4.1-mini")
    initial_calls = context.ai.calls if context.uses_live_ai else 0
    # Case-config keys are a stable external contract; translate the byte-measured ones
    # onto WorkBudget's renamed *_bytes fields (audit R5).
    budget_fields = {"max_call_input_tokens": "max_call_input_bytes", "max_input_tokens_per_job": "max_input_bytes_per_job", "max_output_tokens": "max_output_tokens", "max_images_per_call": "max_images_per_call"}
    token = _current_budget.set(WorkBudget(**{budget_fields[key]:config[key] for key in budget_fields if key in config}))
    try:
        with ExitStack() as stack:
            stack.enter_context(patch.object(settings_module, "get_settings", return_value=settings))
            if "chunk_chars" in config:
                import src.app.chains.attachment_summarization.chain as attachment_chain
                stack.enter_context(patch.object(attachment_chain, "CHUNK_CHAR_LIMIT", config["chunk_chars"]))
            if "retry_limit" in config:
                from src.app.services import summary_runtime
                stack.enter_context(patch.object(summary_runtime, "MAX_TRANSIENT_RETRIES", config["retry_limit"]))
            if config.get("correction_limit", 1) != 1 or config.get("max_vision_attempts", 2) != 2:
                raise NotImplementedError("Requested repair policy is not implemented")
            stack.enter_context(patch.object(factory, "get_pydantic_ai_model", side_effect=model_factory))
            from src.app.services import document_ocr as ocr_module
            if config.get("overlap_crops"):
                from src.app.services import ocr_regions
                stack.enter_context(patch.object(ocr_regions, "REGION_HEIGHT", 600))
                stack.enter_context(patch.object(ocr_regions, "REGION_OVERLAP", 100))
            if "max_output_tokens" in config:
                stack.enter_context(patch.object(ocr_module, "MAX_OCR_OUTPUT_TOKENS", config["max_output_tokens"]))
            if "max_decoded_pixels" in config:
                stack.enter_context(patch.object(ocr_module, "MAX_DECODED_PIXELS", config["max_decoded_pixels"]))
            render = ocr_module.render_pages
            async def observed_render(*args, **kwargs):
                pages = await render(*args, **kwargs)
                capture["rendered_pages"] = capture.get("rendered_pages", 0) + len(pages)
                return pages
            stack.enter_context(patch.object(ocr_module, "render_pages", observed_render))
            # OCR owns its production client; use a borrowed wrapper so it cannot close the shared client early.
            class BorrowedClient:
                chat = client.chat
                async def close(self): pass
            stack.enter_context(patch.object(factory, "create_document_ai_client", return_value=BorrowedClient()))
            for setting, attribute in (("max_pages", "MAX_PAGES"), ("max_expanded_bytes", "MAX_ARCHIVE_EXPANDED_BYTES"), ("max_archive_entries", "MAX_ZIP_ENTRIES"), ("max_archive_depth", "MAX_ARCHIVE_DEPTH")):
                if setting in config:
                    stack.enter_context(patch.object(DocumentTextExtractor, attribute, config[setting]))
            if inject.get("parser"):
                parser = str(inject["parser"]).split(":")[-1]
                method = {"rtf": "_extract_from_rtf", "html": "_html_text"}.get(parser)
                if method is None:
                    raise NotImplementedError("Unwired parser injection")
                stack.enter_context(patch.object(DocumentTextExtractor, method, side_effect=ValueError("synthetic parser failure")))
            adapters = {"_extract_from_pdf": "pdf", "_extract_from_docx": "docx", "_extract_from_rtf": "rtf", "_xml_text": "xml", "_html_text": "html"}
            for method, adapter_name in adapters.items():
                if inject.get("parser"):
                    continue
                original = getattr(DocumentTextExtractor, method)
                if method in {"_xml_text", "_html_text"}:
                    def wrapped(*args, _original=original, _name=adapter_name, **kwargs):
                        capture["adapter"] = _name
                        if _name == "docx": observations["calls"]["docx_parser"] += 1
                        return _original(*args, **kwargs)
                    stack.enter_context(patch.object(DocumentTextExtractor, method, staticmethod(wrapped)))
                else:
                    def wrapped(self, *args, _original=original, _name=adapter_name, **kwargs):
                        capture["adapter"] = _name
                        return _original(self, *args, **kwargs)
                    stack.enter_context(patch.object(DocumentTextExtractor, method, wrapped))
            documents = []
            fixture_names = case.get("fixtures", []) * config.get("repeat_documents", 1)
            if "connector_envelopes.json" in fixture_names:
                from src.app.services.document_ingestion import process_attachments
                from unittest.mock import AsyncMock
                envelope = json.loads((fixture_dir / "connector_envelopes.json").read_text())["sources"][0]
                references = []
                for item in envelope["documents"]:
                    metadata = {"filePath": "qa://" + item["file"], "fileName": item["file"], "title": item["file"], "contentType": item["contentType"], "downloadStatus": inject.get("all_downloads", item["downloadStatus"])}
                    if inject.get("missing_path_document_id") == item["id"]:
                        metadata.pop("filePath")
                    references.append(SimpleNamespace(ehr_resource_id=item["id"], data={"attachments": [metadata]}))
                async def download(path): return (fixture_dir / path.removeprefix("qa://")).read_bytes()
                storage = SimpleNamespace(download_document=AsyncMock(side_effect=download))
                documents = await process_attachments(references, storage, DocumentTextExtractor())
                observations["calls"]["document_download"] = storage.download_document.await_count
                observations["error_codes"].extend(d.extraction_error for d in documents if d.extraction_error)
                fixture_names = []
            if inject.get("parent_resource_id"):
                from src.app.services.document_ingestion import process_attachments
                from unittest.mock import AsyncMock
                reference=SimpleNamespace(ehr_resource_id=inject["parent_resource_id"],data={"attachments":[{"filePath":"qa://"+name,"title":name,"contentType":catalog[name]["mime"],"downloadStatus":"success"} for name in fixture_names]})
                async def download_sibling(path):return (fixture_dir/path.removeprefix("qa://")).read_bytes()
                documents=await process_attachments([reference],SimpleNamespace(download_document=AsyncMock(side_effect=download_sibling)),DocumentTextExtractor())
                observations["identity"]={"distinct_attachment_ids":len({d.resource_id for d in documents})}
                fixture_names=[]
            for index, name in enumerate(fixture_names):
                if name in SUPPORT_DATA:
                    continue
                capture["fixture_ocr_page"] = 0
                info = catalog[name]
                content = (fixture_dir / name).read_bytes()
                if inject.get("append_validated_text"):
                    content += b"\n" + inject["append_validated_text"].encode()
                if inject.get("http_content_encoding"):
                    import gzip,io
                    from src.app.utils.s3_client import S3DocumentClient
                    from unittest.mock import Mock
                    if inject.get("wrap_fixture_in_gzip"):content=gzip.compress(content)
                    storage=S3DocumentClient(allowed_prefixes=['s3://qa-bucket/'])
                    storage.s3_client=SimpleNamespace(get_object=Mock(return_value={'Body':io.BytesIO(content),'ContentLength':len(content),'ContentEncoding':inject['http_content_encoding'],'ETag':'qa'}))
                    content=await storage.download_document('s3://qa-bucket/'+name)
                    observations.setdefault("transport",{})["http_decode_count"]=storage.transport_decode_counts['s3://qa-bucket/'+name]
                capture["active_fixture"] = name
                capture["vision_pages"] = 0
                mime = config.get("declared_mime", info["mime"])
                filename = config.get("filename", name)
                document = DocumentAttachment(file_path=f"qa://{name}", content_type=mime or "application/octet-stream", title=name, resource_id=f"doc-{index}", extracted_text="")
                extractor = DocumentTextExtractor(disabled_adapters=config.get("disabled_adapters", []), transport_enabled=config.get("transport_adapter_enabled", True), allow_containers=True)
                try:
                    # Same production parser; in-process invocation allows deliberate parser fault injection.
                    try:
                        document.extracted_text = extractor.extract_text(content, mime, filename)
                    except DocumentProcessingError as exc:
                        if exc.code != "OCR_REQUIRED":
                            raise
                        from src.app.services.document_ocr import extract_scanned_document
                        document.extracted_text = await extract_scanned_document(content, mime, client=client, model=settings.DOCUMENT_OCR_MODEL)
                    document.content_sha256 = sha256(content).hexdigest()
                    mark_parsed(document)
                    require_parsed(document)
                    if "[OCR page " in document.extracted_text:
                        capture["parsed_ocr_ids"].add(document.resource_id)
                except DocumentProcessingError as exc:
                    document.extraction_error = exc.code
                    capture["accepted_failed_document_pages"] = capture.get("accepted_failed_document_pages", 0) + getattr(exc, "accepted_pages", 0)
                    observations["error_codes"].append(exc.code)
                capture["adapter"] = extractor.last_adapter or capture["adapter"]
                observations.setdefault("transport", {}).setdefault("decode_count", 0)
                observations["transport"]["decode_count"] += extractor.decode_count
                observations["transport"]["file_decode_count"] = extractor.decode_count
                observations.setdefault("extraction", {}).update({"declared_mime_preserved": extractor.declared_mime == mime, "mime_mismatch": extractor.detected_mime is not None and extractor.detected_mime != (mime or "application/octet-stream").split(';')[0].strip().lower()})
                documents.append(document)
            capture["documents"] = documents
            valid = [d for d in documents if not d.extraction_error]
            if config.get("source") == "procedure_summary":
                from src.app.chains.procedure_extraction import chain as procedure_chain
                from src.app.chains.procedure_extraction.consolidation import ProcedureConsolidator
                from src.app.services.summarization.procedure_summarization import ProcedureSummarizationService
                from src.app.models.procedure_summarization import ProcedureSummarizationRequest
                from test_publication_safety import setup_repository
                from uuid import uuid4
                import logging
                stack.enter_context(patch.object(procedure_chain, "get_pydantic_ai_model", side_effect=model_factory))
                original_one = procedure_chain.ProcedureExtractionChain._extract_one
                async def observed_one(chain, document):
                    local_token = procedure_input.set(document)
                    try:
                        return await original_one(chain, document)
                    finally:
                        procedure_input.reset(local_token)
                stack.enter_context(patch.object(procedure_chain.ProcedureExtractionChain, "_extract_one", observed_one))
                extracted, failures = await procedure_chain.ProcedureExtractionChain().extract(valid)
                failures.extend({"source_id": d.resource_id, "error": d.extraction_error} for d in documents if d.extraction_error)
                consolidated = await ProcedureConsolidator().consolidate(extracted)
                repository, session = setup_repository()
                service = object.__new__(ProcedureSummarizationService)
                service.summaries_repo, service.db, service.logger = repository, session, logging.getLogger("qa.procedure")
                request_model = ProcedureSummarizationRequest(appointment_id=uuid4(), user_id=uuid4())
                try:
                    saved = await service._persist(request_model, consolidated, len(valid), failures)
                except DocumentProcessingError as exc:
                    observations["error_codes"].append(exc.code)
                    saved = []
                observations["outcome"] = "partial" if saved and failures else "success" if saved or valid and not failures else "unavailable"
                observations["display"] = {"text": "\n\n".join(row.summary_text for row in saved)}
                observations["clinical"] = {"extracted_event_count": len(extracted), "current_performed_procedures": [item.summary.procedure_type for item in extracted]}
                observations["http"] = {"response_is_list": isinstance(saved, list)}
                observations["persistence"] = {"distinct_event_rows": len(session.rows), "pruned_rows": len(session.deleted), "placeholder_procedure_rows": sum(not (row.data or {}).get("procedure_type") for row in session.rows)}
                observations["model_input"] = {"text": json.dumps(capture["prompts"], ensure_ascii=False)}
                observations["coverage"] = {"complete": not failures and len(valid) == len(documents)}
                observations["pipeline_output"] = {"summary": [row.model_dump(mode="json", by_alias=True) for row in saved], "extractions": [item.summary.model_dump() for item in extracted], "failures": failures}
                return observations
            from src.app.chains.attachment_summarization import chain as chain_module
            stack.enter_context(patch.object(chain_module, "get_pydantic_ai_model", side_effect=model_factory))
            try:
                capture["batch_ordinals"] = {batch[0].resource_id: n for n, batch in enumerate(chain_module._create_batches(valid), 1)}
            except DocumentProcessingError:
                capture["batch_ordinals"] = {}  # Let the real chain produce the job-limit outcome.
            original_extract = chain_module.AttachmentSummarizationChain._extract_batch
            async def observed_extract(chain, *args, **kwargs):
                batch = args[0] if args else kwargs["batch"]
                capture["extraction_attempts"][batch[0].resource_id] = capture["extraction_attempts"].get(batch[0].resource_id, 0) + 1
                for document in batch:
                    if "[OCR page " in document.extracted_text:
                        capture["ocr_gate_checks"].append(document.resource_id.split(":chunk:")[0] in capture["parsed_ocr_ids"])
                    try:
                        require_parsed(document)
                    except DocumentProcessingError:
                        observations["boundary"]["raw_content_forwarded"] = True
                        raise
                batch_token = batch_input.set(batch)
                try:
                    summaries = await original_extract(chain, *args, **kwargs)
                except Exception:
                    capture["failed_batches"].update(d.resource_id for d in batch)
                    raise
                finally:
                    batch_input.reset(batch_token)
                capture["extractions"].extend(summaries)
                return summaries
            stack.enter_context(patch.object(chain_module.AttachmentSummarizationChain, "_extract_batch", observed_extract))
            output = None
            if valid:
                try:
                    output = await chain_module.AttachmentSummarizationChain().analyze({}, documents)
                except Exception as exc:
                    observations["error_codes"].append(getattr(exc, "code", type(exc).__name__))
                    current, seen = exc, set()
                    while current is not None and id(current) not in seen:
                        seen.add(id(current))
                        if hasattr(current, "validation_issues"):
                            observations.setdefault("validation_issues", []).extend(current.validation_issues)
                            observations.setdefault("rejected_candidates", []).append(getattr(current, "validation_candidate", None))
                        current = current.__cause__ or current.__context__
            if inject.get("postprocess_attempts_add_claim") and output:
                from src.app.services.validated_summary import require_validated_summary
                output.clinical_summary += " " + inject["postprocess_attempts_add_claim"]
                try:require_validated_summary(output)
                except DocumentProcessingError as exc:
                    observations["error_codes"].append(exc.code)
                    observations["postprocess_rejected"] = True
                    output = None
            capture["output"] = output.model_dump(mode="json") if output else None
            observations.setdefault("extraction", {}).update({"status": "success" if valid else "failed", "adapter": capture["adapter"] or "text", "text": "\n\n".join(d.extracted_text for d in valid)})
            observations["outcome"] = "partial" if output and output.extraction_errors else "success" if output else "unavailable"
            # Exercise the production JSON publication builder and response serializer.
            # This is a capture at the persistence boundary, never a database write.
            from datetime import datetime, timezone
            from uuid import UUID
            from src.app.models.attachment_summarization import AttachmentSummarizationRequest, AttachmentSummarizationResponse
            from src.app.models.conversation_summaries import ConversationSummary
            from src.app.services.summarization.attachment_summarization import AttachmentSummarizationService, _static_fallback_summary_data
            from src.app.services.summary_outcomes import MESSAGES
            identity = UUID("00000000-0000-4000-8000-000000000001")
            request_model = AttachmentSummarizationRequest(appointment_id=identity, user_id=identity)
            appointment = SimpleNamespace(appointment_date=None, purpose=None, ehr_entity_id="qa-encounter")
            result_model = output or AttachmentSummarizationResponse(clinical_summary="", documents_analyzed=0, extraction_errors=[{"error": code} for code in observations["error_codes"]])
            if "legacy_error_field" in inject:
                result_model = result_model.model_copy(update={"error":inject["legacy_error_field"]})
            payload = AttachmentSummarizationService._prepare_summary_data(None, request_model, appointment, "N/A", result_model, documents) if documents else _static_fallback_summary_data(request_model, appointment, "N/A")
            wire = ConversationSummary.model_validate({**payload, "id": identity, "appointment_id": identity, "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}).model_dump(mode="json", by_alias=True)
            state = payload["summary_metadata"]["processing_outcome"]
            observations["outcome"] = "success" if state == "complete" else state
            observations["attempt"] = {"reported_complete": state == "complete"}
            notice = MESSAGES.get(state, "")
            if state == "unavailable":
                from src.app.services.summary_outcomes import unavailable_message
                notice = unavailable_message(payload["summary_metadata"].get("processing_errors", []))
            observations["display"] = {"text": wire["summaryText"], "kind": state, "notice_is_prefix": bool(notice) and wire["summaryText"].startswith(notice), "notice_count": wire["summaryText"].count(notice) if notice else 0, "template_used": bool(notice) and wire["summaryText"].startswith(notice)}
            observations["persistence"] = {"display_matches_summary_text": observations["display"]["text"] == wire["summaryText"], "boundary_payload": wire}
            if inject.get("postprocess_attempts_add_claim"):
                observations["persistence"]["final_clinical_text_validated"] = observations.get("postprocess_rejected", False) and inject["postprocess_attempts_add_claim"] not in wire["summaryText"]
            observations["http"] = {"public_contract_unchanged": set(wire) == {"id", "appointmentId", "userId", "summaryText", "keyPoints", "medications", "diagnoses", "instructions", "recommendations", "data", "summaryMetadata", "createdAt", "updatedAt", "createdBy", "updatedBy"}}
            observations["coverage"] = {"expected_documents": len(documents), "failed_documents": payload["summary_metadata"]["failed_documents"], "complete": bool(output) and not output.extraction_errors and len(valid) == len(documents)}
            accepted_pages = [int(page) for document in valid for page in re.findall(r"\[(?:OCR page|Page) (\d+)\]", document.extracted_text)]
            observations["coverage"].update({"expected_pages": capture.get("rendered_pages", 0), "accepted_pages": len(accepted_pages) + capture.get("accepted_failed_document_pages", 0), "duplicate_pages": sum(len(ids) - len(set(ids)) for ids in ([int(page) for page in re.findall(r"\[(?:OCR page|Page) (\d+)\]", document.extracted_text)] for document in valid))})
            observations["coverage"].update(failed_chunks=len(capture["failed_batches"]), failed_model_batches=len(capture["failed_batches"]), missing_model_documents=len(capture["model_missing_ids"]), duplicate_model_ids_rejected=capture["duplicate_ids"] and bool(capture["failed_batches"]), unexpected_model_ids_rejected=capture["unexpected_ids"] and bool(capture["failed_batches"]))
            observations["boundary"]["vision_output_validated_before_summary"] = bool(capture["ocr_gate_checks"]) and all(capture["ocr_gate_checks"])
            observations["boundary"]["prior_guess_used_as_evidence"] = any("candidate_transcription" in json.dumps(messages) for messages in capture.get("vision_requests", []) if "transcription engine" in str(messages[0].get("content", "")))
            observations["retry"] = {"count": sum(max(0, n-1) for n in capture["extraction_attempts"].values())}
            observations["coverage"]["manifest_reconciles"] = payload["summary_metadata"]["successful_documents"] + payload["summary_metadata"]["failed_documents"] == len(documents)
            observations["resources"] = {"limit_enforced": any(code in {"FILE_TOO_LARGE", "RESOURCE_LIMIT_EXCEEDED"} for code in observations["error_codes"])}
            observations["resources"]["all_model_calls_within_budget"] = all(body.get("max_completion_tokens",body.get("max_tokens",0)) <= config.get("max_output_tokens",4096) for body in capture.get("provider_bodies",[]))
            if config.get("overlap_crops"):
                anchor = capture.get("last_ocr_gold", "").strip()
                occurrences = sum(d.extracted_text.count(anchor) for d in valid) if anchor else 0
                observations["coverage"]["duplicate_regions"] = max(0, occurrences - len(valid))
                observations["coverage"]["regions_checked"] = capture.get("region_calls", 0)
            observations["coverage"]["all_pages_accounted"] = bool(documents) and all(d.extraction_error or d in valid for d in documents)
            observations["calls"]["error_message_generation"] = 0
            observations["clinical"] = {"current_performed_procedures": output.procedures_mentioned if output else []}
            if not output:
                clinical_fields = (wire["keyPoints"], wire["medications"], wire["diagnoses"], wire["instructions"], wire["recommendations"])
                observations["clinical"]["placeholder_fields_empty"] = not any(clinical_fields) and not any(wire["data"].values())
                observations["clinical"]["unsupported_claims_published"] = sum(len(values or []) for values in clinical_fields) + sum(len(values or []) for values in wire["data"].values())
            from clinical_observations import measure
            observations["clinical"].update(measure(output, capture["extractions"], valid))
            if inject.get("vision_coordinates"):
                observations["clinical"]["unverified_coordinates_accepted"] = bool(output)
            if inject.get("evidence_offset_shift"):
                observations["clinical"]["invalid_evidence_accepted"] = bool(output)
            if inject.get("model_omit_fact"):
                observations["clinical"]["omission_detected"] = output is None and "CLINICAL_EVIDENCE_FAILED" in observations["error_codes"]
            observations["clinical"]["ordered_procedures"] = [p.description for summary in capture["extractions"] for p in summary.procedures if p.status == "ordered"]
            observations["clinical"]["confirmed_diagnoses"] = [d.official_diagnosis for d in output.diagnoses_mentioned] if output else []
            observations["clinical"]["active_medications"] = [m for m in output.medications_mentioned if not re.search(r"\b(stopped|discontinued|cancelled)\b", m, re.I)] if output else []
            observations["clinical"]["amoxicillin_dose"] = next((m for m in observations["clinical"]["active_medications"] if "amoxicillin" in m.lower() and "dose not documented" not in m.lower()), None)
            if context.uses_live_ai:
                observations["calls"]["model_total"] = context.ai.calls - initial_calls
            observations["pipeline_output"] = {"documents": [d.model_dump(mode="json") for d in documents], "summary": capture["output"], "parser_version": DocumentTextExtractor.VERSION, "extractions": [item.model_dump(mode="json") for item in capture["extractions"]]}
            observations["model_input"] = {"text": json.dumps(capture["prompts"], ensure_ascii=False)}
            # A whole-job budget refusal accounts for input by explicitly withholding the summary.
            observations["coverage"]["all_chunks_accounted"] = bool(output) and not output.extraction_errors or (output is None and "RESOURCE_LIMIT_EXCEEDED" in observations["error_codes"])
            metrics = snapshot()
            observed_stages = {key.split(":")[0] for key, count in metrics.items() if count > initial_metrics.get(key, 0)}
            observations["observability"] = {"stage_metrics_distinct": {"parsing", "extraction", "coverage"} <= observed_stages, "stage_events": sorted(observed_stages)}
            if "one_model_batch_fails" in case.get("inject", {}):
                observations["boundary"]["secret_leaked"] = any("SECRET_QA_TOKEN" in key for key in metrics)
            return observations
    finally:
        _current_budget.reset(token)
        await client.close()
