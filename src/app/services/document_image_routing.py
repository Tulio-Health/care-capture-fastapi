"""Conservative layout rules for decorative letterhead images and scanned pages."""


def pdf_page_requires_ocr(page, text):
    images = page.get_image_info()
    if not text.strip():
        # A truly blank page contributes no evidence. Vector-only pages still need OCR.
        return bool(images or page.get_drawings())
    for image in images:
        import fitz
        rectangle = fitz.Rect(image['bbox']) & page.rect
        if rectangle.is_empty:
            continue
        # Only small marginal graphics qualify as decorative letterhead/footer.
        marginal = rectangle.y1 <= page.rect.y0 + 90 or rectangle.y0 >= page.rect.y1 - 72
        if not (marginal and rectangle.width <= 108 and rectangle.height <= 54):
            return True
    return False


def docx_has_unsupported_images(root, *, marginal_part=False):
    w = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    wp = '{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}'
    # Legacy VML pictures have no supported geometry contract.
    if any(node.tag == w + 'pict' for node in root.iter()):
        return True
    body = root.find(w + 'body')
    first_paragraph = body[0] if body is not None and len(body) and body[0].tag == w + 'p' else None
    paragraphs = list(root.iter(w + 'p'))
    for paragraph in paragraphs:
        for drawing in paragraph.iter(w + 'drawing'):
            # Charts, linked images and text boxes are not decorative logo support.
            a = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
            r = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
            blips = list(drawing.iter(a + 'blip'))
            if len(blips) != 1 or not blips[0].get(r + 'embed') or blips[0].get(r + 'link'):
                return True
            extents = list(drawing.iter(wp + 'extent'))
            if not (marginal_part or paragraph is first_paragraph) or len(extents) != 1:
                return True
            try:
                width, height = int(extents[0].get('cx')), int(extents[0].get('cy'))
            except (TypeError, ValueError):
                return True
            if not (0 < width <= 1371600 and 0 < height <= 685800):
                return True
    return False


def html_image_is_decorative(attributes, *, text_seen):
    """Letterhead test for HTML, mirroring pdf_page_requires_ocr: marginal AND small.

    HTML carries no rendered geometry, so 'marginal' degrades to 'appears before any
    visible clinical text'. Unknown dimensions are treated as content, never decoration.
    """
    import re
    style = (attributes.get("style") or "").replace(" ", "").lower()

    def declared(axis):
        match = re.search(rf"(?:^|;){axis}:(\d+(?:\.\d+)?)px", style)
        raw = match.group(1) if match else (attributes.get(axis) or "").strip().lower().removesuffix("px")
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            return None

    width, height = declared("width"), declared("height")
    if width is None or height is None:
        return False                        # unknown size -> assume content
    # 144 x 72 CSS px == the 108 x 54 pt box pdf_page_requires_ocr already calls decorative.
    return text_seen is False and width <= 144 and height <= 72
