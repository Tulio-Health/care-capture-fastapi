"""Exercise the real bounded downloader using an in-memory streaming body."""
import asyncio
import io
import time
from types import SimpleNamespace
from unittest.mock import Mock,patch

CASES={'A12-STORAGE','LIMIT-01','A09-IO','SEC-02'}

async def run(case,fixture_dir):
    from src.app.utils.s3_client import S3DocumentClient
    from src.app.services.document_extraction import DocumentProcessingError,DocumentTextExtractor
    identity=case['id'];inject=case['inject'];config=case['config']
    data=(fixture_dir/'clinical_utf8.txt').read_bytes()*inject.get('download',{}).get('stream_repeat_fixture',1)
    class Body(io.BytesIO):
        bytes_read=0
        def read(self,size=-1):
            if identity=='A09-IO':time.sleep(inject['download_delay_ms']/1000)
            assert size>=0,'Unbounded stream read'
            value=super().read(size);self.bytes_read+=len(value);return value
    body=Body(data);sdk=SimpleNamespace(get_object=Mock(return_value={'Body':body,'ContentLength':inject.get('download',{}).get('declared_length',len(data)),'ETag':'qa-version'}))
    client=S3DocumentClient(allowed_prefixes=['s3://qa-bucket/']);client.s3_client=sdk
    gaps=[];last=time.monotonic();finished=False
    async def heartbeat():
        nonlocal last
        while not finished:
            await asyncio.sleep(.005);now=time.monotonic();gaps.append((now-last)*1000);last=now
    task=asyncio.create_task(heartbeat());errors=[];content=None
    try:
        with patch.object(DocumentTextExtractor,'MAX_FILE_SIZE',config.get('max_download_bytes',DocumentTextExtractor.MAX_FILE_SIZE)):
            try:content=await client.download_document(inject.get('attachment_uri',inject.get('download_redirect','s3://qa-bucket/clinical.txt')))
            except DocumentProcessingError as exc:errors.append(exc.code)
            except ValueError:errors.append('INVALID_STORAGE_URI')
    finally:
        finished=True;await task
        if not body.closed:body.close()
    return {'outcome':'success' if content else 'unavailable','error_codes':errors,
            'calls':{'summarization':0,'database':0,'model_total':0,'document_download':sdk.get_object.call_count,'unapproved_fetch':sdk.get_object.call_count if identity=='SEC-02' else 0},
            'boundary':{'credentials_forwarded':identity=='SEC-02' and sdk.get_object.call_count>0},
            'io':{'bytes_read':body.bytes_read},'resources':{'heartbeat_max_gap_ms':max(gaps,default=0),'body_closed':body.closed},
            'pipeline_output':{'downloaded_bytes':len(content) if content else 0,'errors':errors}}
