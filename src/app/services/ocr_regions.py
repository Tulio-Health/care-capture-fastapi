"""Supplementary overlapping region checks; publish the verified full-page text once."""
import base64
import io
from src.app.services.document_extraction import DocumentProcessingError

REGION_HEIGHT = 2200
REGION_OVERLAP = 240
MAX_REGIONS = 12


def overlapping_regions(encoded_page):
    from PIL import Image
    with Image.open(io.BytesIO(base64.b64decode(encoded_page, validate=True))) as image:
        if image.height <= REGION_HEIGHT:
            return []
        if not 0 < REGION_OVERLAP < REGION_HEIGHT:
            raise DocumentProcessingError('OCR_RENDER_LIMIT_EXCEEDED')
        images = []
        for top in range(0, image.height, REGION_HEIGHT - REGION_OVERLAP):
            if len(images) >= MAX_REGIONS:
                raise DocumentProcessingError('OCR_RENDER_LIMIT_EXCEEDED')
            bottom = min(top + REGION_HEIGHT, image.height)
            with io.BytesIO() as stream:
                image.crop((0, top, image.width, bottom)).save(stream, format='PNG')
                images.append(base64.b64encode(stream.getvalue()).decode())
            if bottom == image.height:
                break
        return images


def join_regions(region_texts):
    """Join tile transcriptions into one page text when tiling replaces the full-page call.
    Crop boundaries can cut a line (see REGION_OVERLAP), so each region contributes only its
    complete interior lines; only the first/last region keeps its outer edge, since there is
    no neighboring crop beyond it. Mirrors the interior-line trim validate_region_coverage
    already uses to compare a region against the (here, absent) full-page anchor.
    """
    lines = []
    for index, text in enumerate(region_texts):
        region_lines = [line for line in text.splitlines() if line.strip()]
        if len(region_lines) > 2:
            start = 0 if index == 0 else 1
            end = len(region_lines) if index == len(region_texts) - 1 else -1
            region_lines = region_lines[start:end]
        lines.extend(region_lines)
    return "\n".join(lines)


def validate_region_coverage(page_text, region_texts):
    """Do not splice ambiguous fragments or delete repeated clinical rows by guessing."""
    normalize = lambda value: ' '.join(value.split()).casefold()
    anchor = normalize(page_text)
    for text in region_texts:
        # Crop boundaries can cut a line; only compare complete interior lines.
        # Image verification still validates every visible crop word independently.
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        complete = lines[1:-1] if len(lines) > 2 else lines
        if any(normalize(line) not in anchor for line in complete):
            raise DocumentProcessingError('OCR_VERIFICATION_FAILED')
    return page_text
