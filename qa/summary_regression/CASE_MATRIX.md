# Regression case matrix

This matrix specifies scenarios; current execution results are in `../results/report.html`. Expectations describe the fixes, not the current baseline.

| ID | Scenario | Plan reference |
|---|---|---|
| MIME-01 | HTML charset parameter selects HTML parser | MIME-01 |
| MIME-02 | Whitespace, mixed case and quoted charset | MIME-02 |
| MIME-03 | Extensionless mislabeled RTF | MIME-03 |
| MIME-04 | BOM-prefixed mislabeled RTF | MIME-04 |
| MIME-05 | PDF signature under octet-stream | MIME-05 |
| MIME-06 | Gateway HTML declared PDF | MIME-06 |
| MIME-07 | Unregistered text subtype | MIME-07 |
| MIME-08 | Generic ZIP must not use DOCX parser | MIME-08 |
| ENC-01-UTF8 | Decode UTF8 | ENC-01 |
| ENC-01-BOM | Decode BOM | ENC-01 |
| ENC-01-LE | Decode LE | ENC-01 |
| ENC-01-BE | Decode BE | ENC-01 |
| ENC-02 | Windows-1252 punctuation | ENC-02 |
| ENC-03 | RTF hex/Unicode escapes | ENC-03 |
| ENC-04 | Invalid declared UTF-8 | ENC-04 |
| ENC-05 | Non-Latin clinical text | ENC-05 |
| PARSE-01 | RTF exception cannot fall back to raw text | PARSE-01 |
| PARSE-02-XML | Malformed XML | PARSE-02 |
| PARSE-02-HTML | Forced HTML parser failure | PARSE-02 |
| PARSE-03-PASSWORD | Encrypted PDF | PARSE-03 |
| PARSE-03-PDF | Corrupt PDF | PARSE-03 |
| PARSE-03-DOCX | Corrupt DOCX | PARSE-03 |
| PARSE-04 | Whitespace extraction is not success | PARSE-04 |
| PARSE-05 | Legacy OLE must not use DOCX adapter | PARSE-05 |
| PARSE-06 | CDA narrative and referral table | PARSE-06 |
| OCR-01 | All scanned PDF pages accounted for | OCR-01 |
| OCR-02 | Mixed native and scanned PDF | OCR-02 |
| OCR-03 | Unreadable scan produces safe failure | OCR-03 |
| LIMIT-01 | Streaming body exceeds stated length | LIMIT-01 |
| LIMIT-02 | Bound archive expansion | LIMIT-02 |
| LONG-01 | Late diagnosis survives old 10000-character limit | LONG-01 |
| LONG-02 | Middle and late content survive old windows | LONG-02 |
| LONG-03 | One chunk fails | LONG-03 |
| LONG-04 | Job budget cannot silently truncate | LONG-04 |
| CLIN-01 | Ordered is not performed | CLIN-01 |
| CLIN-02 | Referral table retains ordered status | CLIN-02 |
| CLIN-03 | Same count but wrong procedure identity | CLIN-03 |
| CLIN-04 | Historical/cancelled procedures excluded from encounter | CLIN-04 |
| CLIN-05 | Ordered then performed at later encounter | CLIN-05 |
| CLIN-06 | Fabricated evidence rejected | CLIN-06 |
| UI-01 | True empty inventory | UI-01 |
| UI-02 | All documents fail | UI-02 |
| UI-03 | One readable and one failed document | UI-03 |
| UI-04 | Translated partial notice remains visible | UI-04 |
| DATA-01 | Failed refresh preserves last good | DATA-01 |
| DATA-02 | Invalidated old summary is not last good | DATA-02 |
| DATA-03 | Procedure failure cannot delete prior rows | DATA-03 |
| DATA-04 | Older completion cannot overwrite newer attempt | DATA-04 |
| DATA-05 | Source coexistence | DATA-05 |
| SEC-01 | XML entities and HTML resources are not fetched | SEC-01 |
| SEC-02 | Unapproved redirect cannot receive credentials | SEC-02 |
| SEC-03 | Document prompt injection ignored | SEC-03 |
| A01-PARTIAL | Partial procedure failure preserves failed-source rows | A01, 23, 24 |
| A01-EMPTY | Authoritative successful empty result may prune its own source | A01, 23, 24 |
| A02-CACHE | Valid cached row maps required created_by | A02, 23, 24 |
| A03-INVENTORY | Inventory query error is not no documents | A03, 23, 24 |
| A03-DOWNLOAD | Failed acquisition counted in denominator | A03, 23, 24 |
| A04-BATCH | Hidden model batch failure marks partial | A04, 23, 24 |
| A05-MERGE | Distinct short and long facts survive consolidation | A05, 23, 24 |
| A06-TIMEOUT | Successful source survives aggregate timeout | A06, 23, 24 |
| A07-SCALARS | Translation cannot alter numbers or booleans | A07, 23, 24 |
| A07-PROSE | Translated negation/unit change rejected | A07, 23, 24 |
| A08-ORDER | Transcript chronology follows timestamps | A08, 23, 24 |
| A08-REDUCE | Aggregate synthesis respects token budget | A08, 23, 24 |
| A09-IO | Slow download does not block event loop | A09, 23, 24 |
| A10-SCHEMA | Multiple sources without DDL | A10, 23, 24 |
| A11-FRESH | Unchanged source and versions reuse cache | A11, 23, 24 |
| A11-CHANGED | Changed source invalidates cache | A11, 23, 24 |
| A11-VERSION | Parser/prompt/model versions invalidate cache | A11, 23, 24 |
| A11-PLACEHOLDER | Placeholder is not a valid clinical cache | A11, 23, 24 |
| ERR-DB | Database failure returns safe error | ERR, 23, 24 |
| ERR-NONE | Procedure failure with no rows returns error without fake row | ERR, 23, 24 |
| ERR-METADATA | Existing metadata keys preserved | ERR, 23, 24 |
| ERR-RETRY | Transient rate limit retries within budget | ERR, 23, 24 |
| ERR-NORETRY | Unsupported input not repeatedly retried | ERR, 23, 24 |
| ERR-EMPTY | Zero-byte file | ERR, 23, 24 |
| ERR-INVALIDJSON | Malformed model output cannot publish | ERR, 23, 24 |
| ERR-LOG | Secrets excluded from display and ordinary logs | ERR, 23, 24 |
| GROUND-NEGATION | Negated diagnosis is not confirmed | 25 |
| GROUND-UNCERTAIN | Rule-out is not confirmed | 25 |
| GROUND-FAMILY | Family history is not patient diagnosis | 25 |
| GROUND-DOSE | Missing dose is not invented | 25 |
| GROUND-STOPPED | Stopped medication not active | 25 |
| GROUND-WRONGPAGE | Quote cannot cite an unknown source | 25 |
| GROUND-PLACEHOLDER | Failure notice must not become clinical evidence | 25 |
| VISION-OFF | Scanned PDF with adapter disabled | 26 |
| VISION-REGION | Selectable footer does not hide image content | 26 |
| VISION-TIFF | All TIFF frames extracted | 26 |
| VISION-ROTATED | Rotation preserves ordered status | 26 |
| VISION-TRUNCATED | Truncated response is not complete | 26 |
| VISION-PAGEID | Invented page ID rejected | 26 |
| VISION-CONFIDENCE | High confidence is not evidence of fidelity | 26 |
| VISION-TIMEOUT | Vision timeout uses bounded retries | 26 |
| VISION-COVERAGE | One omitted scan page detected | 26 |
| VISION-TABLE | Lab values retain row and unit association | 26 |
| VISION-PIXELS | Decoded pixel cap before model call | 26 |
| VISION-BOUNDARY | Vision inputs never bypass extraction validation | 26 |
| VISION-REVIEW | Real-model visual fidelity evaluation | 26 |
| DOCX-TABLE | Native Word table relationships | 25 |
| SEC-ARCHIVE | Archive paths cannot escape extraction directory | SEC-01, 25 |
| RTF-MIME-APP | RTF transport: application/rtf | MIME-01, MIME-02, MIME-03, 25 |
| RTF-MIME-TEXT | RTF transport: text/rtf | MIME-01, MIME-02, MIME-03, 25 |
| RTF-MIME-ALIAS | RTF transport: application/x-rtf | MIME-01, MIME-02, MIME-03, 25 |
| RTF-MIME-APP-UTF8 | RTF transport: application/rtf; charset=utf-8 | MIME-01, MIME-02, MIME-03, 25 |
| RTF-MIME-TEXT-UTF8 | RTF transport: text/rtf;charset=UTF-8 | MIME-01, MIME-02, MIME-03, 25 |
| RTF-MIME-CP1252 | RTF transport: application/rtf; charset=windows-1252 | MIME-01, MIME-02, MIME-03, 25 |
| RTF-MIME-QUOTED | RTF transport: text/rtf; charset="windows-1252" | MIME-01, MIME-02, MIME-03, 25 |
| RTF-MIME-CASE | RTF transport: Application/RTF; CHARSET="UTF-8" | MIME-01, MIME-02, MIME-03, 25 |
| RTF-MIME-SPACE | RTF transport:   application/rtf  ;  charset = "utf-8"   | MIME-01, MIME-02, MIME-03, 25 |
| RTF-MIME-MULTI | RTF transport: application/rtf; charset=utf-8; name="referral.rtf" | MIME-01, MIME-02, MIME-03, 25 |
| RTF-MIME-SEMICOLON | RTF transport: application/rtf; name="Referral; September.rtf"; charset=utf-8 | MIME-01, MIME-02, MIME-03, 25 |
| RTF-MIME-ORDER | RTF transport: text/rtf; name="referral.rtf"; charset="UTF-8" | MIME-01, MIME-02, MIME-03, 25 |
| RTF-MIME-EXTRA | RTF transport: application/rtf; version=1; x-source=cerner; charset=utf-8 | MIME-01, MIME-02, MIME-03, 25 |
| RTF-MIME-OCTET | RTF transport: application/octet-stream | MIME-01, MIME-02, MIME-03, 25 |
| RTF-MIME-OCTET-PARAM | RTF transport: application/octet-stream; name="referral.rtf" | MIME-01, MIME-02, MIME-03, 25 |
| RTF-MIME-PLAIN | RTF transport: text/plain | MIME-01, MIME-02, MIME-03, 25 |
| RTF-MIME-PLAIN-PARAM | RTF transport: text/plain; charset=utf-8 | MIME-01, MIME-02, MIME-03, 25 |
| RTF-MIME-ALIAS-PARAM | RTF transport: application/x-rtf; charset="windows-1252" | MIME-01, MIME-02, MIME-03, 25 |
| RTF-MIME-BOM-PARAM | RTF BOM under parameterized plain text | MIME-04 |
| RTF-MIME-WHITESPACE | RTF signature after whitespace | MIME-03 |
| RTF-MIME-WRONGEXT | RTF bytes with misleading PDF filename | MIME-03 |
| RTF-MIME-DUPLICATE | Conflicting duplicate charset parameters | ENC-04, 25 |
| RTF-MIME-BADQUOTE | Malformed quoted MIME parameter | MIME-02, 25 |
| RTF-ENC-RAW | Preserve raw high-bit RTF byte | ENC-02 |
| RTF-ENC-CONFLICT | Declared UTF-8 conflicts with RTF CP1252 bytes | ENC-04 |
| RTF-ENC-UNICODE | Signed RTF Unicode values retain non-Latin text | ENC-03, ENC-05 |
| RTF-EMPTY | RTF without readable text | PARSE-04 |
| RTF-PARSER-FAIL-PARAM | Parameterized RTF parser failure cannot fall back | PARSE-01 |
| FMT-PDF-BASE | PDF MIME variant BASE | 5, 6, 7, 8 |
| FMT-PDF-CASE | PDF MIME variant CASE | 5, 6, 7, 8 |
| FMT-PDF-SPACE | PDF MIME variant SPACE | 5, 6, 7, 8 |
| FMT-PDF-NAME | PDF MIME variant NAME | 5, 6, 7, 8 |
| FMT-PDF-QUOTED-SEMICOLON | PDF MIME variant QUOTED-SEMICOLON | 5, 6, 7, 8 |
| FMT-PDF-PARAM-ORDER | PDF MIME variant PARAM-ORDER | 5, 6, 7, 8 |
| FMT-PDF-UNKNOWN-PARAM | PDF MIME variant UNKNOWN-PARAM | 5, 6, 7, 8 |
| FMT-PDF-OCTET | PDF MIME variant OCTET | 5, 6, 7, 8 |
| FMT-PDF-ABSENT | PDF MIME variant ABSENT | 5, 6, 7, 8 |
| FMT-PDF-EXTRANEOUS-CHARSET | PDF MIME variant EXTRANEOUS-CHARSET | 5, 6, 7, 8 |
| FMT-PDF-BADPARAM | PDF malformed MIME parameter | 6 |
| FMT-RTF-BASE | RTF MIME variant BASE | 5, 6, 7, 8 |
| FMT-RTF-CASE | RTF MIME variant CASE | 5, 6, 7, 8 |
| FMT-RTF-SPACE | RTF MIME variant SPACE | 5, 6, 7, 8 |
| FMT-RTF-NAME | RTF MIME variant NAME | 5, 6, 7, 8 |
| FMT-RTF-QUOTED-SEMICOLON | RTF MIME variant QUOTED-SEMICOLON | 5, 6, 7, 8 |
| FMT-RTF-PARAM-ORDER | RTF MIME variant PARAM-ORDER | 5, 6, 7, 8 |
| FMT-RTF-UNKNOWN-PARAM | RTF MIME variant UNKNOWN-PARAM | 5, 6, 7, 8 |
| FMT-RTF-OCTET | RTF MIME variant OCTET | 5, 6, 7, 8 |
| FMT-RTF-ABSENT | RTF MIME variant ABSENT | 5, 6, 7, 8 |
| FMT-RTF-CHARSET | RTF MIME variant CHARSET | 5, 6, 7, 8 |
| FMT-RTF-CHARSET-QUOTED | RTF MIME variant CHARSET-QUOTED | 5, 6, 7, 8 |
| FMT-RTF-MULTIPARAM | RTF MIME variant MULTIPARAM | 5, 6, 7, 8 |
| FMT-RTF-BADPARAM | RTF malformed MIME parameter | 6 |
| FMT-TEXT-BASE | TEXT MIME variant BASE | 5, 6, 7, 8 |
| FMT-TEXT-CASE | TEXT MIME variant CASE | 5, 6, 7, 8 |
| FMT-TEXT-SPACE | TEXT MIME variant SPACE | 5, 6, 7, 8 |
| FMT-TEXT-NAME | TEXT MIME variant NAME | 5, 6, 7, 8 |
| FMT-TEXT-QUOTED-SEMICOLON | TEXT MIME variant QUOTED-SEMICOLON | 5, 6, 7, 8 |
| FMT-TEXT-PARAM-ORDER | TEXT MIME variant PARAM-ORDER | 5, 6, 7, 8 |
| FMT-TEXT-UNKNOWN-PARAM | TEXT MIME variant UNKNOWN-PARAM | 5, 6, 7, 8 |
| FMT-TEXT-OCTET | TEXT MIME variant OCTET | 5, 6, 7, 8 |
| FMT-TEXT-ABSENT | TEXT MIME variant ABSENT | 5, 6, 7, 8 |
| FMT-TEXT-CHARSET | TEXT MIME variant CHARSET | 5, 6, 7, 8 |
| FMT-TEXT-CHARSET-QUOTED | TEXT MIME variant CHARSET-QUOTED | 5, 6, 7, 8 |
| FMT-TEXT-MULTIPARAM | TEXT MIME variant MULTIPARAM | 5, 6, 7, 8 |
| FMT-TEXT-BADPARAM | TEXT malformed MIME parameter | 6 |
| FMT-HTML-BASE | HTML MIME variant BASE | 5, 6, 7, 8 |
| FMT-HTML-CASE | HTML MIME variant CASE | 5, 6, 7, 8 |
| FMT-HTML-SPACE | HTML MIME variant SPACE | 5, 6, 7, 8 |
| FMT-HTML-NAME | HTML MIME variant NAME | 5, 6, 7, 8 |
| FMT-HTML-QUOTED-SEMICOLON | HTML MIME variant QUOTED-SEMICOLON | 5, 6, 7, 8 |
| FMT-HTML-PARAM-ORDER | HTML MIME variant PARAM-ORDER | 5, 6, 7, 8 |
| FMT-HTML-UNKNOWN-PARAM | HTML MIME variant UNKNOWN-PARAM | 5, 6, 7, 8 |
| FMT-HTML-OCTET | HTML MIME variant OCTET | 5, 6, 7, 8 |
| FMT-HTML-ABSENT | HTML MIME variant ABSENT | 5, 6, 7, 8 |
| FMT-HTML-CHARSET | HTML MIME variant CHARSET | 5, 6, 7, 8 |
| FMT-HTML-CHARSET-QUOTED | HTML MIME variant CHARSET-QUOTED | 5, 6, 7, 8 |
| FMT-HTML-MULTIPARAM | HTML MIME variant MULTIPARAM | 5, 6, 7, 8 |
| FMT-HTML-BADPARAM | HTML malformed MIME parameter | 6 |
| FMT-XHTML-BASE | XHTML MIME variant BASE | 5, 6, 7, 8 |
| FMT-XHTML-CASE | XHTML MIME variant CASE | 5, 6, 7, 8 |
| FMT-XHTML-SPACE | XHTML MIME variant SPACE | 5, 6, 7, 8 |
| FMT-XHTML-NAME | XHTML MIME variant NAME | 5, 6, 7, 8 |
| FMT-XHTML-QUOTED-SEMICOLON | XHTML MIME variant QUOTED-SEMICOLON | 5, 6, 7, 8 |
| FMT-XHTML-PARAM-ORDER | XHTML MIME variant PARAM-ORDER | 5, 6, 7, 8 |
| FMT-XHTML-UNKNOWN-PARAM | XHTML MIME variant UNKNOWN-PARAM | 5, 6, 7, 8 |
| FMT-XHTML-OCTET | XHTML MIME variant OCTET | 5, 6, 7, 8 |
| FMT-XHTML-ABSENT | XHTML MIME variant ABSENT | 5, 6, 7, 8 |
| FMT-XHTML-CHARSET | XHTML MIME variant CHARSET | 5, 6, 7, 8 |
| FMT-XHTML-CHARSET-QUOTED | XHTML MIME variant CHARSET-QUOTED | 5, 6, 7, 8 |
| FMT-XHTML-MULTIPARAM | XHTML MIME variant MULTIPARAM | 5, 6, 7, 8 |
| FMT-XHTML-BADPARAM | XHTML malformed MIME parameter | 6 |
| FMT-XML-BASE | XML MIME variant BASE | 5, 6, 7, 8 |
| FMT-XML-CASE | XML MIME variant CASE | 5, 6, 7, 8 |
| FMT-XML-SPACE | XML MIME variant SPACE | 5, 6, 7, 8 |
| FMT-XML-NAME | XML MIME variant NAME | 5, 6, 7, 8 |
| FMT-XML-QUOTED-SEMICOLON | XML MIME variant QUOTED-SEMICOLON | 5, 6, 7, 8 |
| FMT-XML-PARAM-ORDER | XML MIME variant PARAM-ORDER | 5, 6, 7, 8 |
| FMT-XML-UNKNOWN-PARAM | XML MIME variant UNKNOWN-PARAM | 5, 6, 7, 8 |
| FMT-XML-OCTET | XML MIME variant OCTET | 5, 6, 7, 8 |
| FMT-XML-ABSENT | XML MIME variant ABSENT | 5, 6, 7, 8 |
| FMT-XML-CHARSET | XML MIME variant CHARSET | 5, 6, 7, 8 |
| FMT-XML-CHARSET-QUOTED | XML MIME variant CHARSET-QUOTED | 5, 6, 7, 8 |
| FMT-XML-MULTIPARAM | XML MIME variant MULTIPARAM | 5, 6, 7, 8 |
| FMT-XML-BADPARAM | XML malformed MIME parameter | 6 |
| FMT-DOCX-BASE | DOCX MIME variant BASE | 5, 6, 7, 8 |
| FMT-DOCX-CASE | DOCX MIME variant CASE | 5, 6, 7, 8 |
| FMT-DOCX-SPACE | DOCX MIME variant SPACE | 5, 6, 7, 8 |
| FMT-DOCX-NAME | DOCX MIME variant NAME | 5, 6, 7, 8 |
| FMT-DOCX-QUOTED-SEMICOLON | DOCX MIME variant QUOTED-SEMICOLON | 5, 6, 7, 8 |
| FMT-DOCX-PARAM-ORDER | DOCX MIME variant PARAM-ORDER | 5, 6, 7, 8 |
| FMT-DOCX-UNKNOWN-PARAM | DOCX MIME variant UNKNOWN-PARAM | 5, 6, 7, 8 |
| FMT-DOCX-OCTET | DOCX MIME variant OCTET | 5, 6, 7, 8 |
| FMT-DOCX-ABSENT | DOCX MIME variant ABSENT | 5, 6, 7, 8 |
| FMT-DOCX-EXTRANEOUS-CHARSET | DOCX MIME variant EXTRANEOUS-CHARSET | 5, 6, 7, 8 |
| FMT-DOCX-BADPARAM | DOCX malformed MIME parameter | 6 |
| FMT-PNG-BASE | PNG MIME variant BASE | 5, 6, 7, 8, 26 |
| FMT-PNG-CASE | PNG MIME variant CASE | 5, 6, 7, 8, 26 |
| FMT-PNG-SPACE | PNG MIME variant SPACE | 5, 6, 7, 8, 26 |
| FMT-PNG-NAME | PNG MIME variant NAME | 5, 6, 7, 8, 26 |
| FMT-PNG-QUOTED-SEMICOLON | PNG MIME variant QUOTED-SEMICOLON | 5, 6, 7, 8, 26 |
| FMT-PNG-PARAM-ORDER | PNG MIME variant PARAM-ORDER | 5, 6, 7, 8, 26 |
| FMT-PNG-UNKNOWN-PARAM | PNG MIME variant UNKNOWN-PARAM | 5, 6, 7, 8, 26 |
| FMT-PNG-OCTET | PNG MIME variant OCTET | 5, 6, 7, 8, 26 |
| FMT-PNG-ABSENT | PNG MIME variant ABSENT | 5, 6, 7, 8, 26 |
| FMT-PNG-EXTRANEOUS-CHARSET | PNG MIME variant EXTRANEOUS-CHARSET | 5, 6, 7, 8, 26 |
| FMT-PNG-BADPARAM | PNG malformed MIME parameter | 6 |
| FMT-JPEG-BASE | JPEG MIME variant BASE | 5, 6, 7, 8, 26 |
| FMT-JPEG-CASE | JPEG MIME variant CASE | 5, 6, 7, 8, 26 |
| FMT-JPEG-SPACE | JPEG MIME variant SPACE | 5, 6, 7, 8, 26 |
| FMT-JPEG-NAME | JPEG MIME variant NAME | 5, 6, 7, 8, 26 |
| FMT-JPEG-QUOTED-SEMICOLON | JPEG MIME variant QUOTED-SEMICOLON | 5, 6, 7, 8, 26 |
| FMT-JPEG-PARAM-ORDER | JPEG MIME variant PARAM-ORDER | 5, 6, 7, 8, 26 |
| FMT-JPEG-UNKNOWN-PARAM | JPEG MIME variant UNKNOWN-PARAM | 5, 6, 7, 8, 26 |
| FMT-JPEG-OCTET | JPEG MIME variant OCTET | 5, 6, 7, 8, 26 |
| FMT-JPEG-ABSENT | JPEG MIME variant ABSENT | 5, 6, 7, 8, 26 |
| FMT-JPEG-EXTRANEOUS-CHARSET | JPEG MIME variant EXTRANEOUS-CHARSET | 5, 6, 7, 8, 26 |
| FMT-JPEG-BADPARAM | JPEG malformed MIME parameter | 6 |
| FMT-TIFF-BASE | TIFF MIME variant BASE | 5, 6, 7, 8, 26 |
| FMT-TIFF-CASE | TIFF MIME variant CASE | 5, 6, 7, 8, 26 |
| FMT-TIFF-SPACE | TIFF MIME variant SPACE | 5, 6, 7, 8, 26 |
| FMT-TIFF-NAME | TIFF MIME variant NAME | 5, 6, 7, 8, 26 |
| FMT-TIFF-QUOTED-SEMICOLON | TIFF MIME variant QUOTED-SEMICOLON | 5, 6, 7, 8, 26 |
| FMT-TIFF-PARAM-ORDER | TIFF MIME variant PARAM-ORDER | 5, 6, 7, 8, 26 |
| FMT-TIFF-UNKNOWN-PARAM | TIFF MIME variant UNKNOWN-PARAM | 5, 6, 7, 8, 26 |
| FMT-TIFF-OCTET | TIFF MIME variant OCTET | 5, 6, 7, 8, 26 |
| FMT-TIFF-ABSENT | TIFF MIME variant ABSENT | 5, 6, 7, 8, 26 |
| FMT-TIFF-EXTRANEOUS-CHARSET | TIFF MIME variant EXTRANEOUS-CHARSET | 5, 6, 7, 8, 26 |
| FMT-TIFF-BADPARAM | TIFF malformed MIME parameter | 6 |
| FMT-WEBP-BASE | WEBP MIME variant BASE | 5, 6, 7, 8, 26 |
| FMT-WEBP-CASE | WEBP MIME variant CASE | 5, 6, 7, 8, 26 |
| FMT-WEBP-SPACE | WEBP MIME variant SPACE | 5, 6, 7, 8, 26 |
| FMT-WEBP-NAME | WEBP MIME variant NAME | 5, 6, 7, 8, 26 |
| FMT-WEBP-QUOTED-SEMICOLON | WEBP MIME variant QUOTED-SEMICOLON | 5, 6, 7, 8, 26 |
| FMT-WEBP-PARAM-ORDER | WEBP MIME variant PARAM-ORDER | 5, 6, 7, 8, 26 |
| FMT-WEBP-UNKNOWN-PARAM | WEBP MIME variant UNKNOWN-PARAM | 5, 6, 7, 8, 26 |
| FMT-WEBP-OCTET | WEBP MIME variant OCTET | 5, 6, 7, 8, 26 |
| FMT-WEBP-ABSENT | WEBP MIME variant ABSENT | 5, 6, 7, 8, 26 |
| FMT-WEBP-EXTRANEOUS-CHARSET | WEBP MIME variant EXTRANEOUS-CHARSET | 5, 6, 7, 8, 26 |
| FMT-WEBP-BADPARAM | WEBP malformed MIME parameter | 6 |
| ALIAS-TEXTXML | Explicitly registered alias text/xml | 5, 6 |
| ALIAS-XPDF | Explicitly registered alias application/x-pdf | 5, 6 |
| ALIAS-JPG | Explicitly registered alias image/jpg | 5, 6 |
| ALIAS-XTIF | Explicitly registered alias image/x-tiff | 5, 6 |
| UNSUPPORTED-DOC-BASE | Disabled/unsupported DOC BASE | 5, 9 |
| UNSUPPORTED-DOC-PARAM | Disabled/unsupported DOC PARAM | 5, 9 |
| UNSUPPORTED-RICHTEXT-BASE | Disabled/unsupported RICHTEXT BASE | 5, 9 |
| UNSUPPORTED-RICHTEXT-PARAM | Disabled/unsupported RICHTEXT PARAM | 5, 9 |
| UNSUPPORTED-ENRICHED-BASE | Disabled/unsupported ENRICHED BASE | 5, 9 |
| UNSUPPORTED-ENRICHED-PARAM | Disabled/unsupported ENRICHED PARAM | 5, 9 |
| UNSUPPORTED-DICOM-BASE | Disabled/unsupported DICOM BASE | 5, 9 |
| UNSUPPORTED-DICOM-PARAM | Disabled/unsupported DICOM PARAM | 5, 9 |
| UNSUPPORTED-AUDIO-BASE | Disabled/unsupported AUDIO BASE | 5, 9 |
| UNSUPPORTED-AUDIO-PARAM | Disabled/unsupported AUDIO PARAM | 5, 9 |
| UNSUPPORTED-VIDEO-BASE | Disabled/unsupported VIDEO BASE | 5, 9 |
| UNSUPPORTED-VIDEO-PARAM | Disabled/unsupported VIDEO PARAM | 5, 9 |
| UNSUPPORTED-CSV-BASE | Disabled/unsupported CSV BASE | 5, 9 |
| UNSUPPORTED-CSV-PARAM | Disabled/unsupported CSV PARAM | 5, 9 |
| UNSUPPORTED-EXECUTABLE-BASE | Disabled/unsupported EXECUTABLE BASE | 5, 9 |
| UNSUPPORTED-EXECUTABLE-PARAM | Disabled/unsupported EXECUTABLE PARAM | 5, 9 |
| UNSUPPORTED-JSON-BASE | Disabled/unsupported JSON BASE | 5, 9 |
| UNSUPPORTED-JSON-PARAM | Disabled/unsupported JSON PARAM | 5, 9 |
| UNSUPPORTED-BMP-BASE | Disabled/unsupported BMP BASE | 5, 9 |
| UNSUPPORTED-BMP-PARAM | Disabled/unsupported BMP PARAM | 5, 9 |
| UNSUPPORTED-GIF-BASE | Disabled/unsupported GIF BASE | 5, 9 |
| UNSUPPORTED-GIF-PARAM | Disabled/unsupported GIF PARAM | 5, 9 |
| UNSUPPORTED-HEIC-BASE | Disabled/unsupported HEIC BASE | 5, 9 |
| UNSUPPORTED-HEIC-PARAM | Disabled/unsupported HEIC PARAM | 5, 9 |
| UNSUPPORTED-HEIF-BASE | Disabled/unsupported HEIF BASE | 5, 9 |
| UNSUPPORTED-HEIF-PARAM | Disabled/unsupported HEIF PARAM | 5, 9 |
| UNSUPPORTED-ANIMATED-BASE | Disabled/unsupported ANIMATED BASE | 5, 9 |
| UNSUPPORTED-ANIMATED-PARAM | Disabled/unsupported ANIMATED PARAM | 5, 9 |
| TRANSPORT-FHIRJSON-OFF | Disabled FHIRJSON transport adapter | 5, 8 |
| TRANSPORT-FHIRJSON-ON | Approved FHIRJSON adapter unwraps content | 5, 8 |
| TRANSPORT-FHIRJSON-PARAM | FHIRJSON transport MIME PARAM | 5, 6, 8 |
| TRANSPORT-FHIRJSON-CASE | FHIRJSON transport MIME CASE | 5, 6, 8 |
| TRANSPORT-FHIRJSON-CHARSET | FHIRJSON transport MIME CHARSET | 5, 6, 8 |
| TRANSPORT-FHIRXML-OFF | Disabled FHIRXML transport adapter | 5, 8 |
| TRANSPORT-FHIRXML-ON | Approved FHIRXML adapter unwraps content | 5, 8 |
| TRANSPORT-FHIRXML-PARAM | FHIRXML transport MIME PARAM | 5, 6, 8 |
| TRANSPORT-FHIRXML-CASE | FHIRXML transport MIME CASE | 5, 6, 8 |
| TRANSPORT-FHIRXML-CHARSET | FHIRXML transport MIME CHARSET | 5, 6, 8 |
| TRANSPORT-NDJSON-OFF | Unsupported release format: Disabled NDJSON transport adapter | 5, 8 |
| TRANSPORT-NDJSON-ON | Unsupported release format: Approved NDJSON adapter unwraps content | 5, 8 |
| TRANSPORT-NDJSON-PARAM | Unsupported release format: NDJSON transport MIME PARAM | 5, 6, 8 |
| TRANSPORT-NDJSON-CASE | Unsupported release format: NDJSON transport MIME CASE | 5, 6, 8 |
| TRANSPORT-NDJSON-CHARSET | Unsupported release format: NDJSON transport MIME CHARSET | 5, 6, 8 |
| TRANSPORT-GZIP-OFF | Unsupported release format: Disabled GZIP transport adapter | 5, 8 |
| TRANSPORT-GZIP-ON | Unsupported release format: Approved GZIP adapter unwraps content | 5, 8 |
| TRANSPORT-GZIP-PARAM | Unsupported release format: GZIP transport MIME PARAM | 5, 6, 8 |
| TRANSPORT-GZIP-CASE | Unsupported release format: GZIP transport MIME CASE | 5, 6, 8 |
| TRANSPORT-GZIP-CHARSET | Unsupported release format: GZIP transport MIME CHARSET | 5, 6, 8 |
| TRANSPORT-ZIP-OFF | Unsupported release format: Disabled ZIP transport adapter | 5, 8 |
| TRANSPORT-ZIP-ON | Unsupported release format: Approved ZIP adapter unwraps content | 5, 8 |
| TRANSPORT-ZIP-PARAM | Unsupported release format: ZIP transport MIME PARAM | 5, 6, 8 |
| TRANSPORT-ZIP-CASE | Unsupported release format: ZIP transport MIME CASE | 5, 6, 8 |
| TRANSPORT-ZIP-CHARSET | Unsupported release format: ZIP transport MIME CHARSET | 5, 6, 8 |
| TRANSPORT-MULTIPART-OFF | Disabled MULTIPART transport adapter | 5, 8 |
| TRANSPORT-MULTIPART-ON | Approved MULTIPART adapter unwraps content | 5, 8 |
| TRANSPORT-MULTIPART-PARAM | MULTIPART transport MIME PARAM | 5, 6, 8 |
| TRANSPORT-MULTIPART-CASE | MULTIPART transport MIME CASE | 5, 6, 8 |
| TRANSPORT-MULTIPART-CHARSET | MULTIPART transport MIME CHARSET | 5, 6, 8 |
| ENC-EXPLICIT-UTF32LE | Explicit encoding UTF32LE | 7 |
| ENC-EXPLICIT-UTF32BE | Explicit encoding UTF32BE | 7 |
| ENC-EXPLICIT-UTF16NOBOM | Explicit encoding UTF16NOBOM | 7 |
| ENC-EXPLICIT-LATIN1 | Explicit encoding LATIN1 | 7 |
| RTF-UC-VENDOR | RTF Unicode fallback rules and hidden destination | 7 |
| ENC-FORMAT-HTMLCP | Honor format encoding HTMLCP | 7 |
| ENC-FORMAT-XMLCP | Honor format encoding XMLCP | 7 |
| ENC-FORMAT-XML16 | Honor format encoding XML16 | 7 |
| ENC-REJECT-HTML | Reject corrupt or conflicting encoding HTML | 7 |
| ENC-REJECT-XML | Reject corrupt or conflicting encoding XML | 7 |
| ENC-REJECT-CONTROL | Reject corrupt or conflicting encoding CONTROL | 7 |
| ENC-REJECT-REPLACEMENT | Reject corrupt or conflicting encoding REPLACEMENT | 7 |
| MIME-RECURSION | Filename inference terminates | 6 |
| MIME-POLYGLOT | Conflicting format markers not accepted | 6 |
| HTML-ACTIVE | Scripts/styles excluded and never executed | 8 |
| XML-DTD | Internal entity processing disabled | 8 |
| FHIR-BASE64 | Malformed attachment base64 rejected | 5, 8 |
| NDJSON-PARTIAL | Malformed NDJSON tail cannot be silently complete | 5, 8 |
| GZIP-DOUBLE | HTTP compression decoded once; nested gzip document rejected | 8 |
| ZIP-DEPTH | Reject excluded ZIP before expansion: Archive depth cap | 8 |
| ZIP-ENTRIES | Reject excluded ZIP before expansion: Archive entry-count cap | 8 |
| LIMIT-PAGES | PDF page count cap before model | 8 |
| LIMIT-PARSER | Parser hard timeout cannot become fallback | 8, A09 |
| LIMIT-MEMORY | Parser worker memory budget enforced | 8, A09 |
| CANCEL-WORKER | Cancellation terminates or reaps worker | 8, 23 |
| CANCEL-COMMIT | Cancellation near save reconciles outcome | A06, 23 |
| CONTRACT-TEXT | Bare string cannot bypass typed extraction gate | 9 |
| CONTRACT-MARKUP | Success label with raw RTF still rejected | 9 |
| A02-FIELDS | All cache clinical fields round-trip | A02 |
| A02-SERIALIZE | Cache serialization error is not cache miss | A02 |
| A02-QUERY | Cache query error is not cache miss | A02 |
| A03-ALLFAILED | All acquisitions failed is not absence | A03 |
| A03-PENDING | Pending acquisition explicitly represented | A03 |
| A03-MISSINGPATH | Missing object path counts as failure | A03 |
| A03-EXCLUDED | Intentional exclusion has reason and count | A03 |
| A03-FHIRFALLBACK | FHIR-only result discloses unavailable attachments | A03 |
| A04-OMITTED | Model omits expected document from successful batch | A04 |
| A04-DUPLICATE | Duplicate model document IDs rejected | A04 |
| A04-UNEXPECTED | Unexpected model source ID rejected | A04 |
| A04-ALLFAILED | All model batches fail without empty synthesis | A04 |
| A05-CONFLICT | Conflicting merged outcomes retain provenance | A05 |
| A05-EQUIVALENT | Equivalent repeated instructions deduplicate | A05 |
| A05-QUOTEPAIR | Merged follow-up keeps correct source quote | A05 |
| A06-CLEANUP | Only pending tasks cancelled at timeout | A06 |
| A07-ARRAY | Same-length reordered translation changes associations | A07 |
| A07-TYPE | Boolean-string substitution rejected | A07 |
| A07-EMPTY | Empty translated narrative retains original | A07 |
| A07-METADATA | Source IDs/evidence/metadata not translated | A07, 25 |
| A07-MIXED | Field fallback reports partial translation | A07 |
| A08-PROCEDURETAIL | Procedure path processes beyond 100000 characters | A08 |
| A08-LONGTRANSCRIPT | Long transcript cannot bypass context gate | A08 |
| A09-FASTREQUEST | Slow parsing allows unrelated fast request | A09 |
| A10-FIRSTWRITES | Concurrent first writes use one source identity | A10 |
| A10-PROCEDURES | Concurrent procedure batches preserve source identity | A10 |
| A10-ORM | ORM alignment does not issue DDL | A10 |
| A11-ADDED | New document invalidates cache | A11 |
| A11-PARTIAL | Prior partial result not reused as complete | A11 |
| A11-FORCE | Explicit regeneration is source scoped | A11 |
| CLIN-LATERALITY | Laterality and decimals preserved | 25 |
| CLIN-CONFLICTDOSE | Conflicting doses never silently reconciled | 25 |
| CLIN-IDENTITY | Second patient facts never assigned to first | 25 |
| CLIN-QUOTESEMANTICS | Existing quote does not validate contradictory paraphrase | 25 |
| CLIN-OFFSETS | Incorrect evidence offsets rejected | 25 |
| CLIN-NORMALIZE | Normalization must retain clinical punctuation | 25 |
| CLIN-OMISSION | Required diagnosis omission measured independently | 25 |
| CLIN-POSTPROCESS | Final persisted version equals validated version | 25 |
| VISION-CROP | Overlapping crops deduplicate without lost rows | 26 |
| VISION-COORDS | Model invented boxes not treated as exact evidence | 26 |
| VISION-BUDGET | Million context does not override output/request budgets | 26 |
| VISION-ESCALATE | Escalation bounded and uses original page | 26 |
| VISION-ROLLBACK | Disabling vision never restores raw forwarding | 26 |
| ERROR-STATUS | Partial outcome not inferred as complete from null error | 23 |
| ERROR-UNKNOWNCOUNTS | Inventory failure leaves counts unknown | 23 |
| ERROR-COVERAGE | Coverage counts reconcile | 23 |
| ERROR-REQUEST | Invalid request distinct from model invalid output | 23 |
| ERROR-MODEL422 | Invalid AI result not blamed on user request | 23 |
| ERROR-PREVIOUS | Failed refresh lifecycle separate from display provenance | 23 |
| ERROR-UNEXPECTED | Unexpected exception safe and classified | 23 |
| ERROR-CORRELATION | External correlation identifier validated | 23 |
| ERROR-PERSISTRETRY | Persistence retry idempotent in memory | 23 |
| UI-CLINICALFIELDS | Unavailable placeholder clears clinical fields | 24 |
| UI-PREFIX | Partial notice precedes clinical prose | 24 |
| UI-DETERMINISTIC | Error copy does not depend on model | 24 |
| UI-CONTRACT | Existing response shapes preserved | 24 |
| UI-PROCEDURELIST | Procedure success retains list response | 24 |
| META-BOUNDED | Metadata bounded and excludes raw documents | 24, 25 |
| MONITOR-STAGES | Metrics distinguish parse/model/coverage failures | 15, 23 |
| ROLLOUT-NOREPROCESS | Parser deployment does not trigger historical regeneration | 18 |
| ROLLOUT-NORAW | Strict-gate rollback never forwards raw markup | 18 |
| POLICY-SOURCE_INVENTORY_FAILED | Central policy for SOURCE_INVENTORY_FAILED | 23 |
| POLICY-DOWNLOAD_PENDING | Central policy for DOWNLOAD_PENDING | 23 |
| POLICY-DOWNLOAD_TIMEOUT | Central policy for DOWNLOAD_TIMEOUT | 23 |
| POLICY-DOWNLOAD_UNAVAILABLE | Central policy for DOWNLOAD_UNAVAILABLE | 23 |
| POLICY-DOCUMENT_NOT_FOUND | Central policy for DOCUMENT_NOT_FOUND | 23 |
| POLICY-DOCUMENT_ACCESS_DENIED | Central policy for DOCUMENT_ACCESS_DENIED | 23 |
| POLICY-MODEL_RATE_LIMITED | Central policy for MODEL_RATE_LIMITED | 23 |
| POLICY-MODEL_TIMEOUT | Central policy for MODEL_TIMEOUT | 23 |
| POLICY-MODEL_UNAVAILABLE | Central policy for MODEL_UNAVAILABLE | 23 |
| POLICY-MODEL_OUTPUT_INVALID | Central policy for MODEL_OUTPUT_INVALID | 23 |
| POLICY-PERSISTENCE_FAILED | Central policy for PERSISTENCE_FAILED | 23 |
| POLICY-INTERNAL_PROCESSING_ERROR | Central policy for INTERNAL_PROCESSING_ERROR | 23 |
| POLICY-RETRYAFTER | Honor bounded provider Retry-After | 23 |
| GATE-ATTACHMENT_SUMMARY | Shared content gate on attachment_summary | 4, 9, 25 |
| GATE-PROCEDURE_SUMMARY | Shared content gate on procedure_summary | 4, 9, 25 |
| GATE-TRANSCRIPT | Shared content gate on transcript | 4, 9, 25 |
| GATE-METADATA-INFERENCE | Document-type metadata boundary rejects raw-body payload | 4, 9, 28 |
| CLIN-LIVE-PRESCRIPTION | Reject unsupported wording observed in live evaluation: PRESCRIPTION | 25 |
| CLIN-LIVE-LAB-INTERPRETATION | Reject unsupported wording observed in live evaluation: LAB-INTERPRETATION | 25 |
| CLIN-LIVE-VISIT-PURPOSE | Reject unsupported wording observed in live evaluation: VISIT-PURPOSE | 25 |
| A12-OWNER | Patient and appointment mismatch rejected before I/O | A12, 28 |
| A12-CACHE | Cache hit cannot bypass ownership check | A12, 28 |
| A12-DELEGATE | Authorized caregiver resolves patient identity correctly | A12, 28 |
| A12-STORAGE | Out-of-scope S3 location not fetched | A12, 28 |
| A13-SINGLETON | Singleton attachment agrees with inventory query contract | A13, 28 |
| A13-REVALIDATION | Failure record does not revalidate invalid metadata | A13, 28 |
| A14-ATTACHMENTS | Sibling attachments retain distinct identities | A14, 28 |
| A14-EVENTS | One report can produce multiple distinct procedures | A14, 28 |
| A14-KEYS | Opaque IDs cannot collide through comma joining | A14, 28 |
| A15-COUNTS | FHIR beyond first 10/20 has truthful coverage | A15, 28 |
| A15-STATUS | FHIR status survives formatting and storage | A15, 28 |
| A15-VALUES | FHIR nonquantity and component results handled | A15, 28 |
| A16-CLASSIDS | Dropped/duplicate classification outputs not silent success | A16, 28 |
| A16-NULLTYPE | NULL document type not silently excluded by SQL predicate | A16, 28 |
| A16-RULESCOPE | Connector-specific exclusion cannot leak to another connector | A16, 28 |
| A16-RULEVERSION | Rules or fallback tier invalidate eligibility cache | A16, 28 |
| A17-PLACEHOLDER | Health insights exclude failure text as clinical evidence | A17, 28 |
| A17-UPDATES | Updated clinical summary eligible for derived refresh | A17, 28 |
| A18-PASTE | Pasted RTF cannot masquerade as validated text | A18, 28 |
| A18-UPLOAD | Empty/missing-name uploads accounted for | A18, 28 |
| A18-OVERRIDE | Prompt experiment cannot disable code validation | A18, 28 |
| A19-REFRESH | Commit succeeds but refresh fails: reconcile without duplicate | A19, 28 |
| A19-RESPONSE | Response validation failure cannot corrupt committed summary | A19, 28 |
| A19-ACK | Unknown commit acknowledgement triggers identity reconciliation | A19, 28 |
| A13-SHAPE-NULL_ITEM | Malformed envelope isolated: null_item | A13, 28 |
| A13-SHAPE-STRING_ITEM | Malformed envelope isolated: string_item | A13, 28 |
| A13-SHAPE-LIST_ITEM | Malformed envelope isolated: list_item | A13, 28 |
| A13-SHAPE-NONOBJECT_RESOURCE_DATA | Malformed envelope isolated: nonobject_resource_data | A13, 28 |
| RES-OPTIONAL | Missing optional OCR dependency isolates capability | R48, 30 |
| RES-MANDATORY | Missing mandatory configuration fails readiness safely | R48, 30 |
| RES-STARTUP | Startup dependency hang bounded | R48, 30 |
| RES-FACTORY | Real test app construction has no production side effects | R48, 30 |
| RES-OVERLOAD | Admission rejects excess work before allocation | R49, 30 |
| RES-WORKERBUDGET | Replica/process multiplication accounted for | R49, 30 |
| RES-PREPDEADLINE | Inventory and cache preparation share deadline | R50, 30 |
| RES-POOLWAIT | Session or lock wait bounded | R50, 30 |
| RES-CLEANUP | Cancellation closes bodies/clients and temporary files | R51, 30 |
| RES-WORKERCRASH | Native worker crash isolated | R51, 30 |
| RES-SHUTDOWN | Shutdown bounded with work in flight | R51, 30 |
| RES-SCHEDULER | Multiple API starts do not duplicate publication | R51, 30 |
| RES-SOURCECHANGE | Source changes between extraction and publication | R52, 30 |
| RES-MEMBERSHIP | Stale document membership cannot drive pruning | R52, 30 |
| RES-JSONDIRTY | Outcome mutation is tracked without DB access | R53, 30 |
| RES-LEGACYMETA | Null/legacy metadata handled without loss | R53, 30 |
| RES-SERIALIZE | Nonserializable metadata rejected before save | R53, 30 |
| RES-ALIASES | Response aliases preserved through real route | R53, 30 |
| RES-ADAPTER | Mock/live use same fixed pipeline entry point | R54, 30 |
| RES-QAKEY | No application-key fallback when regression key absent | R54, 30 |
| RES-REPORTIO | Report write failure never reported as successful run | R54, 30 |
| ROUTING-PDF-LOGO | Native PDF text retained; zero OCR/vision calls | OCR/DOCX routing and compatibility review |
| ROUTING-DOCX-LOGO | Header, first-paragraph and footer logos retain clinical text and table text; zero OCR calls | OCR/DOCX routing and compatibility review |
| ROUTING-DOCX-IMAGE | Unsupported clinical image returns UNSUPPORTED_FORMAT without entering OCR renderer | OCR/DOCX routing and compatibility review |
| ROUTING-MIXED-PDF | Only scanned page transcribed; three native pages preserved in order | OCR/DOCX routing and compatibility review |
| ROUTING-BLANK | Blank PDF returns NO_READABLE_TEXT with no model call | OCR/DOCX routing and compatibility review |
| ACCESS-EXISTING-SERVICE | Trusted service retains existing patient delegation without new mapping lookup | OCR/DOCX routing and compatibility review |
| ACCESS-EXISTING-PATIENT | Authenticated mapped patient accepted; cross-patient request denied | OCR/DOCX routing and compatibility review |
| PRESERVE-FAILED-REFRESH | Failed refresh retains diagnosis and original summary with exactly one notice | OCR/DOCX routing and compatibility review |
| PRESERVE-EMPTY-PARTIAL | Empty failed procedure refresh does not delete prior rows or clinical content | OCR/DOCX routing and compatibility review |
| DOC-LEGACY-VALID | Valid legacy Word parsed before clinical AI | 7, PARSE-05 |
| FHIR-NESTED-NESTED_BUNDLE-JSON | Parse nested FHIR attachment: nested_bundle.json | 5, 8 |
| FHIR-NESTED-NESTED_BUNDLE-XML | Parse nested FHIR attachment: nested_bundle.xml | 5, 8 |
| FHIR-NESTED-NESTED_REPORT-JSON | Parse nested FHIR attachment: nested_report.json | 5, 8 |
| FHIR-NESTED-NESTED_REPORT-XML | Parse nested FHIR attachment: nested_report.xml | 5, 8 |
| FHIR-NESTED-REMOTE | Unacquired nested remote attachment is unavailable | 5, 8 |
