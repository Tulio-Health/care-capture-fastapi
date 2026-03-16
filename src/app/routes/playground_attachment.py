"""Playground router for attachment summarization — dev-only, no DB storage."""

import json
import secrets
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from src.app.chains.attachment_summarization.chain import (
    _EXTRACTION_SYSTEM_PROMPT,
    _SYNTHESIS_SYSTEM_PROMPT,
)
from src.app.common.logging import get_logger
from src.app.core import get_settings
from src.app.models.attachment_summarization import DocumentAttachment
from src.app.models.playground_attachment_summarization import (
    PlaygroundAttachmentRequest,
)
from src.app.services.document_extraction import DocumentTextExtractor
from src.app.services.summarization.playground_attachment_summarization import (
    PlaygroundAttachmentSummarizationService,
)

logger = get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


def verify_playground_key(x_playground_key: str = Header(...)) -> None:
    """FastAPI dependency — validates the X-Playground-Key header."""
    settings = get_settings()
    if not settings.PLAYGROUND_API_KEY:
        raise HTTPException(status_code=503, detail="Playground API key not configured")
    if not secrets.compare_digest(
        x_playground_key.encode(), settings.PLAYGROUND_API_KEY.encode()
    ):
        raise HTTPException(status_code=401, detail="Invalid playground API key")


# ---------------------------------------------------------------------------
# HTML playground (built once at import time)
# ---------------------------------------------------------------------------


def _build_html() -> str:
    ext_js = json.dumps(_EXTRACTION_SYSTEM_PROMPT)
    sys_js = json.dumps(_SYNTHESIS_SYSTEM_PROMPT)
    return (
        """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Attachment Summarization Playground</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f0f2f5;height:100vh;overflow:hidden;display:flex;flex-direction:column}
.header{background:#1a1a2e;color:#fff;padding:10px 20px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0}
.header h1{font-size:17px;font-weight:600}
.badge{background:#e74c3c;color:#fff;font-size:10px;padding:2px 8px;border-radius:10px;margin-left:10px;letter-spacing:.5px;text-transform:uppercase}
.layout{display:flex;flex:1;overflow:hidden}
.divider{width:1px;background:#e5e7eb;flex-shrink:0}
.left-panel{width:44%;display:flex;flex-direction:column;background:#fff}
.right-panel{flex:1;display:flex;flex-direction:column;background:#fff;min-height:0}
.panel-body{flex:1;overflow-y:auto}
.section{padding:12px 16px;border-bottom:1px solid #f0f0f0}
.sec-label{font-size:10px;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:.8px;margin-bottom:7px}
textarea{width:100%;border:1px solid #e0e0e0;border-radius:4px;padding:8px;font-family:'Monaco','Menlo',monospace;font-size:11px;resize:vertical;line-height:1.5;color:#1f2937}
textarea:focus,input:focus{outline:none;border-color:#3b82f6;box-shadow:0 0 0 2px rgba(59,130,246,.15)}
.hint{font-size:10px;color:#9ca3af;margin-bottom:5px;line-height:1.4}
input[type=text],input[type=password]{width:100%;padding:7px 10px;border:1px solid #e0e0e0;border-radius:4px;font-size:13px;color:#1f2937}
.row{display:flex;gap:8px}
.col{flex:1}
.f-label{font-size:12px;color:#4b5563;margin-bottom:3px;display:block}
.panel-footer{padding:12px 16px;border-top:1px solid #f0f0f0;background:#fafafa;flex-shrink:0}
.run-btn{width:100%;background:#2563eb;color:#fff;border:none;padding:10px;border-radius:6px;font-size:14px;font-weight:500;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:8px;transition:background .15s}
.run-btn:hover:not(:disabled){background:#1d4ed8}
.run-btn:disabled{background:#93c5fd;cursor:not-allowed}
.spinner{width:14px;height:14px;border:2px solid rgba(255,255,255,.4);border-top-color:#fff;border-radius:50%;display:none;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.is-loading .spinner{display:block}
.is-loading .btn-label{display:none}
.tabs{display:flex;border-bottom:1px solid #f0f0f0}
.tab-btn{padding:7px 16px;font-size:12px;cursor:pointer;color:#6b7280;background:none;border:none;border-bottom:2px solid transparent;margin-bottom:-1px}
.tab-btn.active{color:#2563eb;border-bottom-color:#2563eb;font-weight:600}
.pane{display:none;padding-top:10px}
.pane.active{display:block}
.drop-zone{border:2px dashed #e0e0e0;border-radius:6px;padding:20px;text-align:center;cursor:pointer;color:#9ca3af;font-size:13px;transition:all .15s}
.drop-zone:hover,.drop-zone.drag-over{border-color:#3b82f6;background:#eff6ff;color:#374151}
.file-list{margin-top:8px}
.file-item{font-size:11px;color:#4b5563;padding:3px 0;display:flex;align-items:center;gap:5px}
.results-section{flex:1;display:flex;flex-direction:column;border-top:1px solid #f0f0f0;min-height:0}
.results-bar{display:flex;align-items:center;justify-content:space-between;padding:7px 16px;background:#fafafa;border-bottom:1px solid #f0f0f0;flex-shrink:0}
.results-label{font-size:10px;font-weight:700;color:#9ca3af;text-transform:uppercase;letter-spacing:.8px}
.copy-btn{font-size:11px;color:#2563eb;background:none;border:none;cursor:pointer;padding:2px 8px;border-radius:3px}
.copy-btn:hover{background:#eff6ff}
.output-box{flex:1;overflow-y:auto;background:#1e1e2e;color:#cdd6f4;padding:14px 16px;font-family:'Monaco','Menlo',monospace;font-size:11.5px;line-height:1.6;white-space:pre-wrap;min-height:0}
.ph{color:#585b70;font-style:italic}
.status-line{padding:5px 16px;font-size:11px;color:#6b7280;background:#fafafa;border-top:1px solid #f0f0f0;flex-shrink:0;min-height:22px}
.status-line.err{color:#f38ba8}
.status-line.ok{color:#a6e3a1}
.jk{color:#89b4fa}.js{color:#a6e3a1}.jn{color:#fab387}.jb{color:#cba6f7}.jz{color:#f38ba8}
</style>
</head>
<body>
<div class="header">
  <span style="display:flex;align-items:center">
    <h1>Attachment Summarization Playground</h1>
    <span class="badge">Dev Only</span>
  </span>
  <span style="font-size:11px;color:#6b7280">Stateless &bull; No data stored</span>
</div>

<div class="layout">
  <!-- LEFT: System Prompts + Auth -->
  <div class="left-panel">
    <div class="panel-body">
      <div class="section">
        <div class="sec-label">Extraction System Prompt</div>
        <div class="hint">Optional override for the per-document extraction prompt (map phase). Leave as-is to use the production default.</div>
        <textarea id="ext-prompt" rows="16" spellcheck="false"></textarea>
      </div>
      <div class="section">
        <div class="sec-label">Synthesis System Prompt</div>
        <div class="hint">Optional override for the synthesis agent's system prompt (reduce phase). Leave as-is to use the production default.</div>
        <textarea id="sys-prompt" rows="16" spellcheck="false"></textarea>
      </div>
      <div class="section">
        <div class="sec-label">Authentication</div>
        <label class="f-label">Playground API Key (X-Playground-Key)</label>
        <input type="password" id="api-key" placeholder="Enter playground API key" autocomplete="off">
      </div>
    </div>
    <div class="panel-footer">
      <button class="run-btn" id="run-btn" onclick="runPlayground()">
        <div class="spinner"></div>
        <span class="btn-label">&#9654;&nbsp; Run</span>
      </button>
    </div>
  </div>

  <div class="divider"></div>

  <!-- RIGHT: Input + Results -->
  <div class="right-panel">
    <!-- Appointment context -->
    <div class="section" style="flex-shrink:0">
      <div class="sec-label">Appointment Context</div>
      <div class="row">
        <div class="col"><label class="f-label">Date</label><input type="text" id="appt-date" placeholder="e.g. 2024-01-15"></div>
        <div class="col"><label class="f-label">Purpose</label><input type="text" id="appt-purpose" placeholder="e.g. Annual Physical"></div>
        <div class="col"><label class="f-label">Provider</label><input type="text" id="appt-provider" placeholder="e.g. Dr. Smith"></div>
      </div>
    </div>

    <!-- Document input -->
    <div class="section" style="flex-shrink:0">
      <div class="sec-label">Document Input</div>
      <div class="tabs">
        <button class="tab-btn active" id="tab-paste" onclick="switchTab('paste')">Paste Text</button>
        <button class="tab-btn" id="tab-upload" onclick="switchTab('upload')">Upload File</button>
      </div>
      <div class="pane active" id="pane-paste">
        <textarea id="doc-text" rows="9" spellcheck="false" placeholder="Paste medical document text here..."></textarea>
      </div>
      <div class="pane" id="pane-upload">
        <div class="drop-zone" id="drop-zone"
             onclick="document.getElementById('file-input').click()"
             ondragover="onDragOver(event)" ondrop="onDrop(event)"
             ondragleave="document.getElementById('drop-zone').classList.remove('drag-over')">
          <div>&#128194; Click to select files or drag &amp; drop</div>
          <div style="font-size:11px;margin-top:4px">PDF &bull; DOCX &bull; TXT &bull; XML</div>
        </div>
        <input type="file" id="file-input" multiple accept=".pdf,.docx,.doc,.txt,.xml"
               style="display:none" onchange="onFileSelect(this.files)">
        <div class="file-list" id="file-list"></div>
      </div>
    </div>

    <!-- Results -->
    <div class="results-section">
      <div class="results-bar">
        <span class="results-label">Results</span>
        <button class="copy-btn" onclick="copyOutput()">&#128203; Copy JSON</button>
      </div>
      <div class="output-box" id="output-box"><span class="ph">Results will appear here after you click Run&hellip;</span></div>
      <div class="status-line" id="status-line"></div>
    </div>
  </div>
</div>

<script>
const EXT = """
        + ext_js
        + """;
const SYS = """
        + sys_js
        + """;

let selFiles = [];
let curTab = 'paste';

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('ext-prompt').value = EXT;
  document.getElementById('sys-prompt').value = SYS;
  const k = sessionStorage.getItem('pg_key');
  if (k) document.getElementById('api-key').value = k;
});

function switchTab(t) {
  curTab = t;
  ['paste','upload'].forEach(x => {
    document.getElementById('tab-'+x).classList.toggle('active', x===t);
    document.getElementById('pane-'+x).classList.toggle('active', x===t);
  });
}

function onFileSelect(files) { selFiles = Array.from(files).filter(f=>f.size>0); renderFiles(); }
function onDragOver(e) { e.preventDefault(); document.getElementById('drop-zone').classList.add('drag-over'); }
function onDrop(e) {
  e.preventDefault();
  document.getElementById('drop-zone').classList.remove('drag-over');
  selFiles = Array.from(e.dataTransfer.files).filter(f=>f.size>0);
  renderFiles();
}
function renderFiles() {
  document.getElementById('file-list').innerHTML = selFiles.map(f =>
    `<div class="file-item"><span>&#128196;</span><span>${esc(f.name)}</span><span style="color:#9ca3af">(${(f.size/1024).toFixed(1)} KB)</span></div>`
  ).join('');
}

async function runPlayground() {
  const apiKey = document.getElementById('api-key').value.trim();
  if (!apiKey) { alert('Please enter your Playground API key.'); return; }

  const docText = document.getElementById('doc-text').value.trim();
  if (curTab==='paste' && !docText) { alert('Please paste some document text.'); return; }
  if (curTab==='upload' && selFiles.length===0) { alert('Please select at least one file.'); return; }

  sessionStorage.setItem('pg_key', apiKey);
  setLoading(true);
  setStatus('', '');

  const fd = new FormData();
  fd.append('extraction_system_prompt', document.getElementById('ext-prompt').value);
  fd.append('synthesis_system_prompt', document.getElementById('sys-prompt').value);
  fd.append('appointment_date', document.getElementById('appt-date').value.trim() || 'N/A');
  fd.append('appointment_purpose', document.getElementById('appt-purpose').value.trim() || 'N/A');
  fd.append('provider_name', document.getElementById('appt-provider').value.trim() || 'N/A');
  if (curTab==='paste') {
    fd.append('documents_text', docText);
  } else {
    selFiles.forEach(f => fd.append('files', f));
  }

  const t0 = Date.now();
  try {
    const res = await fetch('/care-capture/playground-attachment-summary', {
      method: 'POST',
      headers: {'X-Playground-Key': apiKey},
      body: fd
    });
    const elapsed = ((Date.now()-t0)/1000).toFixed(2);
    const data = await res.json();
    if (!res.ok) {
      const msg = data.detail || JSON.stringify(data);
      setStatus('Error ' + res.status + ': ' + msg, 'err');
      document.getElementById('output-box').innerHTML = '<span class="ph">Request failed — see status bar.</span>';
      return;
    }
    renderOutput(data);
    setStatus('Completed in ' + elapsed + 's  \u00b7  request_id: ' + (data.request_id||'?'), 'ok');
  } catch(err) {
    setStatus('Network error: ' + err.message, 'err');
  } finally {
    setLoading(false);
  }
}

function renderOutput(obj) {
  const box = document.getElementById('output-box');
  box.innerHTML = highlight(JSON.stringify(obj, null, 2));
  box.scrollTop = 0;
}

function highlight(s) {
  const e = s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  return e(s).replace(
    /("(\\u[0-9a-fA-F]{4}|\\[^u]|[^\\"])*"(\\s*:)?|\\b(true|false|null)\\b|-?\\d+(?:\\.\\d*)?(?:[eE][+\\-]?\\d+)?)/g,
    m => {
      let c='jn';
      if(/^"/.test(m)) c=/:$/.test(m)?'jk':'js';
      else if(/true|false/.test(m)) c='jb';
      else if(/null/.test(m)) c='jz';
      return '<span class="'+c+'">'+m+'</span>';
    }
  );
}

function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function setLoading(on) {
  const btn = document.getElementById('run-btn');
  btn.disabled = on;
  btn.classList.toggle('is-loading', on);
}

function setStatus(msg, cls) {
  const el = document.getElementById('status-line');
  el.textContent = msg;
  el.className = 'status-line' + (cls?' '+cls:'');
}

async function copyOutput() {
  const text = document.getElementById('output-box').innerText;
  try {
    await navigator.clipboard.writeText(text);
    setStatus('Copied to clipboard', 'ok');
    setTimeout(()=>setStatus('',''), 2000);
  } catch { setStatus('Copy failed — try selecting and copying manually', 'err'); }
}
</script>
</body>
</html>"""
    )


PLAYGROUND_HTML = _build_html()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/care-capture/playground-attachment", response_class=HTMLResponse)
async def playground_attachment_page() -> HTMLResponse:
    """Serve the self-contained HTML playground (no auth required)."""
    return HTMLResponse(content=PLAYGROUND_HTML)


@router.post("/care-capture/playground-attachment-summary")
async def playground_attachment_summary(
    extraction_system_prompt: Optional[str] = Form(default=None),
    synthesis_system_prompt: Optional[str] = Form(default=None),
    appointment_date: str = Form(default="N/A"),
    appointment_purpose: str = Form(default="N/A"),
    provider_name: str = Form(default="N/A"),
    documents_text: Optional[str] = Form(default=None),
    files: Optional[List[UploadFile]] = File(default=None),
    _: None = Depends(verify_playground_key),
) -> JSONResponse:
    """
    Run attachment summarization via the production chain with optional
    extraction and synthesis system prompt overrides.

    Accepts either:
    - ``documents_text`` form field (paste mode), or
    - one or more uploaded ``files`` (upload mode — text is extracted server-side).

    Each file becomes its own DocumentAttachment, preserving per-document structure
    for the map-reduce pipeline. Protected by ``X-Playground-Key`` header.
    """
    extractor = DocumentTextExtractor()
    documents: List[DocumentAttachment] = []

    if files:
        real_files = [f for f in files if f.filename and f.size and f.size > 0]
        if not real_files and not documents_text:
            raise HTTPException(
                status_code=422, detail="No document text or valid files provided"
            )

        for upload in real_files:
            content = await upload.read()
            if not content:
                continue
            inferred_type = extractor._infer_type_from_filename(upload.filename or "")
            content_type = (
                inferred_type
                if inferred_type != "application/octet-stream"
                else (upload.content_type or "text/plain")
            )
            try:
                text = extractor.extract_text(content, content_type, upload.filename)
                documents.append(
                    DocumentAttachment(
                        file_path=f"playground://{upload.filename}",
                        content_type=content_type,
                        title=upload.filename,
                        file_name=upload.filename,
                        size=upload.size,
                        extracted_text=text,
                    )
                )
            except Exception as exc:
                logger.warning("Failed to extract text from %s: %s", upload.filename, exc)
                documents.append(
                    DocumentAttachment(
                        file_path=f"playground://{upload.filename}",
                        content_type=content_type,
                        title=upload.filename,
                        file_name=upload.filename,
                        size=upload.size,
                        extracted_text="",
                        extraction_error=str(exc),
                    )
                )

    if not documents:
        if not documents_text or not documents_text.strip():
            raise HTTPException(
                status_code=422, detail="No document text or files provided"
            )
        documents.append(
            DocumentAttachment(
                file_path="playground://paste",
                content_type="text/plain",
                title="Pasted Document",
                extracted_text=documents_text,
            )
        )

    request = PlaygroundAttachmentRequest(
        extraction_system_prompt=extraction_system_prompt,
        synthesis_system_prompt=synthesis_system_prompt,
        appointment_date=appointment_date,
        appointment_purpose=appointment_purpose,
        provider_name=provider_name,
    )

    service = PlaygroundAttachmentSummarizationService()
    response = await service.summarize(request, documents)
    return JSONResponse(content=response.model_dump(mode="json"))
