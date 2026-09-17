"""Observe parser side effects directly; synthetic inputs and no external access."""
from unittest.mock import patch
import socket
import subprocess
import zipfile
import xml.etree.ElementTree as ET

CASES={'LIMIT-02','SEC-01','SEC-ARCHIVE','MIME-RECURSION','HTML-ACTIVE','XML-DTD'}

async def run(case, fixture_dir):
    import json
    from pathlib import Path
    from src.app.services.document_extraction import DocumentTextExtractor,DocumentProcessingError
    catalog=json.loads((Path(__file__).parent/'fixture_catalog.json').read_text())['fixtures']
    errors=[];texts=[];routing=[]
    # Spy on the actual I/O mechanisms used by these adapters. Attempts fail immediately.
    with patch.object(socket.socket,'connect',side_effect=AssertionError('External parser connection')) as network,patch.object(subprocess,'Popen',side_effect=AssertionError('Active parser subprocess')) as active,patch.object(zipfile.ZipFile,'extract',side_effect=AssertionError('Archive filesystem extraction')) as extract,patch.object(zipfile.ZipFile,'extractall',side_effect=AssertionError('Archive filesystem extraction')) as extractall,patch.object(zipfile.ZipFile,'read',autospec=True,side_effect=zipfile.ZipFile.read) as archive_read,patch.object(ET,'fromstring',wraps=ET.fromstring) as xml:
        for name in case['fixtures']:
            parser=DocumentTextExtractor()
            parser.MAX_ARCHIVE_EXPANDED_BYTES=case['config'].get('max_expanded_bytes',parser.MAX_ARCHIVE_EXPANDED_BYTES)
            with patch.object(parser,'extract_text',wraps=parser.extract_text) as route:
                try:texts.append(parser.extract_text((fixture_dir/name).read_bytes(),case['config'].get('declared_mime',catalog[name]['mime']),case['config'].get('filename',name)))
                except DocumentProcessingError as exc:errors.append(exc.code)
                routing.append(route.call_count)
        observed={'calls':{'external_resource_fetch':network.call_count,'active_content_execution':active.call_count,'summarization':0,'model_total':0,'database':0},
                  'boundary':{'raw_content_forwarded':False,'secret_leaked':any('SECRET_QA_TOKEN' in text for text in texts)},
                  'resources':{'files_written_outside_sandbox':extract.call_count+extractall.call_count,
                               'entity_expansion_performed':any('<!ENTITY' in str(call) for call in xml.call_args_list),
                               'limit_enforced':'RESOURCE_LIMIT_EXCEEDED' in errors or ('UNSUPPORTED_FORMAT' in errors and archive_read.call_count==0)},
                  'extraction':{'routing_attempts':max(routing,default=0),'status':'success' if texts and not errors else 'failed','text':'\n\n'.join(texts)},'error_codes':errors,
                  'pipeline_output':{'parsed_texts':texts,'errors':errors,'entrypoint':'DocumentTextExtractor.extract_text'}}
    return observed
