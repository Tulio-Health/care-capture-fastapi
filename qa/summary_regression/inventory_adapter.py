"""Actual inventory query construction and partitioning; no SQL execution.

The database boundary supplies synthetic rows. Compiled PostgreSQL predicates are
inspected separately so provider scope and NULL handling cannot disappear unnoticed.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from sqlalchemy.dialects import postgresql

CASES={'A03-EXCLUDED','A16-NULLTYPE','A16-RULESCOPE'}

async def run(case, fixture_dir):
    from src.app.db.objects.repositories import fhir_resources as module
    from src.app.services.document_type_rules_client import DocumentTypeRulesClient
    inject=case['inject'];identity=case['id']
    value=inject.get('active_exclude_rule',inject.get('exclude_reason','Insurance'))
    rule={'action':'exclude','matchTarget':'type_text','matchStrategy':'exact','matchValue':value,'sourceEmr':inject.get('rule_source_emr','all')}
    client=DocumentTypeRulesClient();client._fetch_rules=AsyncMock(return_value=[rule])
    a=SimpleNamespace(ehr_resource_id='doc-a',ehr_provider=inject.get('document_source_emr','cerner').upper(),data={'type':inject.get('document_type'),'encounterReference':'Encounter/qa','attachments':[]})
    b=SimpleNamespace(ehr_resource_id=inject.get('exclude_document_id','doc-b'),ehr_provider='CERNER',data={'type':value,'encounterReference':'Encounter/qa','attachments':[]})
    statements=[]
    async def execute(statement):
        statements.append(statement)
        return SimpleNamespace(all=lambda:[(a,None),(b,'document_type_rule:0')] if identity=='A03-EXCLUDED' else [(a,None)])
    repository=module.FhirResourcesRepository(SimpleNamespace(execute=execute))
    with patch.object(module,'get_document_type_rules_client',return_value=client):
        selected=await repository.get_document_references_with_attachments('qa-owner','qa')
    sql=str(statements[0].compile(dialect=postgresql.dialect(),compile_kwargs={'literal_binds':True}))
    scope_present='ehr_provider AS VARCHAR' in sql and "= 'CERNER'" in sql
    null_safe='CASE WHEN coalesce(' in sql and 'false)' in sql
    return {'calls':{'database':0,'model_total':0},
            'inventory':{'unknown_type_retained':a in selected and null_safe,'cross_connector_exclusion':not(scope_present and a in selected)},
            'coverage':{'excluded_documents':repository.document_inventory['excluded_documents'],'exclusions_have_reasons':all(item['reason'] for item in repository.document_inventory['exclusions'])},
            'pipeline_output':{'compiled_query':sql,'inventory':repository.document_inventory,'selected_ids':[item.ehr_resource_id for item in selected],'rule_provenance':repository.eligibility_provenance,'qualification':'SQL construction and result partitioning; database execution is not qualified by this test'}}
