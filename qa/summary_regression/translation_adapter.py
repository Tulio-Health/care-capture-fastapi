"""Translation preservation guards with scripted translation/verifier boundary responses."""
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch

CASES={'A07-SCALARS','A07-PROSE','A07-ARRAY','A07-TYPE','A07-EMPTY','A07-METADATA','A07-MIXED','UI-04'}

async def run(case,fixture_dir):
    from src.app.chains.translation.chain import TranslationChain
    from src.app.models.translation import TranslatedSummary
    from src.app.services.document_extraction import DocumentProcessingError
    from src.app.services.summary_outcomes import MESSAGES
    identity=case['id'];data=json.loads((fixture_dir/'translation_adversarial.json').read_text())
    source=deepcopy(data['source'])
    source.update(data={'active':False,'dose':5},summary_metadata={'source_document_ids':['doc-a'],'evidence_quotes':['No fracture.'],'processing_outcome':'complete'})
    if identity=='UI-04':
        source['summary_text']=MESSAGES['partial']+'\n\n'+source['summary_text'];source['summary_metadata']['processing_outcome']='partial'
    candidate=TranslatedSummary(summary_text=source['summary_text'],medications=deepcopy(source['medications']),data=deepcopy(source['data']))
    semantic_failure=False
    if identity=='A07-SCALARS':candidate.data={'active':True,'dose':50}
    elif identity=='A07-TYPE':candidate.data={'active':'false','dose':5}
    elif identity=='A07-EMPTY':candidate.summary_text=''
    elif identity=='A07-ARRAY':candidate.medications=data['reordered'];semantic_failure=True
    elif identity=='A07-PROSE':candidate.summary_text='Fracture present. Left knee. Follow-up 2026-10-01.';semantic_failure=True
    elif identity=='A07-MIXED':candidate.data={'active':'false','dose':5};candidate.summary_text='Sin fractura. Rodilla derecha. Seguimiento 2026-10-01.'
    chain=TranslationChain();chain._model=object();chain._agent=SimpleNamespace(run=AsyncMock(return_value=SimpleNamespace(output=candidate)))
    verifier=AsyncMock(side_effect=DocumentProcessingError('GROUNDING_VALIDATION_FAILED') if semantic_failure else None)
    with patch('src.app.services.clinical_grounding.verify_grounding',new=verifier):
        result=await chain.translate_conversation_summary(source,'es')
    fields=('medications','data')
    preserved=all(result.get(k)==source.get(k) for k in fields)
    narrative_preserved=source['summary_text'] in result['summary_text']
    return {'calls':{'database':0,'model_total':chain._agent.run.await_count+verifier.await_count},
            'translation':{'accepted':result.get('translation_status')=='complete','original_preserved':preserved and narrative_preserved,'limitation_disclosed':result.get('translation_status') in {'partial','unavailable'} and ('original' in result['summary_text'].lower()),'valid_fields_retained':candidate.summary_text in result['summary_text'],'metadata_unchanged':source['summary_metadata']==result['summary_metadata'],'evidence_ids_unchanged':source['summary_metadata']['source_document_ids']==result['summary_metadata']['source_document_ids']},
            'outcome':result['summary_metadata']['processing_outcome'],
            'display':{'warning_preserved':MESSAGES['partial'] in result['summary_text']},
            'clinical':{'unsupported_claims_published':int(not preserved or (semantic_failure and not narrative_preserved))},
            'pipeline_output':result}
