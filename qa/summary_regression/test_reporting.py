import json
from pathlib import Path
import tempfile
import unittest
from reporting import fixture_inventory, write_report


class ReportingTests(unittest.TestCase):
    def test_fixture_integrity_and_links(self):
        inventory = fixture_inventory(Path(__file__).parent)
        self.assertTrue(inventory)
        for f in inventory.values():
            self.assertEqual(f['integrity'], 'PASS')
            self.assertTrue(f['href'].startswith('../testdata/'))

    def test_overwrite_escape_and_nonpass_health(self):
        report = dict(cases=[], counts={'BLOCKED': 1}, state='completed', planned_executions=1,
                      fixtures={}, requirements=[], run_id='<script>bad</script>', mode='mock',
                      updated_at='now', pack_case_count=476, not_selected_case_count=475,
                      scope='memory', application_adapter='adapter', ai=None)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            write_report(path, report)
            html = (path / 'report.html').read_text()
            self.assertNotIn('<script>bad</script>', html)
            self.assertIn('&lt;script&gt;bad', html)
            self.assertIn('NOT CLEAR', html)
            report['run_id'] = 'second'
            write_report(path, report)
            self.assertEqual(json.loads((path / 'report.json').read_text())['run_id'], 'second')
            self.assertEqual(sorted(p.name for p in path.iterdir()), ['report.html', 'report.json'])

class OutcomeDimensionTests(unittest.TestCase):
    def rejected(self):
        return {'outcome': 'unavailable', 'rejected_candidates': [{'clinical_summary': 'Unsupported claim'}],
                'pipeline_output': {'summary': None},
                'display': {'kind': 'unavailable', 'template_used': True, 'text': 'Summary unavailable.'},
                'persistence': {'boundary_payload': {
                    'summaryText': 'Summary unavailable.', 'keyPoints': [], 'medications': [],
                    'diagnoses': [], 'instructions': [], 'recommendations': [],
                    'data': {'procedures_mentioned': [], 'follow_up': []},
                    'summaryMetadata': {'is_clinical_summary': False, 'lab_results': [], 'risk_factors': []}}}}

    def test_rejection_can_pass_safety_without_producing_summary(self):
        from outcome_assessment import assess_outcomes
        result = assess_outcomes(self.rejected())
        self.assertEqual(result['safety_containment']['status'], 'PASS')
        self.assertEqual(result['summary_generation']['status'], 'NOT_PRODUCED')

    def test_missing_publication_evidence_is_not_a_safety_pass(self):
        from outcome_assessment import assess_outcomes
        observed = self.rejected()
        del observed['persistence']
        self.assertEqual(assess_outcomes(observed)['safety_containment']['status'], 'NOT_ASSESSED')

    def test_clinical_content_in_failure_payload_is_not_a_safety_pass(self):
        from outcome_assessment import assess_outcomes
        for field in ('diagnoses', 'medications', 'recommendations'):
            with self.subTest(field=field):
                observed = self.rejected()
                observed['persistence']['boundary_payload'][field] = ['Unsupported claim']
                self.assertEqual(assess_outcomes(observed)['safety_containment']['status'], 'NOT_ASSESSED')

    def test_produced_summary_does_not_imply_clinical_accuracy(self):
        from outcome_assessment import assess_outcomes
        result = assess_outcomes({'outcome': 'complete', 'pipeline_output': {'summary': {'clinical_summary': 'Some claim'}}})
        self.assertEqual(result['summary_generation']['status'], 'PRODUCED')
        self.assertEqual(result['safety_containment']['status'], 'NOT_ASSESSED')

    def test_expected_rejection_passes_but_required_summary_fails(self):
        from run_pack import evaluate
        observed = self.rejected()
        negative = {'expected': [{'path': 'outcome', 'op': 'eq', 'value': 'unavailable'}], 'manual_review': []}
        positive = {'expected': [{'path': 'outcome', 'op': 'eq', 'value': 'complete'}], 'manual_review': []}
        self.assertEqual(evaluate(negative, observed)[0], 'PASS')
        self.assertEqual(evaluate(positive, observed)[0], 'FAIL')

    def test_safe_rejection_has_own_label_and_preserves_failed_availability_check(self):
        from outcome_assessment import classify_contained_result
        row = {'status': 'FAIL', 'failures': [{'check': {'path': 'pipeline_output.summary', 'op': 'present', 'value': True}, 'actual': None}]}
        classify_contained_result(row, self.rejected())
        self.assertEqual(row['status'], 'SAFELY_REJECTED')
        self.assertEqual(row['assertion_status'], 'FAIL')
        self.assertEqual(len(row['failures']), 1)

    def test_unrelated_failed_assertion_cannot_be_relabelled_as_safe_rejection(self):
        from outcome_assessment import classify_contained_result
        row = {'status': 'FAIL', 'failures': [{'check': {'path': 'boundary.raw_content_forwarded', 'op': 'eq', 'value': False}, 'actual': True}]}
        classify_contained_result(row, self.rejected())
        self.assertEqual(row['status'], 'FAIL')
