"""Published desktop literature DTOs, authority boundaries and actual local wiring."""
import copy
from importlib import metadata
import io
import json
import os
from pathlib import Path
import sys
import threading
import time
from uuid import uuid4

import pytest

from suan.agent.levels import DESKTOP_ONLY, OPERATIONS, TOOL_USES
from suan.desktop_bridge import schema
from suan.desktop_bridge.literature import METHODS, child_environment, request_sha256
from suan.desktop_bridge.protocol import BridgeError
from suan.desktop_bridge.server import Bridge
from suan.graph.schema import check_value
from suan.literature.pdf import checksum
from suan.scripting import ScriptError
from suan.scripting.headless import connect
from test_desktop_bridge import InProcessBridge, ProcessBridge
from test_literature_pdf import make_pdf, pdf_python
from test_literature_store import RIGHTS


@pytest.fixture(autouse=True)
def private_state(tmp_path, monkeypatch):
    monkeypatch.setenv('STK_PROFILES_FILE', str(tmp_path/'profiles'/'connections.json'))
    monkeypatch.setenv('STK_STATE_DIR', str(tmp_path/'no-local-runtime'))
    monkeypatch.setenv('STK_TOKEN_PLAN_API_KEY', '')
    for name in ('STK_TOKEN_PLAN_MODEL','STK_RUNTIME_URL','STK_RUNTIME_TOKEN'):
        monkeypatch.delenv(name, raising=False)


def uid():
    return str(uuid4())


def job(bridge, action, *, operation_id=None, **params):
    params={'operation_id':operation_id or uid(), **params}
    admission=bridge.call('literature.'+action,params)['operation']
    assert admission['operation_id']==params['operation_id']
    assert admission['action']==action and admission['request_sha256']==request_sha256(action,params)
    end=time.monotonic()+700
    while admission['state']=='running' and time.monotonic()<end:
        time.sleep(.02)
        admission=bridge.call('literature.operations.get',{'operation_id':params['operation_id']})['operation']
    assert admission['state']=='completed', admission
    result=bridge.call('literature.operations.result',{'operation_id':params['operation_id'],
        'expected_request_sha256':admission['request_sha256']})
    assert result['operation']==admission
    assert checksum(result['result'])==admission['result_sha256']
    return admission,result['result'],params


def examples():
    ident='00000000-0000-0000-0000-000000000001';sha='a'*64;corpus='local_'+'b'*32
    base={'format':'stk.literature-citation/1','version_id':ident,'source_sha256':sha,
        'extraction_id':sha,'paragraph_id':sha,'text_sha256':sha,'page_index':0,'start':0,'end':1}
    cite={'format':'stk.literature-collection-citation/1','corpus_id':corpus,'database_id':ident,
        'corpus_generation':0,'dense_generation':sha,'inner':base,'evidence_sha256':sha}
    op={'operation_id':ident}
    return {
        'info':{},'corpora.list':{},'corpora.info':{'corpus_id':corpus},'encoder.info':{},
        'corpora.create':{**op,'name':'Owned'},'encoder.review':{**op,'assets':'/tmp/owned'},
        'encoder.select':{**op,'review_id':ident,'review_sha256':sha,'expected_generation':0},
        'import.review':{**op,'corpus_id':corpus,'source':'/tmp/owned.pdf','document_id':ident,'title':'Owned','authorization':RIGHTS},
        'import.commit':{**op,'review_id':ident,'review_sha256':sha},
        'import.recover':{**op,'corpus_id':corpus,'original_operation_id':ident},
        'versions.list':{'corpus_id':corpus},'versions.revoke':{**op,'corpus_id':corpus,'version_id':ident},
        'index.start':{**op,'corpus_id':corpus,'version_id':ident},
        'dense.build':{**op,'corpus_id':corpus,'expected_generation':0,'encoder_generation':0},
        'search':{**op,'scopes':[corpus],'query':'sunlight','encoder_generation':0},
        'citations.resolve':{**op,'scopes':[corpus],'citation':cite},
        'pages.render':{**op,'scopes':[corpus],'citation':cite},
        'operations.get':op,'operations.list':{},'operations.result':{**op,'expected_request_sha256':sha}}


def test_exact_registration_is_desktop_only_and_headless_cannot_dispatch(tmp_path, monkeypatch):
    expected={'literature.'+action for action in METHODS}
    assert len(expected)==20 and set(examples())==METHODS
    bridge=Bridge(tmp_path/'desktop', writer=io.BytesIO(), strict=True)
    try:
        assert {name for name in bridge.methods if name.startswith('literature.')}==expected
        assert {name for name in schema.method_names() if name.startswith('literature.')}==expected
        assert expected<=DESKTOP_ONLY.keys() and not expected&OPERATIONS.keys()
        assert not expected&{op for operations in TOOL_USES.values() for op in operations}
        assert not expected&bridge.script_catalog()['operations'].keys()
        for action,params in examples().items():
            with pytest.raises(BridgeError) as error:
                bridge.script_call('literature.'+action,params,threading.Event())
            assert error.value.code=='unsupported'
        assert bridge._literature is None
    finally:bridge.shutdown()
    monkeypatch.setattr('suan.desktop_bridge.literature.LiteratureService',lambda *a,**k:pytest.fail('Headless constructed literature'))
    with connect(state_dir=tmp_path/'headless') as api:
        for action,params in examples().items():
            with pytest.raises(ScriptError) as error:api.call('literature.'+action,**params)
            assert error.value.code=='unsupported'
    assert not (tmp_path/'headless'/'literature').exists()


def test_constructor_hello_reopen_shutdown_and_passive_reads_never_spawn_or_build(tmp_path, monkeypatch):
    from suan.desktop_bridge import literature
    monkeypatch.setattr(literature,'WorkerProcess',lambda *a,**k:pytest.fail('Passive read spawned worker'))
    monkeypatch.setattr(literature.Library,'__init__',lambda *a,**k:pytest.fail('Passive empty read constructed Library'))
    real=literature.LiteratureService
    for turn in range(2):
        with monkeypatch.context() as bounded:
            bounded.setattr(literature,'LiteratureService',lambda *a,**k:pytest.fail('Construction/hello eagerly made service'))
            bridge=InProcessBridge(tmp_path/'desktop')
            hello=bridge.call('hello',{'protocol':1,'resume_transfers':False})
            assert 'literature.info' in hello['methods'] and bridge.bridge._literature is None
            if turn==0:bridge.close();continue
        assert literature.LiteratureService is real
        try:
            assert bridge.call('literature.info')=={'corpora':[],'encoder_generation':0,'encoder_configured':False,'active_jobs':0}
            assert bridge.call('literature.corpora.list')['corpora']==[]
            assert bridge.call('literature.encoder.info')=={'generation':0,'selection':None}
            assert bridge.call('literature.operations.get',{'operation_id':uid()})=={'operation':None}
            assert bridge.call('literature.operations.list')=={'operations':[]}
        finally:bridge.close()
    assert not (tmp_path/'desktop'/'literature').exists()


def test_stdio_passive_protocol_does_not_create_literature(tmp_path):
    env=child_environment()
    env.update(STK_PROFILES_FILE=str(tmp_path/'profiles.json'),STK_STATE_DIR=str(tmp_path/'no-runtime'))
    bridge=ProcessBridge(tmp_path/'stdio',env=env)
    try:
        assert 'literature.info' in bridge.call('hello',{'protocol':1,'resume_transfers':False})['methods']
        assert bridge.call('literature.info')['corpora']==[]
        assert bridge.call('literature.operations.list')=={'operations':[]}
    finally:assert bridge.close()==0
    assert not (tmp_path/'stdio'/'literature').exists()


def test_only_host_constructor_selects_interpreters_and_shutdown_reaps_created_service(tmp_path, monkeypatch):
    bridge=InProcessBridge(tmp_path/'desktop',literature_parser_python='/tmp/trusted-parser',literature_encoder_python='/tmp/trusted-encoder')
    try:
        assert bridge.bridge._literature is None
        error=bridge.error('literature.encoder.review',{'operation_id':uid(),'assets':'/tmp/assets','python':'/tmp/arbitrary'})
        assert error['code']=='invalid_params'
        service=bridge.bridge._literature
        assert service.parser_python=='/tmp/trusted-parser' and service.encoder_python=='/tmp/trusted-encoder'
        assert service.python==sys.executable and not service.root.exists()
        called=[]
        monkeypatch.setattr(service,'shutdown',lambda:called.append(True))
        bridge.close();assert called==[True]
        with pytest.raises(BridgeError) as error:bridge.bridge.literature_call('info',{})
        assert error.value.code=='shutting_down'
    finally:bridge.close()


@pytest.mark.parametrize('action',sorted(METHODS))
def test_published_params_are_closed_and_action_specific(action):
    params=examples()[action];method='literature.'+action
    assert schema.validate_params(method,params)==[]
    assert schema.validate_params(method,{**params,'encoder_python':'/tmp/arbitrary'})
    if params:
        assert schema.validate_params(method,{key:value for key,value in params.items() if key!=next(iter(params))})


@pytest.mark.parametrize('action,field,value',[
    ('dense.build','expected_generation',True),('dense.build','timeout',0),('dense.build','timeout',3601),
    ('dense.build','encoder_generation',1.5),('encoder.review','assets','relative'),
    ('search','scopes',[]),('search','scopes',['local_'+'b'*32]*2),('search','limit',21),
    ('search','query',''),('pages.render','long_edge',255),('pages.render','long_edge',2049),
    ('operations.result','expected_request_sha256','A'*64),('corpora.create','operation_id','ABCDEF00-0000-0000-0000-000000000001'),
    ('import.review','authorization',{'basis':'paywalled','evidence':'owned','approved_by':'owner'})])
def test_published_params_reject_type_path_scope_and_budget_counterexamples(action,field,value):
    assert schema.validate_params('literature.'+action,{**examples()[action],field:value})


def test_completed_result_union_checks_action_and_exact_shapes():
    import jsonschema
    for action in METHODS:
        contract=schema.method_contract('literature.'+action)
        for shape in contract.values():jsonschema.Draft202012Validator.check_schema(shape)
    operation={'operation_id':uid(),'action':'corpora.create','request_sha256':'a'*64,
        'result_sha256':'b'*64,'error':None,'state':'completed'}
    result={'operation':operation,'result':{'corpus_id':'local_'+'c'*32,'database_id':uid()}}
    shape=schema.method_contract('literature.operations.result')['result']
    assert check_value(result,shape)==[]
    jsonschema.validate(result,shape)
    invalid=[{**result,'unexpected':True},
        {**result,'result':{'arbitrary':'json'}},
        {**result,'operation':{**operation,'action':'encoder.select'}},
        {**result,'operation':{**operation,'state':'running'}},
        {**result,'operation':{**operation,'result_sha256':None}},
        {**result,'result':{**result['result'],'extra':1}}]
    for value in invalid:
        assert check_value(value,shape)
        with pytest.raises(jsonschema.ValidationError):jsonschema.validate(value,shape)
    malformed=copy.deepcopy(examples()['citations.resolve']);malformed['citation']['inner']['page_index']=256
    assert schema.validate_params('literature.citations.resolve',malformed)


@pytest.mark.parametrize('path',['/tmp/owned','C:\\Users\\owner\\assets','\\\\server\\share\\assets'])
def test_path_shape_preserves_supported_host_platform_forms(path):
    assert not schema.validate_params('literature.encoder.review',{'operation_id':uid(),'assets':path})


def test_review_result_preserves_typed_historical_qwen_metadata():
    from suan.literature.encoder_profiles import QWEN_RECIPE
    sha='a'*64
    identity={'assets_sha256':sha,'recipe':dict(QWEN_RECIPE),'runtime':{'python':'historical Python',
        'platform':'historical platform','machine':'historical machine','worker_sha256':sha,
        'packages':{'owned-package':{'version':'1','record_sha256':None}}}}
    review={'format':'stk.literature-encoder-review/1','assets':'/tmp/assets','assets_sha256':sha,
        'python':'/tmp/python','identity':identity,'fingerprint':sha}
    shape=schema.method_contract('literature.operations.result')['result']
    result={'operation':{'operation_id':uid(),'action':'encoder.review','request_sha256':sha,
        'result_sha256':sha,'error':None,'state':'completed'},'result':review}
    assert check_value(result,shape)==[]
    for value in (True,1024.5,0,65537):
        bad=copy.deepcopy(result);bad['result']['identity']['recipe']['dimensions']=value
        assert check_value(bad,shape)
    bad=copy.deepcopy(result);bad['result']['identity']['runtime']['packages']['owned-package']['arbitrary']=True
    assert check_value(bad,shape)


def test_resolved_result_keeps_pdfium_version_reading_order_and_paragraph_recipe():
    """The actual parser's full identity is preserved by the published closed DTO."""
    sha='a'*64;citation=examples()['citations.resolve']['citation']
    parser={'adapter':'stk.pdfium-character-stream/1','pypdfium2':'5.14.0','pdfium':'156.0.8076.0',
        'binary_sha256':sha,'worker_sha256':sha,'reading_order':'pdfium_stream_unreviewed',
        'paragraphs':'line_hypotheses_split_at_2048','normalization':'none','text_positions':'unicode_scalar',
        'unicode_mapping':'pdfium_codepoints_and_utf16_surrogate_pairs'}
    result={'citation':citation,'text':'A','parser':parser,'text_status':'mapped','structure_status':'unreviewed',
        'page':{'page_index':0,'width':612.0,'height':792.0,'page_box':[0.0,0.0,612.0,792.0],'rotation':0,'status':'mapped'},
        'characters':[{'index':0,'text_start':0,'text_end':1,'scalar':65,'unicode':65,'generated':False,
            'mapping_error':False,'box':[20.11199951171875,770.0,25.23200035095215,775.7440185546875]}],
        'corpus_id':citation['corpus_id'],'database_id':citation['database_id']}
    operation={'operation_id':uid(),'action':'citations.resolve','request_sha256':sha,
        'result_sha256':sha,'error':None,'state':'completed'}
    shape=schema.method_contract('literature.operations.result')['result']
    assert not check_value({'operation':operation,'result':result},shape)
    for key in ('pdfium','reading_order','paragraphs'):
        bad=copy.deepcopy(result);del bad['parser'][key]
        assert check_value({'operation':operation,'result':bad},shape)
    bad=copy.deepcopy(result);bad['parser']['arbitrary']=True
    assert check_value({'operation':operation,'result':bad},shape)


def test_actual_default_missing_encoder_dependencies_is_unavailable_without_install(tmp_path):
    from suan.literature.encoder_profiles import CORE
    assets=os.environ.get('STK_LITERATURE_E5_ASSETS')
    if not assets:pytest.skip('Requires explicitly provisioned pinned assets for default-runtime refusal')
    def installed(name):
        try:return metadata.version(name)
        except metadata.PackageNotFoundError:return None
    if all(installed(name)==value for name,value in CORE.items()):
        pytest.skip('This default interpreter already satisfies the reviewed encoder dependencies')
    bridge=InProcessBridge(tmp_path/'desktop')
    try:
        params={'operation_id':uid(),'assets':assets}
        operation=bridge.call('literature.encoder.review',params)['operation']
        until=time.monotonic()+75
        while operation['state']=='running' and time.monotonic()<until:
            time.sleep(.02)
            operation=bridge.call('literature.operations.get',{'operation_id':params['operation_id']})['operation']
        assert operation['state']=='uncertain' and operation['error']['code']=='unavailable'
        assert bridge.bridge.literature.encoder_python==sys.executable
        assert bridge.call('literature.encoder.review',params)=={'operation':operation}
        assert not bridge.call('literature.encoder.info')['selection']
    finally:bridge.close()


def test_actual_corpus_uuid_replay_and_passive_reopen_through_bridge(tmp_path, monkeypatch):
    bridge=InProcessBridge(tmp_path/'desktop')
    try:
        operation,result,params=job(bridge,'corpora.create',name='Owned Bridge library')
        assert result['corpus_id']=='local_'+params['operation_id'].replace('-','')
        assert bridge.call('literature.corpora.info',{'corpus_id':result['corpus_id']})['database_id']==result['database_id']
        assert bridge.call('literature.corpora.create',params)=={'operation':operation}
        assert bridge.error('literature.corpora.create',{**params,'name':'Changed'})['code']=='conflict'
    finally:bridge.close()
    from suan.desktop_bridge import literature
    monkeypatch.setattr(literature,'WorkerProcess',lambda *a,**k:pytest.fail('Reopen dispatched old action'))
    bridge=InProcessBridge(tmp_path/'desktop',literature_encoder_python='/tmp/changed-trusted-encoder')
    try:
        assert bridge.call('literature.corpora.create',params)=={'operation':operation}
        assert bridge.call('literature.operations.result',{'operation_id':operation['operation_id'],
            'expected_request_sha256':operation['request_sha256']})=={'operation':operation,'result':result}
        assert bridge.call('literature.versions.list',{'corpus_id':result['corpus_id']})=={'versions':[]}
    finally:bridge.close()


def test_actual_pdf_e5_bridge_chain_and_revocation_fence(tmp_path,pdf_python):
    assets=os.environ.get('STK_LITERATURE_E5_ASSETS');encoder_python=os.environ.get('STK_LITERATURE_E5_PYTHON')
    if not assets or not encoder_python:pytest.skip('Requires explicitly provisioned real pinned E5 assets/interpreter')
    source=tmp_path/'owned.pdf';source.write_bytes(make_pdf([['A solar cell converts sunlight into electrical energy.']]))
    bridge=InProcessBridge(tmp_path/'desktop',literature_parser_python=pdf_python,literature_encoder_python=encoder_python)
    try:
        _,created,_=job(bridge,'corpora.create',name='Owned fixture');scope=created['corpus_id']
        imported,review,_=job(bridge,'import.review',corpus_id=scope,source=str(source),document_id=uid(),title='Owned software fixture',authorization=RIGHTS)
        commit,receipt,_=job(bridge,'import.commit',review_id=imported['operation_id'],review_sha256=checksum(review))
        version=receipt['receipt']['version_id']
        assert bridge.call('literature.versions.list',{'corpus_id':scope})['versions'][0]['version_id']==version
        _,recovered,_=job(bridge,'import.recover',corpus_id=scope,original_operation_id=commit['operation_id'])
        assert recovered['receipt']['import']==receipt['receipt']
        job(bridge,'index.start',corpus_id=scope,version_id=version)
        reviewed,description,_=job(bridge,'encoder.review',assets=assets)
        assert description['assets_sha256']==os.environ['STK_LITERATURE_E5_MANIFEST_SHA256']
        job(bridge,'encoder.select',review_id=reviewed['operation_id'],review_sha256=checksum(description),expected_generation=0)
        generation=bridge.call('literature.corpora.info',{'corpus_id':scope})['generation']
        job(bridge,'dense.build',corpus_id=scope,expected_generation=generation,encoder_generation=1)
        searched,found,_=job(bridge,'search',scopes=[scope],query='sunlight',encoder_generation=1)
        assert found['retriever']=='local_collection_fts5_e5_rrf' and found['hits']
        cite=found['hits'][0]['citation']
        resolved,text,_=job(bridge,'citations.resolve',scopes=[scope],citation=cite)
        assert text['text']==found['hits'][0]['text']
        rendered,page,_=job(bridge,'pages.render',scopes=[scope],citation=cite,long_edge=256)
        assert page['image']['width']<=256 and page['highlights']
        job(bridge,'versions.revoke',corpus_id=scope,version_id=version)
        for operation in (searched,resolved,rendered):
            assert bridge.call('literature.operations.get',{'operation_id':operation['operation_id']})['operation']==operation
            assert bridge.error('literature.operations.result',{'operation_id':operation['operation_id'],
                'expected_request_sha256':operation['request_sha256']})['code']=='invalid_params'
    finally:bridge.close()
    assert not bridge.bridge.literature._running and not bridge.bridge.literature._children
