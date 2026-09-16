"""Make image-only clinical QA PDFs from downloaded originals; no AI or database calls."""
import hashlib
import json
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1] / 'testdata' / 'web_clinical_samples'
DPI = 180
MAX_PAGES = 20


def main():
    sources = json.loads((ROOT / 'manifest.json').read_text())['samples']
    destination = ROOT / 'ocr'
    destination.mkdir(exist_ok=True)
    rows = []
    for source in sources:
        original = ROOT / source['file']
        assert hashlib.sha256(original.read_bytes()).hexdigest() == source['sha256']
        with fitz.open(original) as document:
            for start in range(0, len(document), MAX_PAGES):
                end = min(start + MAX_PAGES, len(document))
                suffix = f'_pages_{start + 1:02d}-{end:02d}' if len(document) > MAX_PAGES else ''
                filename = original.stem + suffix + '_ocr.pdf'
                with fitz.open() as scanned:
                    for page in list(document)[start:end]:
                        image = page.get_pixmap(dpi=DPI, alpha=False)
                        target = scanned.new_page(width=page.rect.width, height=page.rect.height)
                        target.insert_image(target.rect, stream=image.tobytes('png'))
                    scanned.set_metadata({'title': source['title'] + ' — image-only QA copy',
                                          'subject': 'Rasterized from a public sample PDF; not an original hospital scan.'})
                    scanned.save(destination / filename, garbage=4, deflate=True)
                with fitz.open(destination / filename) as verified:
                    assert len(verified) == end - start
                    assert all(not page.get_text().strip() and page.get_images() for page in verified)
                data = (destination / filename).read_bytes()
                rows.append({'file': filename, 'original': '../' + source['file'],
                             'source_url': source['source_url'], 'original_sha256': source['sha256'],
                             'original_pages': [start + 1, end], 'pages': end - start,
                             'raster_dpi': DPI, 'native_text_characters': 0, 'bytes': len(data),
                             'sha256': hashlib.sha256(data).hexdigest(), 'ocr_test_status': 'NOT_RUN'})
    (destination / 'manifest.json').write_text(json.dumps({'derivation': 'Image-only rasterization of public clinical sample PDFs; originals unchanged.', 'documents': rows}, indent=2) + '\n')
    lines = ['# Clinical documents requiring OCR', '',
             'These image-only PDFs were converted from the public clinical samples in the parent folder. They are not original hospital scans. Every page was verified to contain a raster image and no extractable native text. Originals remain unchanged for comparison.', '',
             'The 29-page blood-report collection is split into 20-page and 9-page files to respect the current OCR page limit. No pages were omitted. Conversion does not establish OCR accuracy; no live OCR, summary generation, or regression was run.', '',
             '| OCR document | Original pages | Pages | Original |', '|---|---|---|---|']
    for item in rows:
        lines.append(f'| [{item["file"]}]({item["file"]}) | {item["original_pages"][0]}–{item["original_pages"][1]} | {item["pages"]} | [Original]({item["original"]}) |')
    (destination / 'README.md').write_text('\n'.join(lines) + '\n')
    print(f'Created {len(rows)} image-only PDFs, {sum(item["pages"] for item in rows)} pages. All have zero native text.')


if __name__ == '__main__':
    main()
