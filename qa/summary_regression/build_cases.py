#!/usr/bin/env python3
"""Write test specifications and expected observations; does not run tests."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parent
CASES=[]

def check(path, op, value): return {'path':path,'op':op,'value':value}
def case(id, title, fixtures, expected, *, inject=None, config=None, refs=None, review=None):
    CASES.append({'id':id,'title':title,'plan_refs':refs or [id],
      'fixtures':fixtures.split() if isinstance(fixtures,str) else fixtures,
      'config':config or {},'inject':inject or {},'expected':expected,
      'manual_review':review or [],'execution_status':'not_run'})
def eq(p,v): return check(p,'eq',v)
def has(p,v): return check(p,'contains',v)
def no(p,v): return check(p,'not_contains',v)
def one(p,v): return check(p,'one_of',v)
def fail(code): return [eq('outcome','unavailable'),eq('calls.summarization',0),has('error_codes',code)]
def parsed(*terms): return [eq('extraction.status','success')]+[has('extraction.text',t) for t in terms]+[eq('boundary.raw_content_forwarded',False)]
def partial(): return [eq('outcome','partial'),has('display.text','Some documents couldn’t be processed. Important information may be missing.'),eq('coverage.complete',False)]

# Section 16: each original case ID is retained for traceability.
case('MIME-01','HTML charset parameter selects HTML parser','clinical.html',parsed('Iron deficiency anemia','Ordered; not performed')+[eq('extraction.adapter','html')],config={'declared_mime':'text/html;charset=utf-8'})
case('MIME-02','Whitespace, mixed case and quoted charset','clinical.html',parsed('Iron deficiency anemia')+[eq('extraction.adapter','html')],config={'declared_mime':' Text/HTML ; Charset="UTF-8" '})
case('MIME-03','Extensionless mislabeled RTF','clinical.rtf',parsed('Iron deficiency anemia')+[eq('extraction.adapter','rtf'),no('extraction.text','\\rtf')],config={'declared_mime':'text/plain','filename':None})
case('MIME-04','BOM-prefixed mislabeled RTF','rtf_bom_no_extension',parsed('Iron deficiency anemia')+[eq('extraction.adapter','rtf'),no('extraction.text','\\rtf')])
case('MIME-05','PDF signature under octet-stream','native.pdf',parsed('Iron deficiency anemia')+[eq('extraction.adapter','pdf'),eq('extraction.mime_mismatch',True)],config={'declared_mime':'application/octet-stream','filename':None})
case('MIME-06','Gateway HTML declared PDF','gateway_error.html',fail('FORMAT_CONFLICT'))
case('MIME-07','Unregistered text subtype','clinical_utf8.txt',fail('UNSUPPORTED_FORMAT'),config={'declared_mime':'text/x-qa-unknown','filename':None,'allow_unknown_text':False})
case('MIME-08','Generic ZIP must not use DOCX parser','generic.zip',fail('UNSUPPORTED_FORMAT')+[eq('calls.docx_parser',0)])
for suffix,file in [('UTF8','clinical_utf8.txt'),('BOM','clinical_utf8_bom.txt'),('LE','clinical_utf16le.txt'),('BE','clinical_utf16be.txt')]:
    case('ENC-01-'+suffix,'Decode '+suffix,file,parsed('Iron deficiency anemia','325 mg')+[no('extraction.text','\u0000')],refs=['ENC-01'])
case('ENC-02','Windows-1252 punctuation','clinical_cp1252.txt',parsed('Patient’s note: “No dizziness”—follow-up planned.'))
case('ENC-03','RTF hex/Unicode escapes','rtf_escapes.rtf',parsed('Patient’s dose: 5 µg.','Ultrasound ordered.'))
case('ENC-04','Invalid declared UTF-8','invalid_utf8.bin',fail('ENCODING_UNRESOLVED'))
case('ENC-05','Non-Latin clinical text','clinical_chinese.txt',parsed('缺铁性贫血','尚未进行'))
case('PARSE-01','RTF exception cannot fall back to raw text','clinical.rtf',fail('PARSE_FAILED')+[eq('boundary.raw_content_forwarded',False)],inject={'parser':'raise:rtf'})
case('PARSE-02-XML','Malformed XML','malformed.xml',fail('PARSE_FAILED'),refs=['PARSE-02'])
case('PARSE-02-HTML','Forced HTML parser failure','clinical.html',fail('PARSE_FAILED'),inject={'parser':'raise:html'},refs=['PARSE-02'])
case('PARSE-03-PASSWORD','Encrypted PDF','encrypted.pdf',fail('PASSWORD_PROTECTED'),refs=['PARSE-03'])
for suffix,file in [('PDF','corrupt.pdf'),('DOCX','corrupt.docx')]:
    case('PARSE-03-'+suffix,'Corrupt '+suffix,file,fail('PARSE_FAILED'),refs=['PARSE-03'])
case('PARSE-04','Whitespace extraction is not success','whitespace.txt',fail('NO_READABLE_TEXT'))
case('PARSE-05','Legacy OLE must not use DOCX adapter','legacy_ole_header.doc',[eq('calls.docx_parser',0),eq('calls.summarization',0),one('outcome',['unavailable'])],config={'legacy_conversion_enabled':False},review=['Fixture is a truncated OLE header, not a valid DOC. Legacy .doc support was dropped (PR-7): the parser fails closed with UNSUPPORTED_LEGACY_OFFICE for every .doc file, valid or malformed, so no positive extraction fixture is needed.'])
case('PARSE-06','CDA narrative and referral table','clinical_cda.xml',parsed('Iron deficiency anemia','Ordered; not performed'),review=['Verify heading and table associations, not only substring presence.'])
case('OCR-01','All scanned PDF pages accounted for','scanned.pdf scan_gold.json',[eq('coverage.expected_pages',2),eq('coverage.accepted_pages',2),eq('coverage.complete',True),has('extraction.text','10.2 g/dL')],config={'vision_enabled':True,'vision_response':'gold_transcription'})
case('OCR-02','Mixed native and scanned PDF','mixed.pdf scan_gold.json',[eq('coverage.accepted_pages',2),eq('coverage.duplicate_pages',0),has('extraction.text','Ferritin')],config={'vision_enabled':True,'vision_response':'gold_transcription'})
case('OCR-03','Unreadable scan produces safe failure','scan_unreadable.png',fail('EXTRACTION_QUALITY_FAILED'),inject={'vision':'unreadable'},config={'vision_enabled':True})
case('LIMIT-01','Streaming body exceeds stated length','clinical_utf8.txt',[eq('outcome','unavailable'),has('error_codes','FILE_TOO_LARGE'),check('io.bytes_read','lte',8192),eq('calls.summarization',0)],config={'max_download_bytes':4096,'read_chunk_bytes':4096},inject={'download':{'declared_length':64,'stream_repeat_fixture':1000}})
case('LIMIT-02','Bound archive expansion','bounded_expansion.zip',[eq('calls.summarization',0),eq('resources.limit_enforced',True)],config={'max_expanded_bytes':65536},review=['If archives are unsupported, reject before expansion. If conversion is enabled, enforce expansion limits.'])
case('LONG-01','Late diagnosis survives old 10000-character limit','long_middle_late.txt',[has('model_input.text','Vitamin B12 deficiency'),eq('coverage.complete',True)])
case('LONG-02','Middle and late content survive old windows','long_middle_late.txt',[has('model_input.text','Vitamin B12 deficiency'),has('model_input.text','Repeat CBC in 2 weeks'),eq('coverage.complete',True)])
case('LONG-03','One chunk fails','long_middle_late.txt',partial()+[eq('coverage.failed_chunks',1)],inject={'model_chunk_ordinal':2,'model_error':'timeout'},config={'chunk_tokens':1000,'retry_limit':0})
case('LONG-04','Job budget cannot silently truncate','long_middle_late.txt',[one('outcome',['partial','unavailable']),eq('coverage.complete',False)],config={'max_input_tokens_per_job':1000})
case('CLIN-01','Ordered is not performed','clinical_utf8.txt model_responses.json',[eq('clinical.unsupported_claims_published',0),eq('clinical.current_performed_procedures',[])],inject={'model_response_key':'fabricated_procedure'})
case('CLIN-02','Referral table retains ordered status','clinical.html',[eq('clinical.current_performed_procedures',[]),has('clinical.ordered_procedures','Abdominal ultrasound')])
case('CLIN-03','Same count but wrong procedure identity','clinical_statuses.txt model_responses.json',[eq('clinical.unsupported_claims_published',0),no('clinical.current_performed_procedures','Ultrasound')],inject={'model_response_key':'same_count_wrong_identity'})
case('CLIN-04','Historical/cancelled procedures excluded from encounter','clinical_statuses.txt',[eq('clinical.current_performed_procedures',['ECG'])])
case('CLIN-05','Ordered then performed at later encounter','clinical_utf8.txt later_completed.txt',[eq('clinical.procedure_timeline',[{'date':'2026-09-08','status':'ordered'},{'date':'2026-09-10','status':'performed'}])])
case('CLIN-06','Fabricated evidence rejected','clinical_statuses.txt model_responses.json',[eq('clinical.unsupported_claims_published',0),has('error_codes','CLINICAL_EVIDENCE_FAILED')],inject={'model_response_key':'missing_quote','repeat_on_correction':True})
case('UI-01','True empty inventory','',[eq('outcome','no_documents'),eq('calls.summarization',0),eq('display.kind','no_documents')])
case('UI-02','All documents fail','corrupt.pdf',[eq('outcome','unavailable'),eq('display.kind','unavailable'),eq('persistence.display_matches_summary_text',True),eq('clinical.unsupported_claims_published',0)])
case('UI-03','One readable and one failed document','clinical_utf8.txt corrupt.pdf',partial()+[eq('persistence.display_matches_summary_text',True)])
case('UI-04','Translated partial notice remains visible','clinical_utf8.txt corrupt.pdf',[eq('outcome','partial'),eq('display.warning_preserved',True),eq('clinical.unsupported_claims_published',0)],config={'target_language':'es'})
case('DATA-01','Failed refresh preserves last good','prior_state.json corrupt.pdf',[eq('persistence.prior_clinical_content_preserved',True),eq('display.kind','refresh_failed'),eq('display.notice_count',1)],config={'refresh':True,'repeat_attempts':2})
case('DATA-02','Invalidated old summary is not last good','prior_state.json corrupt.pdf',[eq('persistence.invalid_prior_exposed',False),eq('display.kind','unavailable')],inject={'prior_validation':'invalid'})
case('DATA-03','Procedure failure cannot delete prior rows','prior_state.json corrupt.pdf',[eq('persistence.deleted_prior_row_ids',[]),eq('persistence.prior_clinical_content_preserved',True)],config={'source':'procedure_summary'})
case('DATA-04','Older completion cannot overwrite newer attempt','prior_state.json clinical_utf8.txt',[eq('persistence.winning_attempt','new'),eq('persistence.duplicate_rows',0)],inject={'attempts':[{'id':'old','source_version':1,'complete_order':2},{'id':'new','source_version':2,'complete_order':1}]})
case('DATA-05','Source coexistence','prior_state.json clinical_utf8.txt',[eq('persistence.other_source_unchanged',True)],config={'source':'attachment_summary'})
case('SEC-01','XML entities and HTML resources are not fetched','external_entity.xml external_resource.html',[eq('calls.external_resource_fetch',0),eq('boundary.secret_leaked',False)])
case('SEC-02','Unapproved redirect cannot receive credentials','clinical_utf8.txt',[eq('calls.unapproved_fetch',0),eq('boundary.credentials_forwarded',False)],inject={'download_redirect':'https://qa.example.invalid/unapproved'},review=['Exercise FastAPI-owned fetch paths only; connector-only remediation remains outside approved scope.'])
case('SEC-03','Document prompt injection ignored','prompt_injection.txt',[eq('clinical.unsupported_claims_published',0),no('clinical.current_performed_procedures','surgery')])

# Named anomalies A01-A11 and error/persistence edge cases.
extra=[
('A01-PARTIAL','Partial procedure failure preserves failed-source rows','prior_state.json clinical_utf8.txt corrupt.pdf',[eq('persistence.failed_source_rows_preserved',True)],{'source':'procedure_summary'},{}),
('A01-EMPTY','Authoritative successful empty result may prune its own source','prior_state.json whitespace.txt',[eq('persistence.pruned_only_authoritative_sources',True)],{'source':'procedure_summary'},{'extraction_outcome':'successful_no_procedures'}),
('A02-CACHE','Valid cached row maps required created_by','prior_state.json',[eq('cache.hit',True),eq('calls.summarization',0),eq('cache.created_by_preserved',True)],{},{}),
('A03-INVENTORY','Inventory query error is not no documents','',[eq('outcome','unavailable'),has('error_codes','SOURCE_INVENTORY_FAILED'),eq('calls.summarization',0)],{}, {'inventory':'raise'}),
('A03-DOWNLOAD','Failed acquisition counted in denominator','connector_envelopes.json clinical_utf8.txt',partial()+[eq('coverage.expected_documents',2),eq('coverage.failed_documents',1)],{},{}),
('A04-BATCH','Hidden model batch failure marks partial','clinical_utf8.txt clinical_statuses.txt',partial()+[eq('coverage.failed_model_batches',1)],{}, {'model_batch_ordinal':2,'model_error':'timeout'}),
('A05-MERGE','Distinct short and long facts survive consolidation','followup_a.txt followup_b.txt',[has('display.text','2 weeks'),has('display.text','one month'),has('clinical.retained_facts','Finding A'),has('clinical.retained_facts','finding B')],{},{}),
('A06-TIMEOUT','Successful source survives aggregate timeout','clinical_utf8.txt',[eq('sources.transcript.outcome','success'),eq('sources.attachment_summary.outcome','unavailable')],{'overall_timeout_ms':50},{'task_delays_ms':{'transcript':0,'attachment_summary':200}}),
('A07-SCALARS','Translation cannot alter numbers or booleans','model_responses.json',[eq('translation.accepted',False),eq('translation.original_preserved',True)],{}, {'translation_response_key':'translated_scalars','translation_source_key':'translation_source'}),
('A07-PROSE','Translated negation/unit change rejected','clinical_statuses.txt model_responses.json',[eq('translation.accepted',False),eq('translation.original_preserved',True)],{}, {'translation_response_keys':['changed_negation','changed_unit']}),
('A08-ORDER','Transcript chronology follows timestamps','transcript.json',[eq('model_input.segment_ids',['t1','t2','t3'])],{'source':'transcript'},{}),
('A08-REDUCE','Aggregate synthesis respects token budget','long_middle_late.txt',[eq('resources.all_model_calls_within_budget',True),eq('coverage.all_chunks_accounted',True)],{'repeat_documents':12,'max_call_input_tokens':2000},{}),
('A09-IO','Slow download does not block event loop','clinical_utf8.txt',[check('resources.heartbeat_max_gap_ms','lte',100)],{}, {'download_delay_ms':300}),
('A10-SCHEMA','Multiple sources without DDL','prior_state.json',[eq('persistence.other_source_unchanged',True),eq('persistence.ddl_calls',0)],{'source':'attachment_summary'},{}),
('A11-FRESH','Unchanged source and versions reuse cache','prior_state.json',[eq('cache.hit',True),eq('calls.summarization',0)],{'same_source_and_versions':True},{}),
('A11-CHANGED','Changed source invalidates cache','prior_state.json clinical_utf8.txt',[eq('cache.hit',False),check('calls.summarization','gte',1)],{'source_checksum_changed':True},{}),
('A11-VERSION','Parser/prompt/model versions invalidate cache','prior_state.json clinical_utf8.txt',[eq('cache.hit',False)],{'processing_version_changed':True},{}),
('A11-PLACEHOLDER','Placeholder is not a valid clinical cache','prior_state.json clinical_utf8.txt',[eq('cache.hit',False)],{}, {'prior_summary_kind':'placeholder'}),
('ERR-DB','Database failure returns safe error','clinical_utf8.txt model_responses.json',[eq('http.status',503),eq('persistence.claimed_saved',False),eq('boundary.secret_leaked',False)],{}, {'persistence':'unavailable','exception_key':'unsafe_error'}),
('ERR-NONE','Procedure failure with no rows returns error without fake row','corrupt.pdf',[check('http.status','gte',400),eq('persistence.created_procedure_rows',0)],{'source':'procedure_summary'},{}),
('ERR-METADATA','Existing metadata keys preserved','prior_state.json clinical_utf8.txt',[eq('persistence.unrelated_metadata_preserved',True)],{},{}),
('ERR-RETRY','Transient rate limit retries within budget','clinical_utf8.txt',[check('calls.model_total','lte',3),eq('outcome','success')],{'retry_limit':2},{'model_error_sequence':['rate_limit','success']}),
('ERR-NORETRY','Unsupported input not repeatedly retried','unknown.bin',[eq('calls.model_total',0),eq('retry.count',0)],{},{}),
('ERR-EMPTY','Zero-byte file','empty.txt',fail('EMPTY_FILE'),{},{}),
('ERR-INVALIDJSON','Malformed model output cannot publish','clinical_utf8.txt model_responses.json',[eq('outcome','unavailable'),eq('clinical.unsupported_claims_published',0)],{'correction_limit':1},{'model_response_key':'invalid_json','repeat_on_correction':True}),
('ERR-LOG','Secrets excluded from display and ordinary logs','clinical_utf8.txt model_responses.json',[eq('boundary.secret_leaked',False),no('display.text','SECRET_QA_TOKEN'),no('logs.text','SECRET_QA_TOKEN')],{}, {'exception_key':'unsafe_error'}),
]
for id,title,files,expect,config,inject in extra:
    case(id,title,files,expect,config=config,inject=inject,refs=[id.split('-')[0],'23','24'])

# Grounding and vision extraction additions.
for id,title,expected in [
 ('GROUND-NEGATION','Negated diagnosis is not confirmed',[no('clinical.confirmed_diagnoses','pneumonia')]),
 ('GROUND-UNCERTAIN','Rule-out is not confirmed',[no('clinical.confirmed_diagnoses','malignancy')]),
 ('GROUND-FAMILY','Family history is not patient diagnosis',[no('clinical.confirmed_diagnoses','breast cancer')]),
 ('GROUND-DOSE','Missing dose is not invented',[eq('clinical.amoxicillin_dose',None)]),
 ('GROUND-STOPPED','Stopped medication not active',[no('clinical.active_medications','Metformin')]),
]: case(id,title,'clinical_statuses.txt clinical_gold.json',expected,refs=['25'])
case('GROUND-WRONGPAGE','Quote cannot cite an unknown source','clinical_utf8.txt model_responses.json',[eq('clinical.unsupported_claims_published',0)],inject={'fact_source_id':'doc-not-in-manifest'},refs=['25'])
case('GROUND-PLACEHOLDER','Failure notice must not become clinical evidence','prior_state.json',[eq('boundary.placeholder_used_as_evidence',False)],inject={'prior_summary_kind':'placeholder'},refs=['25'])
case('VISION-OFF','Scanned PDF with adapter disabled','scanned.pdf',fail('OCR_REQUIRED')+[eq('calls.vision',0)],config={'vision_enabled':False},refs=['26'])
case('VISION-REGION','Selectable footer does not hide image content','mixed_region.pdf scan_gold.json',[has('extraction.text','Iron deficiency anemia'),eq('coverage.complete',True)],config={'vision_enabled':True,'vision_response':'gold_transcription'},refs=['26'])
case('VISION-TIFF','All TIFF frames extracted','scan_multipage.tiff scan_gold.json',[eq('coverage.expected_pages',2),eq('coverage.accepted_pages',2)],config={'vision_enabled':True,'vision_response':'gold_transcription'},refs=['26'])
case('VISION-ROTATED','Rotation preserves ordered status','scan_rotated.png scan_gold.json',[has('extraction.text','not performed'),eq('clinical.current_performed_procedures',[])],config={'vision_enabled':True,'vision_response':'gold_transcription'},refs=['26'],review=['Real-model transcription evaluation required; a canned response only tests routing.'])
case('VISION-TRUNCATED','Truncated response is not complete','scanned.pdf model_responses.json',[eq('coverage.complete',False),one('outcome',['partial','unavailable'])],config={'vision_enabled':True},inject={'vision_response_key':'truncated','repeat_on_retry':True},refs=['26'])
case('VISION-PAGEID','Invented page ID rejected','scanned.pdf model_responses.json',[eq('coverage.complete',False),eq('calls.summarization',0)],config={'vision_enabled':True},inject={'vision_response_key':'invented_page'},refs=['26'])
case('VISION-CONFIDENCE','High confidence is not evidence of fidelity','scan_unreadable.png model_responses.json',fail('EXTRACTION_QUALITY_FAILED'),config={'vision_enabled':True},inject={'vision_response_key':'overconfident_wrong'},refs=['26'])
case('VISION-TIMEOUT','Vision timeout uses bounded retries','scanned.pdf',[check('calls.vision','lte',3),eq('outcome','unavailable'),has('error_codes','OCR_TIMEOUT')],config={'vision_enabled':True,'retry_limit':2},inject={'vision':'timeout_always'},refs=['26'])
case('VISION-COVERAGE','One omitted scan page detected','scanned.pdf scan_gold.json',[eq('coverage.expected_pages',2),eq('coverage.accepted_pages',1),eq('coverage.complete',False),one('outcome',['partial','unavailable'])],config={'vision_enabled':True},inject={'vision_omit_page':2},refs=['26'])
case('VISION-TABLE','Lab values retain row and unit association','scan_page2.jpg scan_gold.json',[eq('clinical.labs',[{'test':'Ferritin','value':8,'unit':'ng/mL'},{'test':'Hemoglobin','value':10.2,'unit':'g/dL'}])],config={'vision_enabled':True,'vision_response':'gold_transcription'},refs=['26'])
case('VISION-PIXELS','Decoded pixel cap before model call','scan_page1.png',[eq('calls.vision',0),has('error_codes','RESOURCE_LIMIT_EXCEEDED')],config={'vision_enabled':True,'max_decoded_pixels':1000},refs=['26'])
case('VISION-BOUNDARY','Vision inputs never bypass extraction validation','scan_page1.png scan_gold.json',[eq('boundary.raw_content_forwarded',False),eq('boundary.vision_output_validated_before_summary',True)],config={'vision_enabled':True,'vision_response':'gold_transcription'},refs=['26'])
case('VISION-REVIEW','Real-model visual fidelity evaluation','scanned.pdf mixed.pdf mixed_region.pdf scan_rotated.png scan_page1.webp scan_gold.json',[eq('evaluation.review_complete',True),eq('evaluation.thresholds_met',True)],config={'mode':'real_model_opt_in'},refs=['26'],review=['Record exact model snapshot, prompt version, images, token cost, latency and independent reviewer assessment. No live calls are made by this pack itself.','Compare actual transcription to scan_gold.json, including numbers/units/status/negation. Set thresholds before execution; do not accept self-confidence as a score.'])
case('DOCX-TABLE','Native Word table relationships','clinical.docx',parsed('Ferritin','10.2','g/dL'),refs=['25'],review=['Verify header/value/unit associations; text substring checks alone are insufficient.'])
case('SEC-ARCHIVE','Archive paths cannot escape extraction directory','path_traversal.zip',[eq('resources.files_written_outside_sandbox',0),eq('calls.summarization',0)],refs=['SEC-01','25'])

# RTF-specific transport MIME matrix. These are desired supported behaviors,
# not assertions that aliases/normalization are implemented today.
rtf_mimes = [
 ('APP','application/rtf'),
 ('TEXT','text/rtf'),
 ('ALIAS','application/x-rtf'),
 ('APP-UTF8','application/rtf; charset=utf-8'),
 ('TEXT-UTF8','text/rtf;charset=UTF-8'),
 ('CP1252','application/rtf; charset=windows-1252'),
 ('QUOTED','text/rtf; charset="windows-1252"'),
 ('CASE','Application/RTF; CHARSET="UTF-8"'),
 ('SPACE','  application/rtf  ;  charset = "utf-8"  '),
 ('MULTI','application/rtf; charset=utf-8; name="referral.rtf"'),
 ('SEMICOLON','application/rtf; name="Referral; September.rtf"; charset=utf-8'),
 ('ORDER','text/rtf; name="referral.rtf"; charset="UTF-8"'),
 ('EXTRA','application/rtf; version=1; x-source=cerner; charset=utf-8'),
 ('OCTET','application/octet-stream'),
 ('OCTET-PARAM','application/octet-stream; name="referral.rtf"'),
 ('PLAIN','text/plain'),
 ('PLAIN-PARAM','text/plain; charset=utf-8'),
 ('ALIAS-PARAM','application/x-rtf; charset="windows-1252"'),
]
for suffix,mime in rtf_mimes:
    case('RTF-MIME-'+suffix,'RTF transport: '+mime,'clinical.rtf',
         parsed('Iron deficiency anemia','not performed') + [eq('extraction.adapter','rtf'),no('extraction.text','\\rtf'),no('model_input.text','\\rtf')],
         config={'declared_mime':mime,'filename':None,'registered_rtf_aliases':['application/rtf','text/rtf','application/x-rtf']},refs=['MIME-01','MIME-02','MIME-03','25'])
case('RTF-MIME-BOM-PARAM','RTF BOM under parameterized plain text','rtf_bom_no_extension',parsed('Iron deficiency anemia')+[eq('extraction.adapter','rtf'),no('extraction.text','\\rtf')],config={'declared_mime':'text/plain; charset="utf-8"','filename':None},refs=['MIME-04'])
case('RTF-MIME-WHITESPACE','RTF signature after whitespace','rtf_leading_whitespace.rtf',parsed('Iron deficiency anemia')+[eq('extraction.adapter','rtf')],config={'filename':None},refs=['MIME-03'])
case('RTF-MIME-WRONGEXT','RTF bytes with misleading PDF filename','clinical.rtf',parsed('Iron deficiency anemia')+[eq('extraction.adapter','rtf'),eq('extraction.mime_mismatch',True)],config={'declared_mime':'application/octet-stream','filename':'wrong.pdf'},refs=['MIME-03'])
case('RTF-MIME-DUPLICATE','Conflicting duplicate charset parameters','rtf_raw_cp1252.rtf',fail('FORMAT_CONFLICT'),config={'declared_mime':'application/rtf; charset=utf-8; charset=windows-1252','parameter_conflict_policy':'reject'},refs=['ENC-04','25'])
case('RTF-MIME-BADQUOTE','Malformed quoted MIME parameter','clinical.rtf',fail('FORMAT_CONFLICT'),config={'declared_mime':'application/rtf; charset="utf-8','malformed_parameter_policy':'reject'},refs=['MIME-02','25'])
case('RTF-ENC-RAW','Preserve raw high-bit RTF byte','rtf_raw_cp1252.rtf',parsed('Patient’s note','not performed'),config={'declared_mime':'application/rtf; charset=windows-1252'},refs=['ENC-02'])
case('RTF-ENC-CONFLICT','Declared UTF-8 conflicts with RTF CP1252 bytes','rtf_raw_cp1252.rtf',fail('ENCODING_UNRESOLVED'),config={'declared_mime':'application/rtf; charset=utf-8','encoding_conflict_policy':'reject'},refs=['ENC-04'])
case('RTF-ENC-UNICODE','Signed RTF Unicode values retain non-Latin text','rtf_unicode_chinese.rtf',parsed('诊断：贫血。'),refs=['ENC-03','ENC-05'])
case('RTF-EMPTY','RTF without readable text','rtf_empty.rtf',fail('NO_READABLE_TEXT'),refs=['PARSE-04'])
case('RTF-PARSER-FAIL-PARAM','Parameterized RTF parser failure cannot fall back','clinical.rtf',fail('PARSE_FAILED')+[eq('boundary.raw_content_forwarded',False)],config={'declared_mime':'text/rtf; charset="utf-8"'},inject={'parser':'raise:rtf'},refs=['PARSE-01'])

from extended_cases import add as add_extended
add_extended(case,eq,has,no,one,parsed,fail,partial,check)

from final_review_cases import add as add_final_review
add_final_review(case,eq,has,no,one,check)

from resilience_cases import add as add_resilience
add_resilience(case,eq,has,check)

from routing_adapter import CASES as ROUTING_CASES
for identity, (test_name, fixtures, expectation) in ROUTING_CASES.items():
    review = []
    if identity == 'ACCESS-EXISTING-SERVICE':
        review = ['Trusted service path passes locally. Direct caregiver/provider grant resolution remains unresolved; verify existing deployed access flows before release.']
    if identity.startswith('PRESERVE-'):
        review = ['Memory-only publication assertions pass. PostgreSQL locking, durable commits and deployed consumer behavior are deferred to deployed-instance verification.']
    case(identity, expectation, fixtures, [eq('regression.passed', True), eq('regression.tests_run', 1), eq('persistence.database_writes', 0)], refs=['OCR/DOCX routing and compatibility review'], review=review)

from approved_scope import apply
apply(CASES)

(ROOT/'cases.json').write_text(json.dumps({'schema_version':1,'execution_status':'not_run','cases':CASES},indent=2,ensure_ascii=False)+'\n')
lines=['# Regression case matrix','','This matrix specifies scenarios; current execution results are in `../results/report.html`. Expectations describe the fixes, not the current baseline.','', '| ID | Scenario | Plan reference |','|---|---|---|']
for c in CASES: lines.append(f"| {c['id']} | {c['title']} | {', '.join(c['plan_refs'])} |")
(ROOT/'CASE_MATRIX.md').write_text('\n'.join(lines)+'\n')
rtf_lines=['# RTF MIME and encoding matrix','','This matrix specifies scenarios; current execution results are in `../results/report.html`. Parameter conflict policies are explicit test configurations. `application/x-rtf` is an approved compatibility alias in this test profile; this does not assert current implementation support.','', '| ID | Declared MIME or scenario | Expected behavior |','|---|---|---|']
for c in CASES:
    if c['id'].startswith('RTF-'):
        expectation='Controlled failure; no clinical summarization' if any(x['path']=='outcome' and x['value']=='unavailable' for x in c['expected']) else 'RTF adapter; preserved clinical text; no raw markup'
        rtf_lines.append(f"| {c['id']} | `{c['config'].get('declared_mime',c['title'])}` | {expectation} |")
(ROOT/'RTF_MIME_MATRIX.md').write_text('\n'.join(rtf_lines)+'\n')
print(f'Wrote {len(CASES)} case specifications. No application tests executed.')
