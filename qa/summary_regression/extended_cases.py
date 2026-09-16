"""Full-plan format matrices and additional service/error/grounding scenarios."""

def add(case,eq,has,no,one,parsed,fail,partial,check):
    formats=[
      ('PDF','native.pdf','application/pdf','pdf','Iron deficiency anemia',False),
      ('RTF','clinical.rtf','application/rtf','rtf','Iron deficiency anemia',False),
      ('TEXT','clinical_utf8.txt','text/plain','text','Iron deficiency anemia',False),
      ('HTML','clinical.html','text/html','html','Iron deficiency anemia',False),
      ('XHTML','clinical.xhtml','application/xhtml+xml','html','Iron deficiency anemia',False),
      ('XML','clinical_cda.xml','application/xml','xml','Iron deficiency anemia',False),
      ('DOCX','clinical.docx','application/vnd.openxmlformats-officedocument.wordprocessingml.document','docx','Iron deficiency anemia',False),
      ('PNG','scan_page1.png','image/png','vision','Iron deficiency anemia',True),
      ('JPEG','scan_page2.jpg','image/jpeg','vision','10.2 g/dL',True),
      ('TIFF','scan_multipage.tiff','image/tiff','vision','Iron deficiency anemia',True),
      ('WEBP','scan_page1.webp','image/webp','vision','Iron deficiency anemia',True),
    ]
    for label,file,mime,adapter,text,vision in formats:
        variants=[('BASE',mime),('CASE',mime.upper()),('SPACE',' '+mime+' '),
                  ('NAME',mime+'; name="clinical document"'),
                  ('QUOTED-SEMICOLON',mime+'; name="Clinical; September"'),
                  ('PARAM-ORDER',mime+'; x-source=fasten; name="clinical"'),
                  ('UNKNOWN-PARAM',mime+'; x-qa-version=1'),
                  ('OCTET','application/octet-stream'),('ABSENT',None)]
        if label in ['RTF','TEXT','HTML','XHTML','XML']:
            variants += [('CHARSET',mime+';charset=utf-8'),('CHARSET-QUOTED',mime+'; charset="UTF-8"'),('MULTIPARAM',mime+'; name="clinical"; CHARSET="utf-8"')]
        else:
            variants += [('EXTRANEOUS-CHARSET',mime+'; charset=utf-8')]
        for variant,declared in variants:
            cfg={'declared_mime':declared,'filename':None,'vision_enabled':vision,'enabled_image_adapters':['png','jpeg','tiff','webp'],'text_without_mime_policy':'strict_readability_detection'}
            if vision: cfg['vision_response']='gold_transcription'
            case('FMT-'+label+'-'+variant,label+' MIME variant '+variant,file+(' scan_gold.json' if vision else ''),parsed(text)+[eq('extraction.adapter',adapter),eq('extraction.declared_mime_preserved',True)],config=cfg,refs=['5','6','7','8','26'] if vision else ['5','6','7','8'])
        case('FMT-'+label+'-BADPARAM',label+' malformed MIME parameter',file,fail('FORMAT_CONFLICT'),config={'declared_mime':mime+'; name="unterminated','malformed_parameter_policy':'reject'},refs=['6'])
    for label,file,mime,adapter,text in [
      ('TEXTXML','clinical_cda.xml','text/xml','xml','Iron deficiency anemia'),
      ('XPDF','native.pdf','application/x-pdf','pdf','Iron deficiency anemia'),
      ('JPG','scan_page2.jpg','image/jpg','vision','10.2 g/dL'),
      ('XTIF','scan_multipage.tiff','image/x-tiff','vision','Iron deficiency anemia')]:
        case('ALIAS-'+label,'Explicitly registered alias '+mime,file+(' scan_gold.json' if adapter=='vision' else ''),parsed(text)+[eq('extraction.adapter',adapter)],config={'declared_mime':mime+'; name="qa"','registered_aliases':{mime:adapter},'vision_enabled':adapter=='vision','vision_response':'gold_transcription'},refs=['5','6'])
    # Unsupported or disabled formats are positive tests of safe failure, not missing coverage.
    unsupported=[('DOC','legacy_ole_header.doc','application/msword'),('RICHTEXT','mime_richtext.txt','text/richtext'),('ENRICHED','mime_enriched.txt','text/enriched'),('DICOM','dicom_header.dcm','application/dicom'),('AUDIO','silent.wav','audio/wav'),('VIDEO','video_header.mp4','video/mp4'),('CSV','clinical.csv','text/csv'),('EXECUTABLE','executable_header.bin','application/x-msdownload'),('JSON','clinical.json','application/json'),('BMP','scan_page1.bmp','image/bmp'),('GIF','scan_page1.gif','image/gif'),('HEIC','heic_header.heic','image/heic'),('HEIF','heic_header.heic','image/heif'),('ANIMATED','scan_animated.gif','image/gif')]
    for label,file,mime in unsupported:
        for suffix,declared in [('BASE',mime),('PARAM',mime+'; name="qa"; x-source=cerner')]:
            case('UNSUPPORTED-'+label+'-'+suffix,'Disabled/unsupported '+label+' '+suffix,file,fail('UNSUPPORTED_FORMAT')+[eq('calls.model_total',0)],config={'declared_mime':declared,'filename':None,'disabled_adapters':[label.lower()],'format_policy':'unsupported_before_conversion'},refs=['5','9'])
    for label,file,mime in [('FHIRJSON','fhir_document.json','application/fhir+json'),('FHIRXML','fhir_document.xml','application/fhir+xml'),('NDJSON','fhir_export.ndjson','application/fhir+ndjson'),('GZIP','clinical.txt.gz','application/gzip'),('ZIP','export.zip','application/zip'),('MULTIPART','multipart.eml','multipart/mixed; boundary="qa-boundary"')]:
        case('TRANSPORT-'+label+'-OFF','Disabled '+label+' transport adapter',file,fail('UNSUPPORTED_FORMAT'),config={'declared_mime':mime,'transport_adapter_enabled':False},refs=['5','8'])
        case('TRANSPORT-'+label+'-ON','Approved '+label+' adapter unwraps content',file,[eq('boundary.raw_content_forwarded',False),has('model_input.text','Iron deficiency anemia'),eq('transport.decode_count',1)],config={'declared_mime':mime,'transport_adapter_enabled':True,'approved_container_profile':'qa-export'},refs=['5','8'],review=['Enable only if this transport adapter is in the release scope; otherwise mark BLOCKED with the disabled-path test as the required containment gate.'])
        for suffix,declared in [('PARAM',mime+'; name="QA; September"'),('CASE',mime.split(';')[0].upper()+(';' + mime.split(';',1)[1] if ';' in mime else '')),('CHARSET',mime+'; charset="UTF-8"')]:
            case('TRANSPORT-'+label+'-'+suffix,label+' transport MIME '+suffix,file,[eq('boundary.raw_content_forwarded',False),has('model_input.text','Iron deficiency anemia'),eq('transport.decode_count',1)],config={'declared_mime':declared,'transport_adapter_enabled':True,'approved_container_profile':'qa-export'},refs=['5','6','8'],review=['Conditional enabled-adapter test; not evidence that this optional transport is implemented.'])
    for suffix,file in [('UTF32LE','text_utf32le.txt'),('UTF32BE','text_utf32be.txt'),('UTF16NOBOM','text_utf16_no_bom.txt'),('LATIN1','text_latin1.txt')]:
        case('ENC-EXPLICIT-'+suffix,'Explicit encoding '+suffix,file,parsed('Iron deficiency anemia','5 µg'),config={'supported_text_encodings':['utf-8','utf-16le','utf-16be','utf-32le','utf-32be','iso-8859-1']},refs=['7'])
    case('RTF-UC-VENDOR','RTF Unicode fallback rules and hidden destination','rtf_uc_rules.rtf',parsed('Dose: 5 µg.','Ultrasound ordered')+[no('extraction.text','HIDDEN_FAKE_DIAGNOSIS'),no('extraction.text','??')],refs=['7'])
    for label,file,text in [('HTMLCP','html_cp1252.html','Patient’s note'),('XMLCP','xml_cp1252.xml','Patient’s note'),('XML16','xml_utf16.xml','Iron deficiency anemia')]:
        case('ENC-FORMAT-'+label,'Honor format encoding '+label,file,parsed(text),refs=['7'])
    for label,file,code in [('HTML','html_encoding_conflict.html','ENCODING_UNRESOLVED'),('XML','xml_decl_conflict.xml','ENCODING_UNRESOLVED'),('CONTROL','text_controls.txt','EXTRACTION_QUALITY_FAILED'),('REPLACEMENT','text_replacements.txt','EXTRACTION_QUALITY_FAILED')]:
        case('ENC-REJECT-'+label,'Reject corrupt or conflicting encoding '+label,file,fail(code),config={'encoding_conflict_policy':'reject','quality_profile':'strict_qa'},refs=['7'])
    cases=[
      ('MIME-RECURSION','Filename inference terminates','unknown.bin',[check('extraction.routing_attempts','lte',2),eq('calls.model_total',0)],{'declared_mime':'application/x-unknown','filename':'unknown.unknown'},{},['6']),
      ('MIME-POLYGLOT','Conflicting format markers not accepted','polyglot_header.bin',[eq('calls.summarization',0),eq('outcome','unavailable')],{},{},['6']),
      ('HTML-ACTIVE','Scripts/styles excluded and never executed','active_content.html',parsed('Iron deficiency anemia')+[no('extraction.text','FAKE_DIAGNOSIS_FROM_SCRIPT'),eq('calls.active_content_execution',0)],{},{},['8']),
      ('XML-DTD','Internal entity processing disabled','xml_internal_entity.xml',[eq('calls.model_total',0),eq('resources.entity_expansion_performed',False)],{},{},['8']),
      ('FHIR-BASE64','Malformed attachment base64 rejected','fhir_invalid_base64.json',[eq('calls.summarization',0),eq('outcome','unavailable')],{'transport_adapter_enabled':True},{},['5','8']),
      ('NDJSON-PARTIAL','Malformed NDJSON tail cannot be silently complete','fhir_truncated.ndjson',[eq('coverage.complete',False),one('outcome',['partial','unavailable'])],{'transport_adapter_enabled':True},{},['5','8']),
      ('GZIP-DOUBLE','HTTP and file compression decoded exactly once each','clinical.txt.gz',[eq('transport.http_decode_count',1),eq('transport.file_decode_count',1),has('model_input.text','Iron deficiency anemia')],{'transport_adapter_enabled':True},{'http_content_encoding':'gzip','wrap_fixture_in_gzip':True},['8']),
      ('ZIP-DEPTH','Archive depth cap','nested.zip',[eq('calls.summarization',0),has('error_codes','RESOURCE_LIMIT_EXCEEDED')],{'transport_adapter_enabled':True,'max_archive_depth':0},{},['8']),
      ('ZIP-ENTRIES','Archive entry-count cap','many_entries.zip',[eq('calls.summarization',0),has('error_codes','RESOURCE_LIMIT_EXCEEDED')],{'transport_adapter_enabled':True,'max_archive_entries':4},{},['8']),
      ('LIMIT-PAGES','PDF page count cap before model','native.pdf',[eq('calls.model_total',0),has('error_codes','RESOURCE_LIMIT_EXCEEDED')],{'max_pages':1},{},['8']),
      ('LIMIT-PARSER','Parser hard timeout cannot become fallback','clinical.rtf',[eq('calls.summarization',0),eq('resources.worker_terminated',True)],{'parser_timeout_ms':50},{'parser_delay_ms':1000},['8','A09']),
      ('LIMIT-MEMORY','Parser worker memory budget enforced','native.pdf',[eq('resources.limit_enforced',True),eq('calls.summarization',0)],{'worker_memory_limit_bytes':1048576},{'worker_reports_memory_exhaustion':True},['8','A09']),
      ('CANCEL-WORKER','Cancellation terminates or reaps worker','native.pdf',[eq('attempt.state','cancelled'),eq('resources.orphan_workers',0)],{},{'cancel_stage':'parsing'},['8','23']),
      ('CANCEL-COMMIT','Cancellation near save reconciles outcome','clinical_utf8.txt',[eq('persistence.commit_state_reconciled',True),eq('persistence.duplicate_rows',0)],{},{'cancel_stage':'persistence'},['A06','23']),
      ('CONTRACT-TEXT','Bare string cannot bypass typed extraction gate','clinical_utf8.txt',[eq('calls.summarization',0),eq('boundary.raw_content_forwarded',False)],{},{'extractor_returns_untyped_string':True},['9']),
      ('CONTRACT-MARKUP','Success label with raw RTF still rejected','clinical.rtf',[eq('calls.summarization',0),eq('boundary.raw_content_forwarded',False)],{},{'extractor_returns_raw_as_success':True},['9']),
      ('A02-FIELDS','All cache clinical fields round-trip','rich_prior_state.json',[eq('cache.all_clinical_fields_preserved',True),eq('cache.hit',True),eq('calls.summarization',0)],{'same_source_and_versions':True},{},['A02']),
      ('A02-SERIALIZE','Cache serialization error is not cache miss','rich_prior_state.json',[eq('cache.lookup_error_reported',True),eq('calls.summarization',0)],{},{'cache_serialization':'raise'},['A02']),
      ('A02-QUERY','Cache query error is not cache miss','rich_prior_state.json',[eq('cache.lookup_error_reported',True),eq('calls.summarization',0)],{},{'cache_query':'raise'},['A02']),
      ('A03-ALLFAILED','All acquisitions failed is not absence','connector_envelopes.json',[eq('outcome','unavailable'),eq('coverage.expected_documents',2),eq('display.kind','unavailable')],{},{'all_downloads':'failed'},['A03']),
      ('A03-PENDING','Pending acquisition explicitly represented','connector_envelopes.json',[has('error_codes','DOWNLOAD_PENDING'),eq('coverage.complete',False)],{},{'all_downloads':'pending'},['A03']),
      ('A03-MISSINGPATH','Missing object path counts as failure','connector_envelopes.json',[eq('coverage.failed_documents',1),eq('coverage.complete',False)],{},{'missing_path_document_id':'doc-b'},['A03']),
      ('A03-EXCLUDED','Intentional exclusion has reason and count','connector_envelopes.json',[eq('coverage.excluded_documents',1),eq('coverage.exclusions_have_reasons',True)],{},{'exclude_document_id':'doc-b','exclude_reason':'outside_encounter'},['A03']),
      ('A03-FHIRFALLBACK','FHIR-only result discloses unavailable attachments','fhir_document.json corrupt.pdf',partial(),{'allow_fhir_fallback':True},{},['A03']),
      ('A04-OMITTED','Model omits expected document from successful batch','clinical_utf8.txt clinical_statuses.txt',[eq('coverage.complete',False),eq('coverage.missing_model_documents',1)],{},{'model_omit_document_id':'doc-b'},['A04']),
      ('A04-DUPLICATE','Duplicate model document IDs rejected','clinical_utf8.txt',[eq('coverage.duplicate_model_ids_rejected',True)],{},{'model_duplicate_document_id':'doc-a'},['A04']),
      ('A04-UNEXPECTED','Unexpected model source ID rejected','clinical_utf8.txt',[eq('coverage.unexpected_model_ids_rejected',True)],{},{'model_add_document_id':'doc-other'},['A04']),
      ('A04-ALLFAILED','All model batches fail without empty synthesis','clinical_utf8.txt clinical_statuses.txt',[eq('outcome','unavailable'),eq('calls.final_synthesis',0)],{},{'all_model_batches':'timeout'},['A04']),
      ('A05-CONFLICT','Conflicting merged outcomes retain provenance','conflicting_procedure_reports.json',[eq('clinical.conflicts_disclosed',True),eq('clinical.arbitrary_conflict_resolution',False)],{},{},['A05']),
      ('A05-EQUIVALENT','Equivalent repeated instructions deduplicate','duplicate_sections.txt',[eq('clinical.duplicate_fact_count',0),has('display.text','2 weeks')],{},{},['A05']),
      ('A05-QUOTEPAIR','Merged follow-up keeps correct source quote','followup_a.txt followup_b.txt',[eq('clinical.followup_evidence_pairs_valid',True)],{},{},['A05']),
      ('A06-CLEANUP','Only pending tasks cancelled at timeout','clinical_utf8.txt',[eq('resources.completed_tasks_cancelled',0),eq('resources.pending_tasks_awaited',True)],{'overall_timeout_ms':50},{'task_delays_ms':{'transcript':0,'attachment_summary':200}},['A06']),
      ('A07-ARRAY','Same-length reordered translation changes associations','translation_adversarial.json',[eq('translation.accepted',False),eq('translation.original_preserved',True)],{},{'translation_response_key':'reordered'},['A07']),
      ('A07-TYPE','Boolean-string substitution rejected','translation_adversarial.json',[eq('translation.accepted',False)],{},{'translation_response_key':'wrong_type'},['A07']),
      ('A07-EMPTY','Empty translated narrative retains original','translation_adversarial.json',[eq('translation.original_preserved',True),eq('translation.limitation_disclosed',True)],{},{'translation_response_key':'empty_narrative'},['A07']),
      ('A07-METADATA','Source IDs/evidence/metadata not translated','rich_prior_state.json',[eq('translation.metadata_unchanged',True),eq('translation.evidence_ids_unchanged',True)],{'target_language':'es'},{},['A07','25']),
      ('A07-MIXED','Field fallback reports partial translation','rich_prior_state.json',[eq('translation.limitation_disclosed',True),eq('translation.valid_fields_retained',True)],{},{'translation_one_field_fails':True},['A07']),
      ('A08-PROCEDURETAIL','Procedure path processes beyond 100000 characters','long_middle_late.txt',[has('model_input.text','Repeat CBC in 2 weeks'),eq('coverage.complete',True)],{'source':'procedure_summary'},{},['A08']),
      ('A08-LONGTRANSCRIPT','Long transcript cannot bypass context gate','transcript.json',[eq('resources.all_model_calls_within_budget',True),eq('coverage.all_chunks_accounted',True)],{'repeat_segments':10000,'max_call_input_tokens':2000},{},['A08']),
      ('A09-FASTREQUEST','Slow parsing allows unrelated fast request','native.pdf',[check('resources.fast_request_latency_ms','lte',100)],{},{'parser_delay_ms':300},['A09']),
      ('A10-FIRSTWRITES','Concurrent first writes use one source identity','clinical_utf8.txt',[eq('persistence.duplicate_rows',0)],{'concurrent_attempts':2,'repository_mode':'memory'},{},['A10']),
      ('A10-PROCEDURES','Concurrent procedure batches preserve source identity','prior_state.json',[eq('persistence.duplicate_rows',0),eq('persistence.failed_source_rows_preserved',True)],{'source':'procedure_summary','concurrent_attempts':2},{'one_attempt_fails':True},['A10']),
      ('A10-ORM','ORM alignment does not issue DDL','prior_state.json',[eq('persistence.ddl_calls',0),eq('persistence.orm_allows_multiple_sources',True)],{'static_mapping_review':True},{},['A10']),
      ('A11-ADDED','New document invalidates cache','prior_state.json clinical_utf8.txt',[eq('cache.hit',False)],{'additional_document':True},{},['A11']),
      ('A11-PARTIAL','Prior partial result not reused as complete','prior_state.json',[eq('cache.hit',False)],{},{'prior_outcome':'partial'},['A11']),
      ('A11-FORCE','Explicit regeneration is source scoped','prior_state.json clinical_utf8.txt',[eq('cache.hit',False),eq('persistence.other_source_unchanged',True)],{'force_regenerate':True,'source':'attachment_summary'},{},['A11']),
      ('CLIN-LATERALITY','Laterality and decimals preserved','clinical_fidelity.txt',[eq('clinical.laterality','right'),eq('clinical.dose_mg',0.5),eq('clinical.followup_date','2026-10-01')],{},{},['25']),
      ('CLIN-CONFLICTDOSE','Conflicting doses never silently reconciled','conflicting_doses.txt',[eq('clinical.conflicts_disclosed',True),eq('clinical.arbitrary_conflict_resolution',False)],{},{},['25']),
      ('CLIN-IDENTITY','Second patient facts never assigned to first','multiple_patients.txt',[eq('clinical.cross_patient_claims',0),eq('coverage.complete',False)],{'patient_id':'qa-001'},{},['25']),
      ('CLIN-QUOTESEMANTICS','Existing quote does not validate contradictory paraphrase','clinical_utf8.txt',[eq('clinical.unsupported_claims_published',0)],{},{'model_claim':'Ultrasound was performed','model_quote':'Abdominal ultrasound ordered; not performed at this visit.'},['25']),
      ('CLIN-OFFSETS','Incorrect evidence offsets rejected','clinical_utf8.txt',[eq('clinical.invalid_evidence_accepted',False)],{},{'evidence_offset_shift':5},['25']),
      ('CLIN-NORMALIZE','Normalization must retain clinical punctuation','clinical_fidelity.txt',[has('model_input.text','0.5 mg'),has('model_input.text','not left')],{},{},['25']),
      ('CLIN-OMISSION','Required diagnosis omission measured independently','clinical_utf8.txt',[eq('clinical.omission_detected',True)],{},{'model_omit_fact':'Iron deficiency anemia'},['25']),
      ('CLIN-POSTPROCESS','Final persisted version equals validated version','clinical_utf8.txt',[eq('persistence.final_clinical_text_validated',True)],{},{'postprocess_attempts_add_claim':'Surgery performed'},['25']),
      ('VISION-CROP','Overlapping crops deduplicate without lost rows','scan_page2.jpg scan_gold.json',[eq('coverage.duplicate_regions',0),eq('coverage.complete',True)],{'vision_enabled':True,'overlap_crops':True,'vision_response':'gold_transcription'},{},['26']),
      ('VISION-COORDS','Model invented boxes not treated as exact evidence','scan_page1.png',[eq('clinical.unverified_coordinates_accepted',False)],{'vision_enabled':True},{'vision_coordinates':'invented'},['26']),
      ('VISION-BUDGET','Million context does not override output/request budgets','scanned.pdf',[eq('resources.all_model_calls_within_budget',True),eq('coverage.all_pages_accounted',True)],{'vision_enabled':True,'max_output_tokens':128,'max_images_per_call':1},{},['26']),
      ('VISION-ESCALATE','Escalation bounded and uses original page','scan_unreadable.png',[check('calls.vision','lte',2),eq('boundary.prior_guess_used_as_evidence',False)],{'vision_enabled':True,'max_vision_attempts':2},{'vision':'unreadable'},['26']),
      ('VISION-ROLLBACK','Disabling vision never restores raw forwarding','scanned.pdf',[eq('calls.summarization',0),eq('boundary.raw_content_forwarded',False)],{'vision_enabled':False},{},['26']),
      ('ERROR-STATUS','Partial outcome not inferred as complete from null error','clinical_utf8.txt corrupt.pdf',[eq('outcome','partial'),eq('attempt.reported_complete',False)],{},{'legacy_error_field':None},['23']),
      ('ERROR-UNKNOWNCOUNTS','Inventory failure leaves counts unknown','',[eq('coverage.expected_documents',None),eq('attempt.outcome','failed')],{},{'inventory':'raise'},['23']),
      ('ERROR-COVERAGE','Coverage counts reconcile','clinical_utf8.txt corrupt.pdf',[eq('coverage.manifest_reconciles',True)],{},{},['23']),
      ('ERROR-REQUEST','Invalid request distinct from model invalid output','clinical_utf8.txt',[eq('http.status',422),eq('calls.model_total',0)],{},{'invalid_request':True},['23']),
      ('ERROR-MODEL422','Invalid AI result not blamed on user request','clinical_utf8.txt',[check('http.status','gte',500),eq('http.blames_user_input',False)],{},{'model_output_validation':'raise'},['23']),
      ('ERROR-PREVIOUS','Failed refresh lifecycle separate from display provenance','prior_state.json corrupt.pdf',[eq('attempt.outcome','unavailable'),eq('display.provenance','previous_valid')],{'refresh':True},{},['23']),
      ('ERROR-UNEXPECTED','Unexpected exception safe and classified','clinical_utf8.txt model_responses.json',[has('error_codes','INTERNAL_PROCESSING_ERROR'),eq('boundary.secret_leaked',False)],{},{'unexpected_exception_key':'unsafe_error'},['23']),
      ('ERROR-CORRELATION','External correlation identifier validated','clinical_utf8.txt',[eq('errors.diagnostic_id_server_owned',True),eq('errors.external_id_sanitized',True)],{},{'external_correlation_id':'bad\r\nFORGED: '+('X'*2000)},['23']),
      ('ERROR-PERSISTRETRY','Persistence retry idempotent in memory','prior_state.json clinical_utf8.txt',[eq('persistence.duplicate_rows',0),eq('persistence.saved_once',True)],{'persistence_retry_limit':1},{'repository_error_sequence':['transient_before_commit','success']},['23']),
      ('UI-CLINICALFIELDS','Unavailable placeholder clears clinical fields','rich_prior_state.json corrupt.pdf',[eq('display.kind','unavailable'),eq('clinical.placeholder_fields_empty',True)],{},{'prior_validation':'invalid'},['24']),
      ('UI-PREFIX','Partial notice precedes clinical prose','clinical_utf8.txt corrupt.pdf',[eq('display.notice_is_prefix',True),eq('display.notice_count',1)],{},{},['24']),
      ('UI-DETERMINISTIC','Error copy does not depend on model','corrupt.pdf',[eq('calls.error_message_generation',0),eq('display.template_used',True)],{},{},['24']),
      ('UI-CONTRACT','Existing response shapes preserved','clinical_utf8.txt',[eq('http.public_contract_unchanged',True)],{},{},['24']),
      ('UI-PROCEDURELIST','Procedure success retains list response','clinical_statuses.txt',[eq('http.response_is_list',True)],{'source':'procedure_summary'},{},['24']),
      ('META-BOUNDED','Metadata bounded and excludes raw documents','clinical_utf8.txt',[eq('persistence.metadata_bounded',True),eq('persistence.raw_document_in_metadata',False)],{'max_processing_metadata_bytes':16384},{},['24','25']),
      ('MONITOR-STAGES','Metrics distinguish parse/model/coverage failures','clinical_utf8.txt corrupt.pdf',[eq('observability.stage_metrics_distinct',True),eq('boundary.secret_leaked',False)],{},{'one_model_batch_fails':True},['15','23']),
      ('ROLLOUT-NOREPROCESS','Parser deployment does not trigger historical regeneration','prior_state.json',[eq('calls.historical_regeneration',0)],{'simulate_feature_enable':True},{},['18']),
      ('ROLLOUT-NORAW','Strict-gate rollback never forwards raw markup','malformed.rtf',[eq('boundary.raw_content_forwarded',False),eq('calls.summarization',0)],{'strict_gate_rollback_requested':True},{'parser':'raise:rtf'},['18']),
    ]
    for id,title,files,expected,cfg,inject,refs in cases:
        case(id,title,files,expected,config=cfg,inject=inject,refs=refs)
    # Complete central error registry classifications.
    for code,stage,retryable in [
      ('SOURCE_INVENTORY_FAILED','inventory',True),('DOWNLOAD_PENDING','download',False),
      ('DOWNLOAD_TIMEOUT','download',True),('DOWNLOAD_UNAVAILABLE','download',True),
      ('DOCUMENT_NOT_FOUND','download',False),('DOCUMENT_ACCESS_DENIED','download',False),
      ('MODEL_RATE_LIMITED','extraction',True),('MODEL_TIMEOUT','extraction',True),
      ('MODEL_UNAVAILABLE','extraction',True),('MODEL_OUTPUT_INVALID','extraction',False),
      ('PERSISTENCE_FAILED','persistence',False),('INTERNAL_PROCESSING_ERROR','internal',False)]:
        case('POLICY-'+code,'Central policy for '+code,'clinical_utf8.txt',[has('error_codes',code),eq('errors.stage',stage),eq('errors.transient_retryable',retryable),eq('boundary.secret_leaked',False)],config={'retry_limit':1,'repair_limit':0,'persistence_retry_limit':0},inject={'dependency_error_code':code,'repeat_on_retry':True},refs=['23'],review=['transient_retryable distinguishes transient retries from a separately configured one-shot correction or idempotent persistence policy.'])
    case('POLICY-RETRYAFTER','Honor bounded provider Retry-After','clinical_utf8.txt',[eq('retry.provider_delay_honored',True),eq('retry.within_deadline',True)],config={'retry_limit':1,'overall_deadline_ms':5000},inject={'rate_limit_retry_after_ms':1000,'use_fake_clock':True},refs=['23'])
    for source in ['attachment_summary','procedure_summary','transcript']:
        case('GATE-'+source.upper(),'Shared content gate on '+source,'malformed.rtf',[eq('boundary.raw_content_forwarded',False),eq('calls.unvalidated_content_model',0)],config={'source':source},inject={'parser':'raise:rtf'},refs=['4','9','25'],review=['For transcript-only entry points, prove attachment payload rejection; do not invent attachment support solely for this case.'])

    case('GATE-METADATA-INFERENCE','Document-type metadata boundary rejects raw-body payload','clinical.rtf',[eq('classification.raw_body_rejected',True),eq('calls.document_parser',0)],config={'source':'document_type_inference'},inject={'unexpected_document_body':True},refs=['4','9','28'])

    for suffix,claim in [
        ('PRESCRIPTION','You were prescribed ferrous sulfate to help with your condition.'),
        ('LAB-INTERPRETATION','Your ferritin level was 8 ng/mL, which is low and suggests iron deficiency.'),
        ('VISIT-PURPOSE','You visited for an assessment of your health.')]:
        case('CLIN-LIVE-'+suffix,'Reject unsupported wording observed in live evaluation: '+suffix,'clinical_utf8.txt',
             [eq('outcome','unavailable'),has('error_codes','CLINICAL_EVIDENCE_FAILED'),eq('clinical.unsupported_claims_published',0)],
             inject={'narrative_append':claim},refs=['25'])
