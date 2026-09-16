"""Create small clinical OCR controls plus an unchanged public handwriting example."""
from pathlib import Path
import hashlib
import json
import httpx
import fitz
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'qa/testdata/clinical_ocr_positive'
DATA = OUT / 'ocr'
SOURCE = 'https://raw.githubusercontent.com/ShubhamRaorane/Handwritten-Prescription-Medicine-Recognition/master/PrescriptionDetection/static/uploadedFiles/demo.jpeg'
CASES = {
    'clear_visit_note': [
        'SYNTHETIC CLINICAL TEST DOCUMENT',
        'Visit note',
        'Patient: Test Patient A',
        'Visit date: 2026-09-01',
        'Chief complaint: Cough for three days.',
        'No fever. No shortness of breath.',
        'Assessment: Viral upper respiratory infection.',
        'Plan: Rest and oral fluids.',
        'Chest X-ray ordered. Not yet performed.',
        'Follow up in one week.'
    ],
    'clear_lab_report': [
        'SYNTHETIC CLINICAL TEST DOCUMENT',
        'Laboratory report',
        'Patient: Test Patient B',
        'Specimen collected: 2026-09-02',
        'Hemoglobin: 13.5 g/dL. Reference range: 12.0-16.0 g/dL.',
        'Sodium: 140 mmol/L. Reference range: 135-145 mmol/L.',
        'Potassium: 4.2 mmol/L. Reference range: 3.5-5.0 mmol/L.',
        'Report status: Final.'
    ],
}

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def build():
    DATA.mkdir(parents=True, exist_ok=True)
    rows=[]
    for name, lines in CASES.items():
        original=OUT/(name+'.pdf')
        c=canvas.Canvas(str(original),pagesize=letter)
        c.setFont('Helvetica',13)
        for i,line in enumerate(lines): c.drawString(42,740-i*32,line)
        c.save()
        source=fitz.open(original); page=source[0]
        raster=page.get_pixmap(dpi=180)
        result=fitz.open(); result.new_page(width=page.rect.width,height=page.rect.height).insert_image(page.rect,stream=raster.tobytes('png'))
        target=DATA/(name+'_ocr.pdf');result.save(target,deflate=True)
        rows.append(dict(file=target.name,original='../'+original.name,source_url='Locally authored synthetic control',
                         fixture_kind='synthetic printed clinical document',reference_text='\n'.join(lines),
                         expected='Preserve stated facts, values, units, negation and ordered/not-performed status. Invent no diagnosis, medication or procedure.',
                         pages=1,sha256=digest(target),original_sha256=digest(original)))
    original=OUT/'public_handwritten_prescription.jpeg'
    response=httpx.get(SOURCE,follow_redirects=True,timeout=30);response.raise_for_status();original.write_bytes(response.content)
    img=fitz.open(original); pdf=fitz.open('pdf',img.convert_to_pdf());target=DATA/'public_handwritten_prescription_ocr.pdf';pdf.save(target,deflate=True)
    rows.append(dict(file=target.name,original='../'+original.name,source_url=SOURCE,
                     fixture_kind='public pen-written prescription demonstration; not a complete visit note',
                     expected='Preserve both handwritten blocks and differing Mixtard quantities. Do not infer frequency, dose units, medication status, diagnosis or performed procedures from x1/x2.',
                     reference_text='Visual reference: two handwritten blocks dated 15/04/20, each labelled Doctor XYZ. First: Aciloc x2, Norvasc x1, Mixtard x2. Second: Aciloc x2, Norvasc x1, Mixtard x1. This manual reading is for review only, not passed to any model.',
                     pages=1,sha256=digest(target),original_sha256=digest(original)))
    for row in rows:
        doc=fitz.open(DATA/row['file']);assert all(not page.get_text().strip() for page in doc)
        row['native_text_characters']=0
        doc[0].get_pixmap(dpi=90).save('/tmp/'+row['file']+'.png')
    (DATA/'manifest.json').write_text(json.dumps({'documents':rows},indent=2)+'\n')
    (OUT/'README.md').write_text('''# Small clinical OCR controls

Two synthetic, clearly printed single-page clinical documents and one public pen-written prescription demonstration. All OCR PDFs contain images only, with no native text. These are positive-path candidates, not guaranteed passes; retain every outcome.

The synthetic note tests negation and ordered versus performed status. The lab report tests values, units and reference ranges. The handwriting sample tests ambiguous quantities: x1/x2 must not become invented dose instructions. It is not a full hospital visit record.

Public handwriting source: https://github.com/ShubhamRaorane/Handwritten-Prescription-Medicine-Recognition (PrescriptionDetection/static/uploadedFiles/demo.jpeg). Original image unchanged. Public availability is not a claim of unrestricted redistribution rights. Provenance and SHA-256 hashes are in ocr/manifest.json.

Reference text and expectations are QA-only: they are not supplied to the OCR or summary models. No production prompts, validators or thresholds are changed for these examples. Review source, extracted text and summary together; model acceptance is not clinical approval.

Run from the repository root:

```sh
python qa/summary_regression/run_clinical_ocr.py --summarize --data-dir qa/testdata/clinical_ocr_positive/ocr --results-dir qa/results/clinical_ocr_positive_live
```

Uses the existing qa/.env.regression.local key and limits, no database access. Results overwrite only this separate result folder. The earlier six-document rejection report is retained.
''')

if __name__=='__main__':build()
