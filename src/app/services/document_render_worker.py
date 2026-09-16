"""Resource-bounded local document rendering. No external URLs or model calls."""
import base64
import io
import json
import sys
from src.app.services.document_extraction import DocumentTextExtractor, DocumentProcessingError


def render(content, *, max_decoded_pixels=20_000_000):
    if type(max_decoded_pixels) is not int or not 0 < max_decoded_pixels <= 20_000_000:
        raise DocumentProcessingError("IMAGE_PIXEL_LIMIT_EXCEEDED")
    pages = []
    if content.lstrip().startswith(b"%PDF-"):
        import fitz
        with fitz.open(stream=content, filetype="pdf") as document:
            if document.needs_pass:
                raise DocumentProcessingError("ENCRYPTED_DOCUMENT")
            if len(document) > 20:
                raise DocumentProcessingError("OCR_PAGE_LIMIT_EXCEEDED")
            for page in document:
                if page.rect.width * page.rect.height * 4 > max_decoded_pixels:
                    raise DocumentProcessingError("IMAGE_PIXEL_LIMIT_EXCEEDED")
                pixels = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                pages.append(base64.b64encode(pixels.tobytes("png")).decode())
    else:
        from PIL import Image, ImageOps
        Image.MAX_IMAGE_PIXELS = max_decoded_pixels
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in {"PNG", "JPEG", "TIFF", "GIF", "WEBP", "BMP"}:
                raise DocumentProcessingError("UNSUPPORTED_IMAGE")
            if getattr(image, "n_frames", 1) > 20:
                raise DocumentProcessingError("OCR_PAGE_LIMIT_EXCEEDED")
            for frame in range(getattr(image, "n_frames", 1)):
                image.seek(frame)
                if image.width * image.height > max_decoded_pixels:
                    raise DocumentProcessingError("IMAGE_PIXEL_LIMIT_EXCEEDED")
                with io.BytesIO() as output:
                    ImageOps.exif_transpose(image).convert("RGB").save(output, format="PNG")
                    pages.append(base64.b64encode(output.getvalue()).decode())
    if not pages or sum(map(len, pages)) > 24 * 1024 * 1024:
        raise DocumentProcessingError("OCR_RENDER_LIMIT_EXCEEDED")
    return pages


def main():
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (25, 25))
        if sys.platform == "linux":
            resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
        content = sys.stdin.buffer.read(DocumentTextExtractor.MAX_FILE_SIZE + 1)
        if len(content) > DocumentTextExtractor.MAX_FILE_SIZE:
            raise DocumentProcessingError("FILE_TOO_LARGE")
        limits = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        result = {"pages": render(content, **limits)}
    except DocumentProcessingError as exc:
        result = {"error": exc.code}
    except ImportError:
        result = {"error": "UNSUPPORTED_FORMAT"}
    except MemoryError:
        result = {"error": "RESOURCE_LIMIT_EXCEEDED"}
    except Exception as exc:
        result = {"error": "RESOURCE_LIMIT_EXCEEDED" if type(exc).__name__ == "DecompressionBombError" else "RENDER_FAILED"}
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
