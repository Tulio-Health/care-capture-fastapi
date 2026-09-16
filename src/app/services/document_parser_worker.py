"""Private parser process. No settings, database, AWS, or model initialization."""
import json
import sys
from src.app.services.document_extraction import DocumentTextExtractor, DocumentProcessingError


def main():
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (25, 25))
        if sys.platform == "linux":
            resource.setrlimit(resource.RLIMIT_AS, (1024 ** 3, 1024 ** 3))
        policy = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
        extractor = DocumentTextExtractor(**policy.get("options", {}))
        for name, value in policy.get("limits", {}).items():
            if name in {"MAX_FILE_SIZE", "MAX_TEXT_CHARS", "MAX_PAGES", "MAX_ZIP_ENTRIES", "MAX_ARCHIVE_EXPANDED_BYTES", "MAX_ARCHIVE_DEPTH"} and type(value) is int and value >= 0:
                setattr(extractor, name, value)
                # Class-level validation is shared with the parsing seal. This
                # process is isolated, so applying limits here cannot affect peers.
                setattr(DocumentTextExtractor, name, value)
        content = sys.stdin.buffer.read(extractor.MAX_FILE_SIZE + 1)
        text = extractor.extract_text(content, sys.argv[1], sys.argv[2])
        result = {"text": text}
    except DocumentProcessingError as exc:
        result = {"error": exc.code}
    except MemoryError:
        result = {"error": "RESOURCE_LIMIT_EXCEEDED"}
    except Exception:
        result = {"error": "PARSE_FAILED"}
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
