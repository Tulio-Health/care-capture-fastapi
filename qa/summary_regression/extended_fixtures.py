"""Additional synthetic formats and edge cases for the full plan coverage matrix."""
from io import BytesIO
import base64
import gzip
import json
import struct
import wave


def build(put, jsonfile, archive, base):
    for name,codec,bom,mime in [
        ('text_utf32le.txt','utf-32le',b'\xff\xfe\0\0','text/plain'),
        ('text_utf32be.txt','utf-32be',b'\0\0\xfe\xff','text/plain'),
        ('text_utf16_no_bom.txt','utf-16le',b'','text/plain; charset=utf-16le'),
        ('text_latin1.txt','iso-8859-1',b'','text/plain; charset=iso-8859-1')]:
        put(name,bom+(base+'Dose symbol: 5 µg.\n').encode(codec),mime,'Additional explicit encoding/BOM fixture')
    put('rtf_uc_rules.rtf',r'{\rtf1\ansi SYNTHETIC QA\par \uc0 Dose: 5 \u181g.\par \uc2 Dose: 5 \u181??g.\par {\*\qaunknown HIDDEN_FAKE_DIAGNOSIS} Ultrasound ordered.}','application/rtf','RTF fallback-count rules and ignorable vendor destination')
    put('clinical.xhtml','<?xml version="1.0" encoding="UTF-8"?><html xmlns="http://www.w3.org/1999/xhtml"><body><h1>SYNTHETIC QA</h1><p>Iron deficiency anemia.</p><p>Ultrasound ordered; not performed.</p></body></html>','application/xhtml+xml','XHTML parser and MIME parameters')
    for name,text,codec,mime in [
        ('html_cp1252.html','<html><head><meta charset="windows-1252"></head><body>SYNTHETIC QA Patient’s note: no dizziness.</body></html>','cp1252','text/html; charset=windows-1252'),
        ('html_encoding_conflict.html','<html><head><meta charset="windows-1252"></head><body>SYNTHETIC QA Patient’s note.</body></html>','cp1252','text/html; charset=utf-8'),
        ('xml_cp1252.xml','<?xml version="1.0" encoding="windows-1252"?><report>SYNTHETIC QA Patient’s note: ultrasound ordered.</report>','cp1252','application/xml'),
        ('xml_utf16.xml','<?xml version="1.0" encoding="UTF-16"?><report>SYNTHETIC QA Iron deficiency anemia.</report>','utf-16','application/xml'),
        ('xml_decl_conflict.xml','<?xml version="1.0" encoding="UTF-8"?><report>SYNTHETIC QA Patient’s note.</report>','cp1252','application/xml; charset=utf-8'),
        ('text_controls.txt','SYNTHETIC QA\x00\x01\x02Dose: 5 mg','utf-8','text/plain'),
        ('text_replacements.txt','SYNTHETIC QA\nDose: 3\ufffd5 mg','utf-8','text/plain'),
    ]: put(name,text.encode(codec),mime,'Encoding and text-quality evidence')
    put('xml_internal_entity.xml','<!DOCTYPE x [<!ENTITY a "QA"><!ENTITY b "&a;&a;&a;&a;">]><x>&b;</x>','application/xml','Small safe entity expansion; parser should disable DTD entities')
    put('active_content.html','<html><head><style>.x{display:none}</style><script>FAKE_DIAGNOSIS_FROM_SCRIPT</script></head><body><h1>SYNTHETIC QA</h1><p>Iron deficiency anemia.</p><p>Ultrasound ordered.</p></body></html>','text/html','Script/style exclusion without execution')
    put('clinical.csv','Test,Value,Unit\nFerritin,8,ng/mL\nHemoglobin,10.2,g/dL\n','text/csv','Unsupported unless CSV adapter explicitly enabled; no text wildcard fallback')
    put('mime_richtext.txt','<bold>SYNTHETIC QA</bold><nl>Ultrasound ordered.','text/richtext','MIME richtext is not Microsoft RTF')
    put('mime_enriched.txt','<bold>SYNTHETIC QA</bold>\n\nUltrasound ordered.','text/enriched','MIME enriched is not Microsoft RTF')
    put('clinical.json',json.dumps({'synthetic':True,'assessment':'Iron deficiency anemia','ultrasound_status':'ordered'}),'application/json','Generic JSON is not implicitly clinical text')
    resource={'resourceType':'DocumentReference','id':'qa-docref','status':'current','description':'SYNTHETIC QA','content':[{'attachment':{'contentType':'text/plain; charset=utf-8','data':base64.b64encode(base.encode()).decode()}}]}
    put('fhir_document.json',json.dumps(resource),'application/fhir+json','FHIR resource with base64 embedded attachment')
    put('fhir_document.xml','<DocumentReference xmlns="http://hl7.org/fhir"><id value="qa-docref"/><status value="current"/><content><attachment><contentType value="text/plain; charset=utf-8"/><data value="'+base64.b64encode(base.encode()).decode()+'"/></attachment></content></DocumentReference>','application/fhir+xml','FHIR XML attachment decoding')
    second={'resourceType':'Observation','id':'qa-observation','status':'final','code':{'text':'SYNTHETIC QA Ferritin'},'valueQuantity':{'value':8,'unit':'ng/mL'}}
    put('fhir_export.ndjson',json.dumps(resource)+'\r\n'+json.dumps(second)+'\r\n','application/fhir+ndjson','Two streaming resources; CRLF delimiters')
    put('fhir_truncated.ndjson',json.dumps(resource)+'\n{"resourceType":','application/fhir+ndjson','Valid first resource and malformed last line')
    bad=dict(resource); bad['content']=[{'attachment':{'contentType':'application/rtf','data':'!!!not-base64!!!'}}]
    put('fhir_invalid_base64.json',json.dumps(bad),'application/fhir+json','Invalid transport encoding must not reach parser/model')
    put('clinical.txt.gz',gzip.compress(base.encode(),mtime=0),'application/gzip','Approved compression container')
    put('export.zip',archive({'clinical.txt':base,'manifest.json':json.dumps({'documents':['clinical.txt']})}),'application/zip','Approved archive path only')
    put('nested.zip',archive({'inner.zip':archive({'clinical.txt':base})}),'application/zip','Nested archive depth policy')
    put('many_entries.zip',archive({f'qa-{i}.txt':'SYNTHETIC QA' for i in range(8)}),'application/zip','Entry-count limit with low configured ceiling')
    put('dicom_header.dcm',b'\0'*128+b'DICM'+b'SYNTHETIC_QA_HEADER_ONLY','application/dicom','Negative routing fixture; not a diagnostic image or complete DICOM')
    out=BytesIO()
    with wave.open(out,'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000);w.writeframes(b'\0\0'*800)
    put('silent.wav',out.getvalue(),'audio/wav','Audio must not enter document text fallback')
    put('video_header.mp4',struct.pack('>I',24)+b'ftypisom'+b'\0'*12,'video/mp4','Negative routing only; truncated video header')
    put('executable_header.bin',b'MZ'+b'SYNTHETIC_QA_NONEXECUTABLE_HEADER','application/x-msdownload','Inert executable-signature rejection')
    put('polyglot_header.bin',b'%PDF-1.7\n{\\rtf1 SYNTHETIC QA conflicting format markers}', 'application/octet-stream','Suspicious conflicting markers; no supported successful extraction')
    put('clinical_fidelity.txt','SYNTHETIC QA\nRight knee pain, not left.\nDose: 0.5 mg, not 5 mg.\nTemperature: 37.5 C.\nVitamin B12: 180 pg/mL.\nFollow-up: 2026-10-01.\nNo evidence of fracture.\nPrescription status: stopped.\n','text/plain','Decimals, units, laterality, dates, negation')
    put('conflicting_doses.txt','SYNTHETIC QA\n2026-09-01: Medication Q 5 mg daily.\n2026-09-08: Medication Q 10 mg daily.\nUndated note: Medication Q 20 mg daily.\n','text/plain','Dated versus undated dose conflict; preserve provenance')
    put('multiple_patients.txt','SYNTHETIC QA\nPatient QA Example 001: Ultrasound ordered.\nPatient QA Example 002: Ultrasound performed.\n','text/plain','Identity conflict; never attribute second patient procedure to first')
    put('duplicate_sections.txt','SYNTHETIC QA\nAssessment: Iron deficiency anemia.\nCopied prior assessment: Iron deficiency anemia.\nPlan: Return in 2 weeks.\n','text/plain','Equivalent fact deduplication')
    jsonfile('conflicting_procedure_reports.json',{'reports':[{'document_id':'doc-a','date':'2026-09-08','procedure':'ECG','outcome':'normal','followup':'Return in 2 weeks.'},{'document_id':'doc-b','date':'2026-09-08','procedure':'ECG','outcome':'abnormal','followup':'Repeat ECG tomorrow.'}]},'Conflicting outcomes must retain provenance or be withheld')
    jsonfile('rich_prior_state.json',{'summary':{'id':'00000000-0000-0000-0000-000000000010','created_by':'00000000-0000-0000-0000-000000000002','summary_text':'SYNTHETIC QA summary','key_points':['Iron deficiency anemia'],'diagnoses':['Iron deficiency anemia'],'medications':[{'name':'Medication Q','dose':'5 mg'}],'data':{'qa':'preserve','follow_up':'2 weeks'},'summary_metadata':{'source':'attachment_summary','unrelated':'preserve'}}},'Full cache mapping oracle')
    jsonfile('translation_adversarial.json',{'source':{'medications':[{'name':'A','dose':5},{'name':'B','dose':10}],'active':False,'summary_text':'No fracture. Right knee. Follow-up 2026-10-01.'},'reordered':[{'name':'B','dose':5},{'name':'A','dose':10}],'wrong_type':{'active':'false'},'empty_narrative':'','wrong_date':'Follow-up 2026-01-10.','wrong_status':'Medication continued.','wrong_laterality':'Left knee.'},'Translation correspondence/empty/type/prose edge cases')
    # Derived common image formats: fixture generation only.
    from PIL import Image
    source=Image.open(BytesIO(__import__('pathlib').Path(__file__).resolve().parent.parent.joinpath('testdata/scan_page1.png').read_bytes()))
    for name,fmt,mime in [('scan_page1.bmp','BMP','image/bmp'),('scan_page1.gif','GIF','image/gif')]:
        out=BytesIO();source.resize((612,792)).save(out,format=fmt);put(name,out.getvalue(),mime,'Disabled converter routing unless explicitly enabled')
    out=BytesIO();source.resize((612,792)).save(out,format='GIF',save_all=True,append_images=[source.resize((612,792)).rotate(180)],duration=200,loop=0)
    put('scan_animated.gif',out.getvalue(),'image/gif','Two animation frames; do not silently process first frame only')
    put('heic_header.heic',struct.pack('>I',24)+b'ftypheic'+b'\0'*12,'image/heic','Negative routing only; not a complete HEIC image')
    # MIME multipart is a transport envelope, not a file MIME alias.
    multipart=('MIME-Version: 1.0\r\nContent-Type: multipart/mixed; boundary="qa-boundary"\r\n\r\n--qa-boundary\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Transfer-Encoding: base64\r\n\r\n'+base64.b64encode(base.encode()).decode()+'\r\n--qa-boundary--\r\n')
    put('multipart.eml',multipart,'multipart/mixed; boundary="qa-boundary"','Explicit transport decoding only; not raw summarization')
