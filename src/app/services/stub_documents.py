"""Conservative detection of stub / blank / header-only documents (parsed text carries no
clinical content) and parsed-text dedup helpers. Pure functions, no I/O."""

import re

# "Page: 1 of 1", "Page 2/3" footers/headers that make a blank PDF look non-empty.
_PAGE_MARKER_RE = re.compile(
    r"\bpage\s*:?\s*\d+\s*(?:of|/)\s*\d+\b|\[\s*page\s*\d+\s*\]", re.IGNORECASE
)
# Cerner-style printed note wrapper: the note body sits between the "Sign Information:" line and
# the "Electronically Signed" line. Nothing (or only the "could not be loaded" notice) there means
# the printout carries headers only.
_WRAPPED_BODY_RE = re.compile(
    r"Sign Information:[^\n]*\n(.*?)Electronically Signed", re.DOTALL | re.IGNORECASE
)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

# Whole-text placeholders (after normalization). Deliberately tiny: anything else is treated
# as real content, even when short.
_PLACEHOLDER_RE = re.compile(
    r"^(?:test(?:ing)?(?: (?:note|document|file|doc|data|pdf))?|sample(?: (?:note|document))?|dummy(?: (?:note|text))?"
    r"|asdf[a-z]*|qwerty[a-z]*|[asdfghjkl]{4,}|x{2,}|n a|na|none|null|nil|blank|empty|lorem ipsum.*"
    r"|no (?:content|text|data)|untitled|document|note|\d+)$"
)
# Header-only "external document" placeholders produced by the EHR export.
_UNLOADED_RE = re.compile(
    r"external document (?:could not|couldn t|cannot|can not) be (?:loaded|retrieved|displayed)"
)
_UNLOADED_MAX_CHARS = 3000


def normalize_text(text: str) -> str:
    return " ".join((text or "").split()).casefold()


def stub_reason(text: str):
    """Return a short reason string when `text` is a stub/blank/header-only document, else None."""
    stripped = _PAGE_MARKER_RE.sub(" ", text or "")
    norm = _NON_ALNUM_RE.sub(" ", stripped.casefold()).strip()
    if not norm:
        return "blank"
    if _PLACEHOLDER_RE.match(norm):
        return "placeholder"
    wrapped = _WRAPPED_BODY_RE.search(text or "")
    if wrapped and len(text) <= _UNLOADED_MAX_CHARS:
        body = _NON_ALNUM_RE.sub(
            " ", _PAGE_MARKER_RE.sub(" ", wrapped.group(1)).casefold()
        ).strip()
        if not body or _UNLOADED_RE.fullmatch(body):
            return "header_only"
    if len(text) <= _UNLOADED_MAX_CHARS and _UNLOADED_RE.search(
        _NON_ALNUM_RE.sub(" ", text.casefold()).replace("  ", " ")
    ):
        return "unloaded_external_document"
    return None
