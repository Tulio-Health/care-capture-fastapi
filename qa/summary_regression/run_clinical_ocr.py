"""Live OCR qualification with optional production summarization. No database access."""
import asyncio
import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ai_runtime import load_config, RegressionAI, redact

DATA = ROOT / 'qa/testdata/web_clinical_samples/ocr'
RESULTS = ROOT / 'qa/results/clinical_ocr_live'
SUMMARIZE = False
ALL_SAMPLES = False
REPEAT = 1


def write_report(report):
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    e = html.escape
    sections = []
    for row in report['documents']:
        sections.append('<section><h2>' + e(row['file']) + ' — attempt ' + str(row.get('repeat_index', 1)) + '</h2><p><strong>' + e(row['status']) + '</strong> — ' + e(row.get('reason', '')) + '</p>'
                        '<p>Error: ' + e(row.get('error_code', 'None')) + ' · Detail: ' + e(row.get('detail_code', 'None')) + '</p>'
                        '<p><a href="' + e(os.path.relpath(DATA / row['file'], RESULTS)) + '">OCR input PDF</a> · '
                        '<a href="' + e(os.path.relpath(DATA / row['original'], RESULTS)) + '">Original reference document</a></p>'
                        '<p>Fixture: ' + e(row.get('fixture_kind', 'Public clinical sample')) + '</p><p>Case expectations: ' + e(row.get('expected', 'Faithful complete extraction; no invented facts.')) + '</p>'
                        '<details><summary>QA reference (not supplied to the model)</summary><pre>' + e(row.get('reference_text', 'Compare against linked original.')) + '</pre></details>'
                        '<p>Expected: complete faithful transcription, followed by a source-grounded summary when requested. Rejected text must be withheld; rejection confirms containment, not successful clinical extraction.</p><p>OCR stage: ' + e(row.get('ocr_status', 'NOT_RUN')) + ' · Summary stage: ' + e(row.get('summary_status', 'NOT_RUN')) + '</p><h3>Accepted document transcription</h3><pre>' + e(row.get('accepted_text') or 'No complete document transcription accepted.') + '</pre>'
                        '<h3>Clinical summarization</h3><pre>' + e(json.dumps({'status': row.get('summary_status', 'NOT_RUN'), 'output': row.get('summary'), 'validation_findings': row.get('validation_findings', [])}, indent=2, ensure_ascii=False)) + '</pre>'
                        '<details><summary>Actual OCR responses and verification findings</summary><p>These are diagnostic candidates. They are not approved or published text when the document is rejected.</p><pre>'
                        + e(json.dumps(row.get('responses', []), indent=2, ensure_ascii=False)) + '</pre></details></section>')
    page = '<!doctype html><html lang="en"><meta charset="utf-8"><title>Clinical OCR-only results</title><style>body{font:16px/1.5 system-ui;max-width:1150px;margin:30px auto;padding:0 20px}section{border-top:1px solid #ccc;padding:20px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f7;padding:16px}.note{background:#fff1cc;padding:16px}</style><h1>Clinical OCR-only results</h1>'
    page += '<p>Run: ' + e(report['run_id']) + ' · State: ' + e(report['state']) + '</p><div class="note">LIVE OCR only. No summarization, database access, or application startup. Model verification is not clinical approval. Unprocessed cases are not passes.</div>'
    counts = {status: sum(row['status'] == status for row in report['documents']) for status in sorted({row['status'] for row in report['documents']})}
    page += '<h2>Outcomes</h2><pre>' + e(json.dumps(counts, indent=2)) + '</pre>'
    if report.get('assessment'):
        page += '<h2>Run assessment</h2><pre>' + e(json.dumps(report['assessment'], indent=2, ensure_ascii=False)) + '</pre>'
    page += '<h2>Run settings and usage</h2><pre>' + e(json.dumps({'settings': report['settings'], 'usage': report.get('usage'), 'configuration_error': report.get('configuration_error')}, indent=2)) + '</pre>' + ''.join(sections) + '</html>'
    if SUMMARIZE:
        page = page.replace('Clinical OCR-only results', 'Clinical OCR and summarization results').replace('LIVE OCR only. No summarization, database access, or application startup.', 'LIVE OCR followed by production clinical summarization for accepted text. No database access or application startup.')
    (RESULTS / 'report.html').write_text(page)


async def main():
    if ALL_SAMPLES:
        manifest = {'documents': []}
        for directory in (DATA / 'web_clinical_samples/ocr', DATA / 'clinical_ocr_positive/ocr'):
            for original_row in json.loads((directory / 'manifest.json').read_text())['documents']:
                row = dict(original_row)
                row['file'] = str((directory / row['file']).relative_to(DATA))
                row['original'] = str((directory / row['original']).resolve().relative_to(DATA))
                manifest['documents'].append(row)
    else:
        manifest = json.loads((DATA / 'manifest.json').read_text())
    manifest['documents'] = [{**row, 'repeat_index': repeat} for repeat in range(1, REPEAT + 1) for row in manifest['documents']]
    report = {'run_id': datetime.now(timezone.utc).isoformat(), 'state': 'running',
              'repeat': REPEAT, 'mode': 'live_ocr_summary' if SUMMARIZE else 'live_ocr_only', 'summarization_calls': 0, 'database_writes': 0,
              'settings': {}, 'documents': [{**row, 'status': 'NOT_RUN', 'ocr_status': 'NOT_RUN', 'summary_status': 'NOT_RUN'} for row in manifest['documents']]}
    try:
        config = load_config(ROOT / 'qa/.env.regression.local')
    except Exception as exc:
        report['configuration_error'] = type(exc).__name__
        for row in report['documents']:
            row.update(status='BLOCKED', reason='Regression-only AI configuration unavailable.')
        report['state'] = 'completed'
        write_report(report)
        return 1
    from src.app.services.document_extraction import DocumentTextExtractor, DocumentProcessingError
    from src.app.services.document_ocr import extract_scanned_document
    from src.app.services.summary_runtime import WorkBudget, _current_budget

    ai = RegressionAI(config)
    report['settings'] = {'vision_model': config.vision_model, 'summary_model': config.model, 'max_calls': config.max_calls,
                          'max_total_tokens': config.max_total_tokens,
                          'ocr_output_token_limit': min(config.max_output_tokens, 4096),
                          'verification_output_token_limit': min(config.max_output_tokens, 2048),
                          'verification_retry_output_token_limit': min(config.max_output_tokens, 4096),
                          'note': 'QA output-token cap applied to OCR and extraction/synthesis agents; production default is 4096. Existing QA limits retained.'}
    client = ai.make_async_client()
    from src.app.services.summary_runtime import reserve_provider_request
    client._client.event_hooks.setdefault('request', []).append(reserve_provider_request)
    blocked = None
    try:
        for row in report['documents']:
            if blocked:
                row.update(status='BLOCKED', reason=blocked)
                continue
            row['responses'] = []
            row['ocr_status'] = 'RUNNING'
            row['summary_status'] = 'NOT_RUN'
            row['status'] = 'RUNNING'
            write_report(report)
            content = (DATA / row['file']).read_bytes()
            if hashlib.sha256(content).hexdigest() != row['sha256']:
                row.update(status='FAILED', reason='Input fixture hash mismatch.')
                continue
            async def capture(**kwargs):
                response = await client.chat.completions.create(**kwargs)
                prompts = [part.get('text', '') for message in kwargs.get('messages', [])
                           for part in (message.get('content') if isinstance(message.get('content'), list) else [])
                           if isinstance(part, dict) and part.get('type') == 'text']
                label = 'verification' if 'You verify a transcription' in str(kwargs.get('messages', [{}])[0].get('content')) else 'transcription'
                row['responses'].append({'stage': label, 'request_text': prompts,
                                         'finish_reason': response.choices[0].finish_reason if response.choices else None,
                                         'content': response.choices[0].message.content if response.choices else None})
                return response
            proxy = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=capture)))
            token = _current_budget.set(WorkBudget())
            before = ai.calls
            try:
                # Verify actual parser routing before invoking the unchanged OCR pipeline.
                try:
                    DocumentTextExtractor().extract_text(content, 'application/pdf')
                    raise RuntimeError('OCR input unexpectedly has native extractable text')
                except DocumentProcessingError as exc:
                    if exc.code != 'OCR_REQUIRED':
                        raise
                settings = SimpleNamespace(ENABLE_DOCUMENT_OCR=True, DOCUMENT_OCR_MODEL=config.vision_model, DOCUMENT_VERIFICATION_MODEL=config.vision_model, LANGSMITH_TRACING='false', OPENAI_API_KEY='')
                with patch('src.app.core.settings.get_settings', return_value=settings), patch('src.app.services.document_ocr.MAX_OCR_OUTPUT_TOKENS', min(config.max_output_tokens, 4096)):
                    async with asyncio.timeout(600):
                        text = await extract_scanned_document(content, 'application/pdf', client=proxy, model=config.vision_model)
                row.update(status='REVIEW_REQUIRED', reason='OCR and application validation accepted text; source-to-transcription clinical review pending.', accepted_text=text, ocr_status='ACCEPTED')
                if SUMMARIZE:
                    row['summary_status'] = 'RUNNING'
                    write_report(report)
                    before_summary = ai.calls
                    try:
                        row['summary'] = await summarize(text, row, config, client, settings)
                        row.update(summary_status='ACCEPTED', reason='OCR and summary passed application validation; clinical review pending.')
                    finally:
                        row['summary_api_calls'] = ai.calls - before_summary
                        report['summarization_calls'] += row['summary_api_calls']
            except DocumentProcessingError as exc:
                stage = 'summary_status' if row['summary_status'] == 'RUNNING' else 'ocr_status'
                row[stage] = 'REJECTED'
                current, seen = exc, set()
                while current is not None and id(current) not in seen:
                    seen.add(id(current))
                    if hasattr(current, 'validation_issues'):
                        row.setdefault('validation_findings', []).append({'issues': current.validation_issues, 'rejected_candidate': getattr(current, 'validation_candidate', None)})
                    current = current.__cause__ or current.__context__
                if exc.code == 'MODEL_AUTH_FAILED':
                    blocked = 'OpenAI rejected the regression credentials (HTTP 401/403). Remaining calls stopped.'
                    row.update(status='BLOCKED', reason=blocked)
                    row[stage] = 'BLOCKED'
                elif ai.blocked_reason:
                    blocked = 'Regression AI budget/transport limit reached: ' + ai.blocked_reason
                    row.update(status='BLOCKED', reason=blocked)
                    row[stage] = 'BLOCKED'
                else:
                    row.update(status='REJECTED', reason='Application withheld the clinical summary.' if stage == 'summary_status' else 'Application withheld the document transcription.', error_code=exc.code, detail_code=exc.reason_code,
                               accepted_pages_before_rejection=getattr(exc, 'accepted_pages', 0))
            except Exception as exc:
                row.update(status='ERROR', reason=type(exc).__name__)
                row['summary_status' if row['summary_status'] == 'RUNNING' else 'ocr_status'] = 'ERROR'
            finally:
                _current_budget.reset(token)
                row['api_calls'] = ai.calls - before
                row['clinical_accuracy'] = 'NOT_VERIFIED'
                report['usage'] = {'calls': ai.calls, 'total_tokens': ai.total_tokens, 'events': ai.events}
                write_report(redact(report, config.api_key))
            print(row['file'], row['status'], flush=True)
    finally:
        await client.close()
        report['state'] = 'completed'
        report['assessment'] = {
            'accepted_ocr_documents': sum(row.get('ocr_status') == 'ACCEPTED' for row in report['documents']),
            'accepted_summaries': sum(row.get('summary_status') == 'ACCEPTED' for row in report['documents']),
            'scope': 'Each document stops on its first rejected page. Remaining pages are not verified. All selected cases, including rejections, remain in this report.',
            'clinical_approval': 'Pending source-to-output clinician review; model acceptance is not clinical approval.',
            'containment': 'Rejected OCR is withheld from summarization. No database access.',
        }
        report['usage'] = {'calls': ai.calls, 'total_tokens': ai.total_tokens, 'events': ai.events}
        write_report(redact(report, config.api_key))
    print('Separate clinical report:', RESULTS / 'report.html', flush=True)
    return int(any(row['status'] not in {'REVIEW_REQUIRED', 'PASS'} for row in report['documents']))


async def summarize(text, row, config, client, settings):
    from src.app.models.attachment_summarization import DocumentAttachment
    from src.app.services.document_ingestion import mark_parsed, require_parsed
    from src.app.chains.attachment_summarization import chain as chain_module
    from src.app.common import llm_factory
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
    document = DocumentAttachment(file_path='qa://' + row['file'], content_type='application/pdf',
                                  title=row['file'], resource_id='qa-document', extracted_text=text,
                                  content_sha256=row['sha256'])
    mark_parsed(document)
    require_parsed(document)
    def model_factory(*args, **kwargs):
        name = config.vision_model if args and args[0] == settings.DOCUMENT_VERIFICATION_MODEL else config.model
        return OpenAIChatModel(name, provider=OpenAIProvider(openai_client=client))
    with patch('src.app.core.settings.get_settings', return_value=settings), \
         patch.object(llm_factory, 'get_pydantic_ai_model', side_effect=model_factory), \
         patch.object(chain_module, 'get_pydantic_ai_model', side_effect=model_factory):
        chain = chain_module.AttachmentSummarizationChain()
        # Preserve prompts, schemas and validators while respecting the QA output budget.
        chain.extraction_agent.model_settings['max_tokens'] = min(config.max_output_tokens, 4096)
        chain.synthesis_agent.model_settings['max_tokens'] = min(config.max_output_tokens, 4096)
        async with asyncio.timeout(600):
            result = await chain.analyze({}, [document])
        return result.model_dump(mode='json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summarize', action='store_true', help='Run actual clinical summarization after accepted OCR.')
    parser.add_argument('--data-dir', type=Path, help='Fixture directory under qa/testdata containing manifest.json.')
    parser.add_argument('--results-dir', type=Path, help='Separate report directory under qa/results.')
    parser.add_argument('--all-samples', action='store_true', help='Run all nine public/synthetic clinical OCR samples with one shared AI budget.')
    parser.add_argument('--repeat', type=int, choices=range(1, 4), default=1, help='Repeat every selected document under one shared AI budget.')
    args = parser.parse_args()
    REPEAT = args.repeat
    ALL_SAMPLES = args.all_samples
    if ALL_SAMPLES and (args.data_dir or args.results_dir):
        parser.error('--all-samples uses fixed QA fixture and result paths.')
    SUMMARIZE = args.summarize
    if args.data_dir:
        DATA = args.data_dir.resolve()
        if not DATA.is_relative_to(ROOT / 'qa/testdata'):
            parser.error('Data directory must be under qa/testdata.')
    if SUMMARIZE:
        RESULTS = ROOT / 'qa/results/clinical_ocr_summary_live'
    if args.results_dir:
        RESULTS = args.results_dir.resolve()
        if not RESULTS.is_relative_to(ROOT / 'qa/results') or RESULTS == ROOT / 'qa/results':
            parser.error('Results must be a subdirectory of qa/results.')
    if ALL_SAMPLES:
        DATA = ROOT / 'qa/testdata'
        RESULTS = ROOT / 'qa/results/clinical_ocr_all_live'
    raise SystemExit(asyncio.run(main()))
