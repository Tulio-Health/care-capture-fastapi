# MIME and format regression matrix

This matrix specifies scenarios; current execution results are in `../results/report.html`. Supported/unsupported status is controlled by the explicit case profile, not implied by a file extension. Binary MIME charset parameters do not authorize decoding binary containers as text.

| Case | Input | Declared MIME / profile |
|---|---|---|
| MIME-01 | clinical.html | `text/html;charset=utf-8` |
| MIME-02 | clinical.html | ` Text/HTML ; Charset="UTF-8" ` |
| MIME-03 | clinical.rtf | `text/plain` |
| MIME-04 | rtf_bom_no_extension | `fixture declaration` |
| MIME-05 | native.pdf | `application/octet-stream` |
| MIME-06 | gateway_error.html | `fixture declaration` |
| MIME-07 | clinical_utf8.txt | `text/x-qa-unknown` |
| MIME-08 | generic.zip | `fixture declaration` |
| RTF-MIME-APP | clinical.rtf | `application/rtf` |
| RTF-MIME-TEXT | clinical.rtf | `text/rtf` |
| RTF-MIME-ALIAS | clinical.rtf | `application/x-rtf` |
| RTF-MIME-APP-UTF8 | clinical.rtf | `application/rtf; charset=utf-8` |
| RTF-MIME-TEXT-UTF8 | clinical.rtf | `text/rtf;charset=UTF-8` |
| RTF-MIME-CP1252 | clinical.rtf | `application/rtf; charset=windows-1252` |
| RTF-MIME-QUOTED | clinical.rtf | `text/rtf; charset="windows-1252"` |
| RTF-MIME-CASE | clinical.rtf | `Application/RTF; CHARSET="UTF-8"` |
| RTF-MIME-SPACE | clinical.rtf | `  application/rtf  ;  charset = "utf-8"  ` |
| RTF-MIME-MULTI | clinical.rtf | `application/rtf; charset=utf-8; name="referral.rtf"` |
| RTF-MIME-SEMICOLON | clinical.rtf | `application/rtf; name="Referral; September.rtf"; charset=utf-8` |
| RTF-MIME-ORDER | clinical.rtf | `text/rtf; name="referral.rtf"; charset="UTF-8"` |
| RTF-MIME-EXTRA | clinical.rtf | `application/rtf; version=1; x-source=cerner; charset=utf-8` |
| RTF-MIME-OCTET | clinical.rtf | `application/octet-stream` |
| RTF-MIME-OCTET-PARAM | clinical.rtf | `application/octet-stream; name="referral.rtf"` |
| RTF-MIME-PLAIN | clinical.rtf | `text/plain` |
| RTF-MIME-PLAIN-PARAM | clinical.rtf | `text/plain; charset=utf-8` |
| RTF-MIME-ALIAS-PARAM | clinical.rtf | `application/x-rtf; charset="windows-1252"` |
| RTF-MIME-BOM-PARAM | rtf_bom_no_extension | `text/plain; charset="utf-8"` |
| RTF-MIME-WHITESPACE | rtf_leading_whitespace.rtf | `fixture declaration` |
| RTF-MIME-WRONGEXT | clinical.rtf | `application/octet-stream` |
| RTF-MIME-DUPLICATE | rtf_raw_cp1252.rtf | `application/rtf; charset=utf-8; charset=windows-1252` |
| RTF-MIME-BADQUOTE | clinical.rtf | `application/rtf; charset="utf-8` |
| FMT-PDF-BASE | native.pdf | `application/pdf` |
| FMT-PDF-CASE | native.pdf | `APPLICATION/PDF` |
| FMT-PDF-SPACE | native.pdf | ` application/pdf ` |
| FMT-PDF-NAME | native.pdf | `application/pdf; name="clinical document"` |
| FMT-PDF-QUOTED-SEMICOLON | native.pdf | `application/pdf; name="Clinical; September"` |
| FMT-PDF-PARAM-ORDER | native.pdf | `application/pdf; x-source=fasten; name="clinical"` |
| FMT-PDF-UNKNOWN-PARAM | native.pdf | `application/pdf; x-qa-version=1` |
| FMT-PDF-OCTET | native.pdf | `application/octet-stream` |
| FMT-PDF-ABSENT | native.pdf | `None` |
| FMT-PDF-EXTRANEOUS-CHARSET | native.pdf | `application/pdf; charset=utf-8` |
| FMT-PDF-BADPARAM | native.pdf | `application/pdf; name="unterminated` |
| FMT-RTF-BASE | clinical.rtf | `application/rtf` |
| FMT-RTF-CASE | clinical.rtf | `APPLICATION/RTF` |
| FMT-RTF-SPACE | clinical.rtf | ` application/rtf ` |
| FMT-RTF-NAME | clinical.rtf | `application/rtf; name="clinical document"` |
| FMT-RTF-QUOTED-SEMICOLON | clinical.rtf | `application/rtf; name="Clinical; September"` |
| FMT-RTF-PARAM-ORDER | clinical.rtf | `application/rtf; x-source=fasten; name="clinical"` |
| FMT-RTF-UNKNOWN-PARAM | clinical.rtf | `application/rtf; x-qa-version=1` |
| FMT-RTF-OCTET | clinical.rtf | `application/octet-stream` |
| FMT-RTF-ABSENT | clinical.rtf | `None` |
| FMT-RTF-CHARSET | clinical.rtf | `application/rtf;charset=utf-8` |
| FMT-RTF-CHARSET-QUOTED | clinical.rtf | `application/rtf; charset="UTF-8"` |
| FMT-RTF-MULTIPARAM | clinical.rtf | `application/rtf; name="clinical"; CHARSET="utf-8"` |
| FMT-RTF-BADPARAM | clinical.rtf | `application/rtf; name="unterminated` |
| FMT-TEXT-BASE | clinical_utf8.txt | `text/plain` |
| FMT-TEXT-CASE | clinical_utf8.txt | `TEXT/PLAIN` |
| FMT-TEXT-SPACE | clinical_utf8.txt | ` text/plain ` |
| FMT-TEXT-NAME | clinical_utf8.txt | `text/plain; name="clinical document"` |
| FMT-TEXT-QUOTED-SEMICOLON | clinical_utf8.txt | `text/plain; name="Clinical; September"` |
| FMT-TEXT-PARAM-ORDER | clinical_utf8.txt | `text/plain; x-source=fasten; name="clinical"` |
| FMT-TEXT-UNKNOWN-PARAM | clinical_utf8.txt | `text/plain; x-qa-version=1` |
| FMT-TEXT-OCTET | clinical_utf8.txt | `application/octet-stream` |
| FMT-TEXT-ABSENT | clinical_utf8.txt | `None` |
| FMT-TEXT-CHARSET | clinical_utf8.txt | `text/plain;charset=utf-8` |
| FMT-TEXT-CHARSET-QUOTED | clinical_utf8.txt | `text/plain; charset="UTF-8"` |
| FMT-TEXT-MULTIPARAM | clinical_utf8.txt | `text/plain; name="clinical"; CHARSET="utf-8"` |
| FMT-TEXT-BADPARAM | clinical_utf8.txt | `text/plain; name="unterminated` |
| FMT-HTML-BASE | clinical.html | `text/html` |
| FMT-HTML-CASE | clinical.html | `TEXT/HTML` |
| FMT-HTML-SPACE | clinical.html | ` text/html ` |
| FMT-HTML-NAME | clinical.html | `text/html; name="clinical document"` |
| FMT-HTML-QUOTED-SEMICOLON | clinical.html | `text/html; name="Clinical; September"` |
| FMT-HTML-PARAM-ORDER | clinical.html | `text/html; x-source=fasten; name="clinical"` |
| FMT-HTML-UNKNOWN-PARAM | clinical.html | `text/html; x-qa-version=1` |
| FMT-HTML-OCTET | clinical.html | `application/octet-stream` |
| FMT-HTML-ABSENT | clinical.html | `None` |
| FMT-HTML-CHARSET | clinical.html | `text/html;charset=utf-8` |
| FMT-HTML-CHARSET-QUOTED | clinical.html | `text/html; charset="UTF-8"` |
| FMT-HTML-MULTIPARAM | clinical.html | `text/html; name="clinical"; CHARSET="utf-8"` |
| FMT-HTML-BADPARAM | clinical.html | `text/html; name="unterminated` |
| FMT-XHTML-BASE | clinical.xhtml | `application/xhtml+xml` |
| FMT-XHTML-CASE | clinical.xhtml | `APPLICATION/XHTML+XML` |
| FMT-XHTML-SPACE | clinical.xhtml | ` application/xhtml+xml ` |
| FMT-XHTML-NAME | clinical.xhtml | `application/xhtml+xml; name="clinical document"` |
| FMT-XHTML-QUOTED-SEMICOLON | clinical.xhtml | `application/xhtml+xml; name="Clinical; September"` |
| FMT-XHTML-PARAM-ORDER | clinical.xhtml | `application/xhtml+xml; x-source=fasten; name="clinical"` |
| FMT-XHTML-UNKNOWN-PARAM | clinical.xhtml | `application/xhtml+xml; x-qa-version=1` |
| FMT-XHTML-OCTET | clinical.xhtml | `application/octet-stream` |
| FMT-XHTML-ABSENT | clinical.xhtml | `None` |
| FMT-XHTML-CHARSET | clinical.xhtml | `application/xhtml+xml;charset=utf-8` |
| FMT-XHTML-CHARSET-QUOTED | clinical.xhtml | `application/xhtml+xml; charset="UTF-8"` |
| FMT-XHTML-MULTIPARAM | clinical.xhtml | `application/xhtml+xml; name="clinical"; CHARSET="utf-8"` |
| FMT-XHTML-BADPARAM | clinical.xhtml | `application/xhtml+xml; name="unterminated` |
| FMT-XML-BASE | clinical_cda.xml | `application/xml` |
| FMT-XML-CASE | clinical_cda.xml | `APPLICATION/XML` |
| FMT-XML-SPACE | clinical_cda.xml | ` application/xml ` |
| FMT-XML-NAME | clinical_cda.xml | `application/xml; name="clinical document"` |
| FMT-XML-QUOTED-SEMICOLON | clinical_cda.xml | `application/xml; name="Clinical; September"` |
| FMT-XML-PARAM-ORDER | clinical_cda.xml | `application/xml; x-source=fasten; name="clinical"` |
| FMT-XML-UNKNOWN-PARAM | clinical_cda.xml | `application/xml; x-qa-version=1` |
| FMT-XML-OCTET | clinical_cda.xml | `application/octet-stream` |
| FMT-XML-ABSENT | clinical_cda.xml | `None` |
| FMT-XML-CHARSET | clinical_cda.xml | `application/xml;charset=utf-8` |
| FMT-XML-CHARSET-QUOTED | clinical_cda.xml | `application/xml; charset="UTF-8"` |
| FMT-XML-MULTIPARAM | clinical_cda.xml | `application/xml; name="clinical"; CHARSET="utf-8"` |
| FMT-XML-BADPARAM | clinical_cda.xml | `application/xml; name="unterminated` |
| FMT-DOCX-BASE | clinical.docx | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| FMT-DOCX-CASE | clinical.docx | `APPLICATION/VND.OPENXMLFORMATS-OFFICEDOCUMENT.WORDPROCESSINGML.DOCUMENT` |
| FMT-DOCX-SPACE | clinical.docx | ` application/vnd.openxmlformats-officedocument.wordprocessingml.document ` |
| FMT-DOCX-NAME | clinical.docx | `application/vnd.openxmlformats-officedocument.wordprocessingml.document; name="clinical document"` |
| FMT-DOCX-QUOTED-SEMICOLON | clinical.docx | `application/vnd.openxmlformats-officedocument.wordprocessingml.document; name="Clinical; September"` |
| FMT-DOCX-PARAM-ORDER | clinical.docx | `application/vnd.openxmlformats-officedocument.wordprocessingml.document; x-source=fasten; name="clinical"` |
| FMT-DOCX-UNKNOWN-PARAM | clinical.docx | `application/vnd.openxmlformats-officedocument.wordprocessingml.document; x-qa-version=1` |
| FMT-DOCX-OCTET | clinical.docx | `application/octet-stream` |
| FMT-DOCX-ABSENT | clinical.docx | `None` |
| FMT-DOCX-EXTRANEOUS-CHARSET | clinical.docx | `application/vnd.openxmlformats-officedocument.wordprocessingml.document; charset=utf-8` |
| FMT-DOCX-BADPARAM | clinical.docx | `application/vnd.openxmlformats-officedocument.wordprocessingml.document; name="unterminated` |
| FMT-PNG-BASE | scan_page1.png, scan_gold.json | `image/png` |
| FMT-PNG-CASE | scan_page1.png, scan_gold.json | `IMAGE/PNG` |
| FMT-PNG-SPACE | scan_page1.png, scan_gold.json | ` image/png ` |
| FMT-PNG-NAME | scan_page1.png, scan_gold.json | `image/png; name="clinical document"` |
| FMT-PNG-QUOTED-SEMICOLON | scan_page1.png, scan_gold.json | `image/png; name="Clinical; September"` |
| FMT-PNG-PARAM-ORDER | scan_page1.png, scan_gold.json | `image/png; x-source=fasten; name="clinical"` |
| FMT-PNG-UNKNOWN-PARAM | scan_page1.png, scan_gold.json | `image/png; x-qa-version=1` |
| FMT-PNG-OCTET | scan_page1.png, scan_gold.json | `application/octet-stream` |
| FMT-PNG-ABSENT | scan_page1.png, scan_gold.json | `None` |
| FMT-PNG-EXTRANEOUS-CHARSET | scan_page1.png, scan_gold.json | `image/png; charset=utf-8` |
| FMT-PNG-BADPARAM | scan_page1.png | `image/png; name="unterminated` |
| FMT-JPEG-BASE | scan_page2.jpg, scan_gold.json | `image/jpeg` |
| FMT-JPEG-CASE | scan_page2.jpg, scan_gold.json | `IMAGE/JPEG` |
| FMT-JPEG-SPACE | scan_page2.jpg, scan_gold.json | ` image/jpeg ` |
| FMT-JPEG-NAME | scan_page2.jpg, scan_gold.json | `image/jpeg; name="clinical document"` |
| FMT-JPEG-QUOTED-SEMICOLON | scan_page2.jpg, scan_gold.json | `image/jpeg; name="Clinical; September"` |
| FMT-JPEG-PARAM-ORDER | scan_page2.jpg, scan_gold.json | `image/jpeg; x-source=fasten; name="clinical"` |
| FMT-JPEG-UNKNOWN-PARAM | scan_page2.jpg, scan_gold.json | `image/jpeg; x-qa-version=1` |
| FMT-JPEG-OCTET | scan_page2.jpg, scan_gold.json | `application/octet-stream` |
| FMT-JPEG-ABSENT | scan_page2.jpg, scan_gold.json | `None` |
| FMT-JPEG-EXTRANEOUS-CHARSET | scan_page2.jpg, scan_gold.json | `image/jpeg; charset=utf-8` |
| FMT-JPEG-BADPARAM | scan_page2.jpg | `image/jpeg; name="unterminated` |
| FMT-TIFF-BASE | scan_multipage.tiff, scan_gold.json | `image/tiff` |
| FMT-TIFF-CASE | scan_multipage.tiff, scan_gold.json | `IMAGE/TIFF` |
| FMT-TIFF-SPACE | scan_multipage.tiff, scan_gold.json | ` image/tiff ` |
| FMT-TIFF-NAME | scan_multipage.tiff, scan_gold.json | `image/tiff; name="clinical document"` |
| FMT-TIFF-QUOTED-SEMICOLON | scan_multipage.tiff, scan_gold.json | `image/tiff; name="Clinical; September"` |
| FMT-TIFF-PARAM-ORDER | scan_multipage.tiff, scan_gold.json | `image/tiff; x-source=fasten; name="clinical"` |
| FMT-TIFF-UNKNOWN-PARAM | scan_multipage.tiff, scan_gold.json | `image/tiff; x-qa-version=1` |
| FMT-TIFF-OCTET | scan_multipage.tiff, scan_gold.json | `application/octet-stream` |
| FMT-TIFF-ABSENT | scan_multipage.tiff, scan_gold.json | `None` |
| FMT-TIFF-EXTRANEOUS-CHARSET | scan_multipage.tiff, scan_gold.json | `image/tiff; charset=utf-8` |
| FMT-TIFF-BADPARAM | scan_multipage.tiff | `image/tiff; name="unterminated` |
| FMT-WEBP-BASE | scan_page1.webp, scan_gold.json | `image/webp` |
| FMT-WEBP-CASE | scan_page1.webp, scan_gold.json | `IMAGE/WEBP` |
| FMT-WEBP-SPACE | scan_page1.webp, scan_gold.json | ` image/webp ` |
| FMT-WEBP-NAME | scan_page1.webp, scan_gold.json | `image/webp; name="clinical document"` |
| FMT-WEBP-QUOTED-SEMICOLON | scan_page1.webp, scan_gold.json | `image/webp; name="Clinical; September"` |
| FMT-WEBP-PARAM-ORDER | scan_page1.webp, scan_gold.json | `image/webp; x-source=fasten; name="clinical"` |
| FMT-WEBP-UNKNOWN-PARAM | scan_page1.webp, scan_gold.json | `image/webp; x-qa-version=1` |
| FMT-WEBP-OCTET | scan_page1.webp, scan_gold.json | `application/octet-stream` |
| FMT-WEBP-ABSENT | scan_page1.webp, scan_gold.json | `None` |
| FMT-WEBP-EXTRANEOUS-CHARSET | scan_page1.webp, scan_gold.json | `image/webp; charset=utf-8` |
| FMT-WEBP-BADPARAM | scan_page1.webp | `image/webp; name="unterminated` |
| ALIAS-TEXTXML | clinical_cda.xml | `text/xml; name="qa"` |
| ALIAS-XPDF | native.pdf | `application/x-pdf; name="qa"` |
| ALIAS-JPG | scan_page2.jpg, scan_gold.json | `image/jpg; name="qa"` |
| ALIAS-XTIF | scan_multipage.tiff, scan_gold.json | `image/x-tiff; name="qa"` |
| UNSUPPORTED-DOC-BASE | legacy_ole_header.doc | `application/msword` |
| UNSUPPORTED-DOC-PARAM | legacy_ole_header.doc | `application/msword; name="qa"; x-source=cerner` |
| UNSUPPORTED-RICHTEXT-BASE | mime_richtext.txt | `text/richtext` |
| UNSUPPORTED-RICHTEXT-PARAM | mime_richtext.txt | `text/richtext; name="qa"; x-source=cerner` |
| UNSUPPORTED-ENRICHED-BASE | mime_enriched.txt | `text/enriched` |
| UNSUPPORTED-ENRICHED-PARAM | mime_enriched.txt | `text/enriched; name="qa"; x-source=cerner` |
| UNSUPPORTED-DICOM-BASE | dicom_header.dcm | `application/dicom` |
| UNSUPPORTED-DICOM-PARAM | dicom_header.dcm | `application/dicom; name="qa"; x-source=cerner` |
| UNSUPPORTED-AUDIO-BASE | silent.wav | `audio/wav` |
| UNSUPPORTED-AUDIO-PARAM | silent.wav | `audio/wav; name="qa"; x-source=cerner` |
| UNSUPPORTED-VIDEO-BASE | video_header.mp4 | `video/mp4` |
| UNSUPPORTED-VIDEO-PARAM | video_header.mp4 | `video/mp4; name="qa"; x-source=cerner` |
| UNSUPPORTED-CSV-BASE | clinical.csv | `text/csv` |
| UNSUPPORTED-CSV-PARAM | clinical.csv | `text/csv; name="qa"; x-source=cerner` |
| UNSUPPORTED-EXECUTABLE-BASE | executable_header.bin | `application/x-msdownload` |
| UNSUPPORTED-EXECUTABLE-PARAM | executable_header.bin | `application/x-msdownload; name="qa"; x-source=cerner` |
| UNSUPPORTED-JSON-BASE | clinical.json | `application/json` |
| UNSUPPORTED-JSON-PARAM | clinical.json | `application/json; name="qa"; x-source=cerner` |
| UNSUPPORTED-BMP-BASE | scan_page1.bmp | `image/bmp` |
| UNSUPPORTED-BMP-PARAM | scan_page1.bmp | `image/bmp; name="qa"; x-source=cerner` |
| UNSUPPORTED-GIF-BASE | scan_page1.gif | `image/gif` |
| UNSUPPORTED-GIF-PARAM | scan_page1.gif | `image/gif; name="qa"; x-source=cerner` |
| UNSUPPORTED-HEIC-BASE | heic_header.heic | `image/heic` |
| UNSUPPORTED-HEIC-PARAM | heic_header.heic | `image/heic; name="qa"; x-source=cerner` |
| UNSUPPORTED-HEIF-BASE | heic_header.heic | `image/heif` |
| UNSUPPORTED-HEIF-PARAM | heic_header.heic | `image/heif; name="qa"; x-source=cerner` |
| UNSUPPORTED-ANIMATED-BASE | scan_animated.gif | `image/gif` |
| UNSUPPORTED-ANIMATED-PARAM | scan_animated.gif | `image/gif; name="qa"; x-source=cerner` |
| TRANSPORT-FHIRJSON-OFF | fhir_document.json | `application/fhir+json` |
| TRANSPORT-FHIRJSON-ON | fhir_document.json | `application/fhir+json` |
| TRANSPORT-FHIRJSON-PARAM | fhir_document.json | `application/fhir+json; name="QA; September"` |
| TRANSPORT-FHIRJSON-CASE | fhir_document.json | `APPLICATION/FHIR+JSON` |
| TRANSPORT-FHIRJSON-CHARSET | fhir_document.json | `application/fhir+json; charset="UTF-8"` |
| TRANSPORT-FHIRXML-OFF | fhir_document.xml | `application/fhir+xml` |
| TRANSPORT-FHIRXML-ON | fhir_document.xml | `application/fhir+xml` |
| TRANSPORT-FHIRXML-PARAM | fhir_document.xml | `application/fhir+xml; name="QA; September"` |
| TRANSPORT-FHIRXML-CASE | fhir_document.xml | `APPLICATION/FHIR+XML` |
| TRANSPORT-FHIRXML-CHARSET | fhir_document.xml | `application/fhir+xml; charset="UTF-8"` |
| TRANSPORT-NDJSON-OFF | fhir_export.ndjson | `application/fhir+ndjson` |
| TRANSPORT-NDJSON-ON | fhir_export.ndjson | `application/fhir+ndjson` |
| TRANSPORT-NDJSON-PARAM | fhir_export.ndjson | `application/fhir+ndjson; name="QA; September"` |
| TRANSPORT-NDJSON-CASE | fhir_export.ndjson | `APPLICATION/FHIR+NDJSON` |
| TRANSPORT-NDJSON-CHARSET | fhir_export.ndjson | `application/fhir+ndjson; charset="UTF-8"` |
| TRANSPORT-GZIP-OFF | clinical.txt.gz | `application/gzip` |
| TRANSPORT-GZIP-ON | clinical.txt.gz | `application/gzip` |
| TRANSPORT-GZIP-PARAM | clinical.txt.gz | `application/gzip; name="QA; September"` |
| TRANSPORT-GZIP-CASE | clinical.txt.gz | `APPLICATION/GZIP` |
| TRANSPORT-GZIP-CHARSET | clinical.txt.gz | `application/gzip; charset="UTF-8"` |
| TRANSPORT-ZIP-OFF | export.zip | `application/zip` |
| TRANSPORT-ZIP-ON | export.zip | `application/zip` |
| TRANSPORT-ZIP-PARAM | export.zip | `application/zip; name="QA; September"` |
| TRANSPORT-ZIP-CASE | export.zip | `APPLICATION/ZIP` |
| TRANSPORT-ZIP-CHARSET | export.zip | `application/zip; charset="UTF-8"` |
| TRANSPORT-MULTIPART-OFF | multipart.eml | `multipart/mixed; boundary="qa-boundary"` |
| TRANSPORT-MULTIPART-ON | multipart.eml | `multipart/mixed; boundary="qa-boundary"` |
| TRANSPORT-MULTIPART-PARAM | multipart.eml | `multipart/mixed; boundary="qa-boundary"; name="QA; September"` |
| TRANSPORT-MULTIPART-CASE | multipart.eml | `MULTIPART/MIXED; boundary="qa-boundary"` |
| TRANSPORT-MULTIPART-CHARSET | multipart.eml | `multipart/mixed; boundary="qa-boundary"; charset="UTF-8"` |
| MIME-RECURSION | unknown.bin | `application/x-unknown` |
| MIME-POLYGLOT | polyglot_header.bin | `fixture declaration` |
