"""Inspection-only legacy Word (.doc) classification: OLE2 structure is validated to
produce a precise error taxonomy, but no text is ever extracted. Legacy .doc parsing
fails closed -- see UNSUPPORTED_LEGACY_OFFICE."""
import io
import struct

from src.app.services.document_extraction import DocumentProcessingError


def extract_legacy_word(extractor, content):
    import olefile
    try:
        with olefile.OleFileIO(io.BytesIO(content), raise_defects=olefile.DEFECT_INCORRECT) as ole:
            names = ole.listdir()
            if not ole.exists('WordDocument'):
                raise DocumentProcessingError('UNSUPPORTED_FORMAT')
            if any(part.casefold() in {'vba', 'macros', 'objectpool'} for name in names for part in name):
                raise DocumentProcessingError('UNSUPPORTED_EMBEDDED_CONTENT')
            header = ole.openstream('WordDocument').read(32)
            if len(header) != 32 or struct.unpack_from('<H', header)[0] != 0xA5EC:
                raise DocumentProcessingError('PARSE_FAILED')
            # MS-DOC FibBase: encrypted bit 8; picture bit 3. Never silently drop pictures.
            # https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-doc/26fb6c06-4e5c-4778-ab4e-edbf26a545bb
            flags = struct.unpack_from('<H', header, 10)[0]
            if flags & 0x0100:
                raise DocumentProcessingError('PASSWORD_PROTECTED')
            if flags & 0x0008 or any(name[0].casefold() in {'pictures', 'data'} and ole.get_size(name) for name in names):
                raise DocumentProcessingError('UNSUPPORTED_EMBEDDED_CONTENT')
    except DocumentProcessingError:
        raise
    except (OSError, ValueError, struct.error) as exc:
        raise DocumentProcessingError('PARSE_FAILED') from exc
    # Legacy .doc text extraction is unsupported: no real-world document in the prod
    # corpus survey (0/663) was application/msword, and antiword required writing PHI
    # to disk and shelling out to an unsandboxed subprocess. Fail closed instead.
    raise DocumentProcessingError('UNSUPPORTED_LEGACY_OFFICE')
