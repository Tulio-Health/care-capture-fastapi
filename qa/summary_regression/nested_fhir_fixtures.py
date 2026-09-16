"""Synthetic nested FHIR documents, independent of model-generated output."""
import base64
import json


def build(put):
    note='Procedure scheduled; completion not documented.'
    encoded=base64.b64encode(note.encode()).decode()
    bundle={'resourceType':'Bundle','entry':[{'resource':{'resourceType':'Binary','contentType':'text/plain','data':encoded}}]}
    put('nested_bundle.json',json.dumps(bundle),'application/fhir+json','FHIR Bundle with an embedded text document.')
    xml=f'<Bundle xmlns="http://hl7.org/fhir"><entry><resource><Binary><contentType value="text/plain"/><data value="{encoded}"/></Binary></resource></entry></Bundle>'
    put('nested_bundle.xml',xml,'application/fhir+xml','FHIR XML Bundle with an embedded text document.')
    report={'resourceType':'DiagnosticReport','presentedForm':[{'contentType':'text/plain','data':encoded}]}
    put('nested_report.json',json.dumps(report),'application/fhir+json','Typed attachment nested in a DiagnosticReport.')
    xml=f'<DiagnosticReport xmlns="http://hl7.org/fhir"><presentedForm><contentType value="text/plain"/><data value="{encoded}"/></presentedForm></DiagnosticReport>'
    put('nested_report.xml',xml,'application/fhir+xml','FHIR XML typed attachment nested in a DiagnosticReport.')
    put('nested_external.json',json.dumps({'resourceType':'DiagnosticReport','presentedForm':[{'contentType':'text/plain','url':'https://example.invalid/clinical'}]}),'application/fhir+json','Unacquired remote attachment must not trigger arbitrary fetching or summarize missing content.')
