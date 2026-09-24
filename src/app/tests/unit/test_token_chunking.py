"""Token-denominated chunk sizing: the dual char+token ceiling in _create_batches.

Covers the binding conditions from the token-based-chunking design (rounds 3-4):
- dual ceiling: a chunk boundary is wherever EITHER CHUNK_TOKEN_LIMIT or the char
  ceiling is hit FIRST (fixtures where each binds first);
- `:chunk:<offset>` suffixes are real character offsets: text[offset:offset+len] must
  equal the chunk verbatim, on every fixture including non-Latin script;
- literal "<|endoftext|>" in document text must not raise (encode_ordinary, not encode);
- encoder-unavailable fallback (_ENC = None) degrades to char-only sizing, no crash.

Fixture sizes are parametrized off the LIVE constants where they matter -- fixtures
pinned to absolute sizes sit on ch/tok boundaries and flip binding regimes when a
constant changes.
"""

import base64
import random

import pytest

from src.app.chains.attachment_summarization import chain
from src.app.models.attachment_summarization import DocumentAttachment
from src.app.services.document_ingestion import mark_parsed


def _doc(text: str, resource_id: str = "doc-1") -> DocumentAttachment:
    return mark_parsed(
        DocumentAttachment(
            file_path=f"s3://bucket/{resource_id}.txt",
            content_type="text/plain",
            title="Progress Note",
            extracted_text=text,
            resource_id=resource_id,
        )
    )


# Whitespace/layout-padded (the 13.8 ch/token class produced by PDF/plain-text
# extraction) -- the char ceiling must bind here, the token bound alone would allow
# ~165k-char chunks.
PADDED = ("Vital Signs" + " " * 40 + "\n" + " " * 60 + "BP 128/76 mmHg" + " " * 50 + "\n") * 1200

# Tag-dense CDA/XML narrative (~2.4 ch/token) -- the token bound binds here.
CDA_ROW = "<tr><td>Lisinopril 10 mg oral tablet</td><td>1 tablet daily</td><td>Active</td><td>Dr. A. Physician</td></tr>\n"
CDA = CDA_ROW * 1600

# base64-dense (~1.46 ch/token, the embedded-payload class) -- token bound binds hard.
BASE64_DENSE = base64.b64encode(random.Random(0).randbytes(60_000)).decode()

# Non-Latin multibyte script -- char-offset slicing must never corrupt it.
JAPANESE = ("\u60a3\u8005\u306f\u9ad8\u8840\u5727\u3068\uff12\u578b\u7cd6\u5c3f\u75c5\u306e"
            "\u65e2\u5f80\u304c\u3042\u308a\u3001\u672c\u65e5\u306e\u8840\u5727\u306f"
            "128/76\u3067\u5b89\u5b9a\u3057\u3066\u3044\u308b\u3002\u7d4c\u904e\u89b3\u5bdf"
            "\u3092\u7d99\u7d9a\u3059\u308b\u3002") * 900

ENDOFTEXT = ("Discharge note <|endoftext|> BP 128/76 mmHg. Continue metformin as directed. " * 1500)

_ALL_FIXTURES = {
    "padded": PADDED,
    "cda": CDA,
    "base64": BASE64_DENSE,
    "japanese": JAPANESE,
    "endoftext": ENDOFTEXT,
}

requires_encoder = pytest.mark.skipif(
    chain._ENC is None, reason="o200k_base encoder unavailable (char-only fallback active)"
)


def _chunks(text: str):
    return [batch[0] for batch in chain._create_batches([_doc(text)])]


# --- exact char offsets + exhaustive coverage, every fixture ---


@pytest.mark.parametrize("name", sorted(_ALL_FIXTURES))
def test_offsets_are_exact_and_coverage_is_exhaustive(name):
    doc = _doc(_ALL_FIXTURES[name])
    # Offsets are into the VALIDATED document text (mark_parsed applies validate_text's
    # strip to the parent before chunking ever runs) -- that is the text every
    # downstream consumer slices with these offsets.
    text = doc.extracted_text
    chunks = [batch[0] for batch in chain._create_batches([doc])]
    assert chunks, "expected at least one chunk"
    covered = bytearray(len(text))
    for chunk_doc in chunks:
        offset = int(chunk_doc.resource_id.rsplit(":chunk:", 1)[1])
        chunk = chunk_doc.extracted_text
        # The load-bearing contract: the chunk is the verbatim slice at its claimed
        # char offset (validate_quotes and the final re-validation both depend on it).
        assert chunk == text[offset:offset + len(chunk)]
        for i in range(offset, offset + len(chunk)):
            covered[i] = 1
    # Every character lands in some chunk, except boundary whitespace that
    # validate_text strips from chunk edges (never content, never interior
    # whitespace) -- identical to shipped behavior.
    assert all(covered[i] or text[i].isspace() for i in range(len(text))), (
        "every non-whitespace character of the source must land in some chunk"
    )


@pytest.mark.parametrize("name", sorted(_ALL_FIXTURES))
def test_no_chunk_exceeds_either_ceiling(name):
    for chunk_doc in _chunks(_ALL_FIXTURES[name]):
        assert len(chunk_doc.extracted_text) <= chain.CHUNK_CHAR_LIMIT
        if chain._ENC is not None:
            assert len(chain._ENC.encode_ordinary(chunk_doc.extracted_text)) <= chain.CHUNK_TOKEN_LIMIT


# --- binding order: each ceiling must be the one that binds on its fixture ---


@requires_encoder
def test_char_ceiling_binds_first_on_whitespace_padded_text(monkeypatch):
    chunks = _chunks(PADDED)
    assert len(chunks) > 1
    for chunk_doc in chunks:
        # Tokens sit far below the token bound on 13+ ch/token padded text -- the char
        # ceiling is the binding constraint (token-only sizing would emit one giant
        # ~165k-char chunk here).
        assert len(chunk_doc.extracted_text) <= chain.CHUNK_CHAR_LIMIT
        assert len(chain._ENC.encode_ordinary(chunk_doc.extracted_text)) < chain.CHUNK_TOKEN_LIMIT
    # Binding-order proof: with the encoder disabled (char-only sizing) the cut points
    # are IDENTICAL -- the token leg contributed nothing on this fixture.
    with_enc = [c.resource_id for c in chunks]
    monkeypatch.setattr(chain, "_ENC", None)
    without_enc = [c.resource_id for c in _chunks(PADDED)]
    assert with_enc == without_enc


@requires_encoder
@pytest.mark.parametrize("name", ["cda", "base64"])
def test_token_bound_binds_first_on_token_dense_text(name):
    chunks = _chunks(_ALL_FIXTURES[name])
    assert len(chunks) > 1
    for chunk_doc in chunks[:-1]:
        tokens = len(chain._ENC.encode_ordinary(chunk_doc.extracted_text))
        # Token bound binds (within one token of the limit -- the binary search finds
        # the largest end that still fits); the char ceiling is NOT what cut it.
        assert tokens <= chain.CHUNK_TOKEN_LIMIT
        assert tokens > chain.CHUNK_TOKEN_LIMIT - 10
        assert len(chunk_doc.extracted_text) < chain.CHUNK_CHAR_LIMIT


# --- <|endoftext|> literal must not raise (encode_ordinary, never encode) ---


@requires_encoder
def test_endoftext_literal_does_not_raise():
    chunks = _chunks(ENDOFTEXT)  # raises ValueError if anything calls encode()
    assert chunks
    assert any("<|endoftext|>" in c.extracted_text for c in chunks)


# --- encoder-unavailable fallback: char-only sizing, today's shipped behavior ---


def test_encoder_none_falls_back_to_char_only_sizing(monkeypatch):
    monkeypatch.setattr(chain, "_ENC", None)
    text = BASE64_DENSE  # token-dense on purpose: with _ENC=None tokens must be ignored
    chunks = _chunks(text)
    assert chunks
    covered = bytearray(len(text))
    for chunk_doc in chunks:
        offset = int(chunk_doc.resource_id.rsplit(":chunk:", 1)[1])
        chunk = chunk_doc.extracted_text
        assert len(chunk) <= chain.CHUNK_CHAR_LIMIT
        assert chunk == text[offset:offset + len(chunk)]
        for i in range(offset, offset + len(chunk)):
            covered[i] = 1
    assert all(covered)
    # Char-only sizing: every non-final chunk is cut at the char ceiling exactly.
    for chunk_doc in chunks[:-1]:
        assert len(chunk_doc.extracted_text) == chain.CHUNK_CHAR_LIMIT


# --- redundant-final-tail guard ---


def test_document_exactly_at_char_ceiling_yields_single_chunk_no_ghost_tail():
    """The pre-rewrite range() loop emitted a ghost final chunk fully contained in the
    previous chunk's span when the document length landed on a step boundary. The tail
    guard breaks instead."""
    chunks = _chunks("x" * chain.CHUNK_CHAR_LIMIT)  # 'x'*48k is ~6k tokens: char-bound
    assert len(chunks) == 1
    assert chunks[0].extracted_text == "x" * chain.CHUNK_CHAR_LIMIT
