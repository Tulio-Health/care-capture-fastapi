# RTF MIME and encoding matrix

This matrix specifies scenarios; current execution results are in `../results/report.html`. Parameter conflict policies are explicit test configurations. `application/x-rtf` is an approved compatibility alias in this test profile; this does not assert current implementation support.

| ID | Declared MIME or scenario | Expected behavior |
|---|---|---|
| RTF-MIME-APP | `application/rtf` | RTF adapter; preserved clinical text; no raw markup |
| RTF-MIME-TEXT | `text/rtf` | RTF adapter; preserved clinical text; no raw markup |
| RTF-MIME-ALIAS | `application/x-rtf` | RTF adapter; preserved clinical text; no raw markup |
| RTF-MIME-APP-UTF8 | `application/rtf; charset=utf-8` | RTF adapter; preserved clinical text; no raw markup |
| RTF-MIME-TEXT-UTF8 | `text/rtf;charset=UTF-8` | RTF adapter; preserved clinical text; no raw markup |
| RTF-MIME-CP1252 | `application/rtf; charset=windows-1252` | RTF adapter; preserved clinical text; no raw markup |
| RTF-MIME-QUOTED | `text/rtf; charset="windows-1252"` | RTF adapter; preserved clinical text; no raw markup |
| RTF-MIME-CASE | `Application/RTF; CHARSET="UTF-8"` | RTF adapter; preserved clinical text; no raw markup |
| RTF-MIME-SPACE | `  application/rtf  ;  charset = "utf-8"  ` | RTF adapter; preserved clinical text; no raw markup |
| RTF-MIME-MULTI | `application/rtf; charset=utf-8; name="referral.rtf"` | RTF adapter; preserved clinical text; no raw markup |
| RTF-MIME-SEMICOLON | `application/rtf; name="Referral; September.rtf"; charset=utf-8` | RTF adapter; preserved clinical text; no raw markup |
| RTF-MIME-ORDER | `text/rtf; name="referral.rtf"; charset="UTF-8"` | RTF adapter; preserved clinical text; no raw markup |
| RTF-MIME-EXTRA | `application/rtf; version=1; x-source=cerner; charset=utf-8` | RTF adapter; preserved clinical text; no raw markup |
| RTF-MIME-OCTET | `application/octet-stream` | RTF adapter; preserved clinical text; no raw markup |
| RTF-MIME-OCTET-PARAM | `application/octet-stream; name="referral.rtf"` | RTF adapter; preserved clinical text; no raw markup |
| RTF-MIME-PLAIN | `text/plain` | RTF adapter; preserved clinical text; no raw markup |
| RTF-MIME-PLAIN-PARAM | `text/plain; charset=utf-8` | RTF adapter; preserved clinical text; no raw markup |
| RTF-MIME-ALIAS-PARAM | `application/x-rtf; charset="windows-1252"` | RTF adapter; preserved clinical text; no raw markup |
| RTF-MIME-BOM-PARAM | `text/plain; charset="utf-8"` | RTF adapter; preserved clinical text; no raw markup |
| RTF-MIME-WHITESPACE | `RTF signature after whitespace` | RTF adapter; preserved clinical text; no raw markup |
| RTF-MIME-WRONGEXT | `application/octet-stream` | RTF adapter; preserved clinical text; no raw markup |
| RTF-MIME-DUPLICATE | `application/rtf; charset=utf-8; charset=windows-1252` | Controlled failure; no clinical summarization |
| RTF-MIME-BADQUOTE | `application/rtf; charset="utf-8` | Controlled failure; no clinical summarization |
| RTF-ENC-RAW | `application/rtf; charset=windows-1252` | RTF adapter; preserved clinical text; no raw markup |
| RTF-ENC-CONFLICT | `application/rtf; charset=utf-8` | Controlled failure; no clinical summarization |
| RTF-ENC-UNICODE | `Signed RTF Unicode values retain non-Latin text` | RTF adapter; preserved clinical text; no raw markup |
| RTF-EMPTY | `RTF without readable text` | Controlled failure; no clinical summarization |
| RTF-PARSER-FAIL-PARAM | `text/rtf; charset="utf-8"` | Controlled failure; no clinical summarization |
| RTF-UC-VENDOR | `RTF Unicode fallback rules and hidden destination` | RTF adapter; preserved clinical text; no raw markup |
