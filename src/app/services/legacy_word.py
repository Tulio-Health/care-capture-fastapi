"""Read-only legacy Word extraction inside the bounded document parser worker."""
import io
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

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
    executable = shutil.which('antiword')
    if not executable:
        raise DocumentProcessingError('PARSER_UNAVAILABLE')
    with tempfile.TemporaryDirectory(prefix='clinical-doc-', dir=extractor._work_directory) as directory:
        source = Path(directory) / 'input.doc'
        source.write_bytes(content)
        # No shell, macros or office automation. Worker CPU/memory limits are inherited.
        with tempfile.TemporaryFile() as output:
            try:
                result = subprocess.run([executable, '-m', 'UTF-8.txt', '-w', '0', str(source)],
                                        stdin=subprocess.DEVNULL, stdout=output,
                                        stderr=subprocess.DEVNULL, timeout=20, check=False)
            except subprocess.TimeoutExpired as exc:
                raise DocumentProcessingError('PARSER_TIMEOUT') from exc
            if result.returncode:
                raise DocumentProcessingError('PARSE_FAILED')
            if output.tell() > extractor.MAX_TEXT_CHARS * 4:
                raise DocumentProcessingError('TEXT_LIMIT_EXCEEDED')
            output.seek(0)
            return extractor.validate_text(output.read().decode('utf-8', errors='strict'))
