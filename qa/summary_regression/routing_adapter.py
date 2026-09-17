"""Run production routing and memory-only compatibility assertions in the main report."""
import io
import unittest

CASES = {
    'ROUTING-PDF-LOGO': ('test_routing_safety.RoutingSafety.test_logo_pdf_has_zero_vision_calls', ['routing/letterhead.pdf'], 'Native PDF text retained; zero OCR/vision calls'),
    'ROUTING-DOCX-LOGO': ('test_routing_safety.RoutingSafety.test_docx_logos_preserve_native_text_and_tables_without_vision', ['routing/logo_header.docx', 'routing/logo_body.docx', 'routing/logo_footer.docx'], 'Header, first-paragraph and footer logos retain clinical text and table text; zero OCR calls'),
    'ROUTING-DOCX-IMAGE': ('test_routing_safety.RoutingSafety.test_docx_clinical_image_is_contained_without_unsupported_renderer', ['routing/clinical_image.docx'], 'Unsupported clinical image returns UNSUPPORTED_FORMAT without entering OCR renderer'),
    'ROUTING-MIXED-PDF': ('test_routing_safety.RoutingSafety.test_mixed_pdf_only_transcribes_scan_and_preserves_page_order', ['routing/mixed_scan.pdf'], 'Only scanned page transcribed; three native pages preserved in order'),
    'ROUTING-BLANK': ('test_routing_safety.RoutingSafety.test_blank_page_does_not_trigger_ocr_but_body_image_does', [], 'Blank PDF returns NO_READABLE_TEXT with no model call'),
    'ACCESS-EXISTING-SERVICE': ('test_routing_safety.AccessCompatibilitySafety.test_existing_trusted_service_delegation_does_not_require_patient_mapping', [], 'Trusted service retains existing patient delegation without new mapping lookup'),
    'ACCESS-EXISTING-PATIENT': ('test_routing_safety.AccessCompatibilitySafety.test_authenticated_patient_access_and_cross_patient_rejection', [], 'Authenticated mapped patient accepted; cross-patient request denied'),
    'PRESERVE-FAILED-REFRESH': ('test_publication_safety.PublicationSafety.test_failed_refresh_preserves_validated_summary_and_displays_notice_once', [], 'Failed refresh retains diagnosis and original summary with exactly one notice'),
    'PRESERVE-EMPTY-PARTIAL': ('test_publication_safety.PublicationSafety.test_empty_failed_procedure_refresh_preserves_all_existing_rows', [], 'Empty failed procedure refresh does not delete prior rows or clinical content'),
}


def run_case(case):
    name, _, expectation = CASES[case['id']]
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromName(name)
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    return {'regression': {'passed': result.wasSuccessful(), 'tests_run': result.testsRun,
                           'expectation': expectation, 'actual_assertions': stream.getvalue()},
            'persistence': {'mode': 'memory', 'database_writes': 0}}
