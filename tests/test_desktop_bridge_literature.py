"""Local desktop literature contracts; real parser/E5 cases require provisioned assets."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import queue
import sys
import threading
import time
from uuid import uuid4

import pytest

import suan.desktop_bridge.literature as module
from suan.desktop_bridge.literature import LiteratureService, child_environment, request_sha256
from suan.desktop_bridge.protocol import BridgeError
from suan.literature.pdf import checksum
from suan.literature.store import Library
from test_literature_pdf import make_pdf, unicode_pdf, pdf_python
from test_literature_store import RIGHTS


def job(service,action,**params):
    params={'operation_id':str(uuid4()),**params}
    admission=service.call(action,params)['operation'];end=time.monotonic()+700
    while admission['state']=='running' and time.monotonic()<end:
        time.sleep(.02)
        admission=service.call('operations.get',{'operation_id':params['operation_id']})['operation']
    assert admission['state']=='completed', admission
    result=service.call('operations.result',{'operation_id':params['operation_id'],
        'expected_request_sha256':admission['request_sha256']})['result']
    return admission,result


def corpus(service,name='Owned validation library'):
    return job(service,'corpora.create',name=name)[1]['corpus_id']


def capture(service,tmp_path,scope,*,rotation=0,crop=None,content=None):
    source=tmp_path/(uuid4().hex+'.pdf')
    source.write_bytes(content or make_pdf([['A solar cell converts sunlight into electrical energy.']],rotation=rotation,crop=crop))
    review,description=job(service,'import.review',corpus_id=scope,source=str(source),document_id=str(uuid4()),
                           title='Self-authored software fixture',authorization=RIGHTS)
    committed,result=job(service,'import.commit',review_id=review['operation_id'],review_sha256=checksum(description))
    return source,result['receipt']['version_id'],description


def test_passive_missing_service_has_no_files_dispatch_or_model(tmp_path,monkeypatch):
    monkeypatch.setattr(module,'WorkerProcess',lambda *a,**k:pytest.fail('Passive worker dispatch'))
    state=tmp_path/'absent'
    for _ in range(2):
        service=LiteratureService(state)
        assert service.call('info',{})['corpora']==[]
        assert service.call('encoder.info',{})=={'generation':0,'selection':None}
        assert service.call('operations.list',{})=={'operations':[]}
        assert service.call('operations.get',{'operation_id':str(uuid4())})=={'operation':None}
        service.shutdown()
    assert not state.exists()


@pytest.mark.parametrize('action,params',[
    ('search',{'scopes':[],'query':'owned','encoder_generation':0}),
    ('encoder.review',{'assets':'relative'}),
    ('encoder.review',{'assets':'/tmp/owned','python':'/tmp/untrusted-python'}),
    ('corpora.create',{'name':'\ud800'}),('corpora.create',{'name':'owned','extra':True}),
    ('dense.build',{'corpus_id':'local_'+'a'*32,'expected_generation':True,'encoder_generation':0}),
    ('dense.build',{'corpus_id':'local_'+'a'*32,'expected_generation':0,'encoder_generation':0,'timeout':3601}),
    ('dense.build',{'corpus_id':'local_'+'a'*32,'expected_generation':0,'encoder_generation':0,'timeout':True}),
    ('citations.resolve',{'scopes':['local_'+'a'*32],'citation':{}}),
])
def test_invalid_request_rejected_before_state_or_dispatch(tmp_path,monkeypatch,action,params):
    monkeypatch.setattr(module,'WorkerProcess',lambda *a,**k:pytest.fail('Invalid dispatch'))
    service=LiteratureService(tmp_path/'absent',encoder_python=sys.executable)
    with pytest.raises(BridgeError):service.call(action,{'operation_id':str(uuid4()),**params})
    assert not service.root.exists()


def test_deep_input_is_bounded_before_canonicalization(tmp_path):
    value={}
    for _ in range(20000):value={'nested':value}
    service=LiteratureService(tmp_path/'absent')
    with pytest.raises(BridgeError):service.call('info',value)
    assert not service.root.exists()


def test_parent_environment_allowlist_does_not_read_credential_values(monkeypatch):
    class Environment(dict):
        def items(self):raise AssertionError('Ambient values enumerated')
        def __getitem__(self,key):
            assert key in {'LANG','SYSTEMROOT','WINDIR','TEMP','TMP','LC_ALL','TZ'}
            return super().__getitem__(key)
    monkeypatch.setattr(module.os,'environ',Environment(LANG='C.UTF-8',STK_TOKEN_PLAN_API_KEY='abcdefghijklmnopqrstu',
        HF_TOKEN='abcdefghijklmnopqrstu',STK_TOKEN_PLAN_MODEL='owned',UNRELATED='owned'))
    result=child_environment()
    assert result['STK_TOKEN_PLAN_API_KEY']=='' and result['LANG']=='C.UTF-8'
    assert not {'HF_TOKEN','STK_TOKEN_PLAN_MODEL','UNRELATED'}&result.keys()


@pytest.mark.parametrize('explicit',[False,True])
def test_worker_process_optional_env_preserves_omitted_kwargs(monkeypatch,explicit):
    import suan.desktop_bridge.worker_process as transport
    captured={}
    class Stop(Exception):pass
    def popen(*a,**kwargs):captured.update(kwargs);raise Stop
    monkeypatch.setattr(transport.subprocess,'Popen',popen)
    with pytest.raises(Stop):transport.WorkerProcess(['owned'],**({'env':{'STK_TOKEN_PLAN_API_KEY':''}} if explicit else {}))
    assert ('env' in captured)==explicit


def test_unknown_or_missing_state_fails_closed_without_reset(tmp_path):
    service=LiteratureService(tmp_path);service.root.mkdir(mode=0o700)
    foreign=service.root/'unknown';foreign.write_text('owned');foreign.chmod(0o600)
    before=foreign.read_bytes()
    with pytest.raises(BridgeError):service.call('info',{})
    assert foreign.read_bytes()==before and not (service.root/'state.json').exists()


def test_actual_import_review_commit_reopen_original_ids_and_receipts(tmp_path):
    service=LiteratureService(tmp_path);scope=corpus(service)
    source,version,review=capture(service,tmp_path,scope)
    records=service.call('operations.list',{})['operations']
    committed=next(r for r in records if r['action']=='import.commit')
    assert Library(service.root/'corpora'/scope).operation(committed['operation_id'])['state']=='completed'
    assert service.call('versions.list',{'corpus_id':scope})['versions'][0]['version_id']==version
    service.shutdown();before={str(p):p.read_bytes() for p in (tmp_path/'literature').rglob('*.json')}
    reopened=LiteratureService(tmp_path)
    assert reopened.call('info',{})['active_jobs']==0
    assert reopened.call('operations.list',{})['operations']==records
    assert {str(p):p.read_bytes() for p in (tmp_path/'literature').rglob('*.json')}==before
    reopened.shutdown()


def test_passive_corpus_info_is_one_bound_transaction_and_never_dispatches(tmp_path,monkeypatch):
    service=LiteratureService(tmp_path);scope=corpus(service)
    service.shutdown();observer=LiteratureService(tmp_path)
    monkeypatch.setattr(module,'WorkerProcess',lambda *a,**k:pytest.fail('Passive corpus metadata dispatched'))
    monkeypatch.setattr(Library,'_verify_object',lambda *a,**k:pytest.fail('Metadata hashed a PDF'))
    before={str(p):p.read_bytes() for p in observer.root.rglob('*') if p.is_file()}
    with monkeypatch.context() as bounded:
        bounded.setattr(Library,'info',lambda *a,**k:pytest.fail('Metadata opened a second Library transaction'))
        actual=observer.call('corpora.info',{'corpus_id':scope})
    assert actual=={'corpus_id':scope,'database_id':observer._state()['corpora'][scope]['database_id'],'generation':0,
        'dense_generation':None,'dense_source_generation':None,'dense_encoder_fingerprint':None}
    assert {str(p):p.read_bytes() for p in observer.root.rglob('*') if p.is_file()}==before
    with pytest.raises(BridgeError):observer.call('corpora.info',{'corpus_id':scope,'operation_id':str(uuid4())})
    # A real new database at the same managed path must not be adopted.
    replacement=Library(tmp_path/'replacement')
    with replacement._db(write=True):pass
    target=Library(observer.root/'corpora'/scope).path;saved=target.read_bytes()
    target.write_bytes(replacement.path.read_bytes())
    with pytest.raises(BridgeError):observer.call('corpora.info',{'corpus_id':scope})
    target.write_bytes(saved);observer.shutdown()


def test_review_source_changes_fail_without_recopy_or_replay(tmp_path):
    service=LiteratureService(tmp_path);scope=corpus(service)
    source=tmp_path/'owned.pdf';source.write_bytes(make_pdf([['Original owned bytes']]))
    reviewed,description=job(service,'import.review',corpus_id=scope,source=str(source),document_id=str(uuid4()),title='Owned',authorization=RIGHTS)
    source.write_bytes(make_pdf([['Changed owned bytes']]))
    params={'operation_id':str(uuid4()),'review_id':reviewed['operation_id'],'review_sha256':checksum(description)}
    ticket=service.call('import.commit',params)['operation']
    until=time.monotonic()+10
    while ticket['state']=='running' and time.monotonic()<until:
        time.sleep(.02);ticket=service.call('operations.get',{'operation_id':params['operation_id']})['operation']
    assert ticket['state']=='uncertain'
    assert service.call('import.commit',params)['operation']==ticket
    assert service.call('versions.list',{'corpus_id':scope})=={'versions':[]}
    service.shutdown()


def test_bounded_admission_shutdown_and_passive_uncertain_reopen(tmp_path,monkeypatch):
    started=[]
    class Worker:
        def __init__(self,*a,**k):self.incoming=queue.Queue();self.outgoing=queue.Queue();self.stopped=False;started.append(self)
        def stop(self):self.stopped=True;self.incoming.put(None)
    monkeypatch.setattr(module,'WorkerProcess',Worker)
    service=LiteratureService(tmp_path)
    tickets=[service.call('corpora.create',{'operation_id':str(uuid4()),'name':'Owned'})['operation'] for _ in range(2)]
    with pytest.raises(BridgeError) as caught:service.call('corpora.create',{'operation_id':str(uuid4()),'name':'Third'})
    assert caught.value.code=='busy'
    until=time.monotonic()+3
    while len(started)<2 and time.monotonic()<until:time.sleep(.01)
    service.shutdown();assert len(started)==2 and all(w.stopped for w in started)
    reopened=LiteratureService(tmp_path)
    assert all(reopened.call('operations.get',{'operation_id':t['operation_id']})['operation']['state']=='uncertain' for t in tickets)
    assert len(started)==2;reopened.shutdown()


def test_original_encoder_review_replay_survives_trusted_interpreter_change(tmp_path,monkeypatch):
    class Worker:
        def __init__(self,*a,**k):self.incoming=queue.Queue();self.outgoing=queue.Queue()
        def stop(self):self.incoming.put(None)
    monkeypatch.setattr(module,'WorkerProcess',Worker)
    params={'operation_id':str(uuid4()),'assets':str(tmp_path/'owned-assets'),'python':sys.executable}
    service=LiteratureService(tmp_path,encoder_python=sys.executable)
    service.call('encoder.review',params)
    service.shutdown()
    observer=LiteratureService(tmp_path,encoder_python=str(tmp_path/'other-trusted-python'))
    monkeypatch.setattr(module,'WorkerProcess',lambda *a,**k:pytest.fail('Historical admission redispatched'))
    original=observer.call('operations.get',{'operation_id':params['operation_id']})['operation']
    assert original['state']=='uncertain'
    assert observer.call('encoder.review',params)=={'operation':original}
    with pytest.raises(BridgeError) as caught:
        observer.call('encoder.review',{**params,'python':observer.encoder_python})
    assert caught.value.code=='conflict'
    with pytest.raises(BridgeError) as caught:
        observer.call('encoder.review',{**params,'operation_id':str(uuid4())})
    assert caught.value.code=='invalid_params'
    assert observer.call('operations.list',{})['operations']==[original]
    observer.shutdown()


def test_submit_enqueue_then_raise_never_dispatches(tmp_path,monkeypatch):
    pending=[]
    class Pool:
        def __init__(self,**kwargs):pass
        def submit(self,fn,*args):pending.append((fn,args));raise RuntimeError('Owned rejection')
        def shutdown(self,**kwargs):pass
    monkeypatch.setattr(module,'ThreadPoolExecutor',Pool)
    monkeypatch.setattr(module,'WorkerProcess',lambda *a,**k:pytest.fail('Rejected admission executed'))
    service=LiteratureService(tmp_path)
    ticket=service.call('corpora.create',{'operation_id':str(uuid4()),'name':'Owned'})['operation']
    assert ticket['state']=='uncertain'
    fn,args=pending.pop();fn(*args)
    assert not (service.root/'corpora').exists();service.shutdown()


def test_managed_corpus_limit_and_closed_persisted_journal(tmp_path):
    service=LiteratureService(tmp_path)
    for n in range(8):corpus(service,'Owned '+str(n))
    assert len(service.call('corpora.list',{})['corpora'])==8
    with pytest.raises(BridgeError):service.call('corpora.create',{'operation_id':str(uuid4()),'name':'Ninth'})
    record=service.call('operations.list',{})['operations'][0]
    path=service._record_path(record['operation_id']);body=module._read(path,module.MAX_METADATA)
    body['frozen']['unrecognized']='owned';module._write(path,body,module.MAX_METADATA)
    with pytest.raises(BridgeError):service.call('operations.get',{'operation_id':record['operation_id']})
    service.shutdown()


def test_disk_budget_rejects_before_operation_or_dispatch(tmp_path,monkeypatch):
    service=LiteratureService(tmp_path);corpus(service)
    before=set((service.root/'operations').iterdir())
    monkeypatch.setattr(module,'MAX_SERVICE_BYTES',1)
    with pytest.raises(BridgeError) as caught:service.call('corpora.create',{'operation_id':str(uuid4()),'name':'Owned'})
    assert caught.value.code=='busy' and set((service.root/'operations').iterdir())==before
    service.shutdown()


def test_unknown_worker_result_cannot_publish_catalog(tmp_path,monkeypatch):
    class Worker:
        def __init__(self,*a,**k):self.incoming=queue.Queue();self.outgoing=self
        def put(self,line):
            payload=json.loads(line)
            self.incoming.put({'id':payload['id'],'result':{'database_id':str(uuid4()),'corpus_id':payload['frozen']['new_corpus'],'unknown':'owned'}})
        def stop(self):pass
    monkeypatch.setattr(module,'WorkerProcess',Worker)
    service=LiteratureService(tmp_path)
    ticket=service.call('corpora.create',{'operation_id':str(uuid4()),'name':'Owned'})['operation']
    end=time.monotonic()+3
    while ticket['state']=='running' and time.monotonic()<end:
        time.sleep(.01);ticket=service.call('operations.get',{'operation_id':ticket['operation_id']})['operation']
    assert ticket['state']=='uncertain' and service.call('corpora.list',{})['corpora']==[]
    service.shutdown()


@pytest.fixture(scope='module')
def local_e5():
    assets=os.environ.get('STK_LITERATURE_E5_ASSETS');python=os.environ.get('STK_LITERATURE_E5_PYTHON')
    if not assets or not python:pytest.skip('Requires explicitly provisioned real pinned local E5 assets and interpreter')
    return assets,python


def test_actual_local_e5_search_render_current_authorization_and_original_db(tmp_path,pdf_python,local_e5,monkeypatch):
    assets,python=local_e5
    service=LiteratureService(tmp_path,parser_python=pdf_python,encoder_python=python)
    reviewed,description=job(service,'encoder.review',assets=assets,python=python)
    assert description['python']==python
    _,selection=job(service,'encoder.select',review_id=reviewed['operation_id'],review_sha256=checksum(description),expected_generation=0)
    # Historical metadata has no current-dispatch authority. Changing trusted
    # interpreter/profile configuration must not erase prior admission evidence.
    import suan.literature.encoder_profiles as profile
    with monkeypatch.context() as changed:
        changed.setattr(profile,'E5_RECIPE',{**profile.E5_RECIPE,'revision':'historical-profile-change'})
        changed.setattr(profile,'CORE',{**profile.CORE,'torch':'historical-runtime-change'})
        observer=LiteratureService(tmp_path,encoder_python=sys.executable)
        assert observer.call('operations.get',{'operation_id':reviewed['operation_id']})['operation']==reviewed
        assert observer.call('operations.result',{'operation_id':reviewed['operation_id'],'expected_request_sha256':reviewed['request_sha256']})['result']==description
        assert observer.call('operations.list',{})['operations']
        observer.shutdown()
    scope=corpus(service);source,version,_=capture(service,tmp_path,scope,rotation=90,crop=[10,10,600,790])
    index_ticket,index_result=job(service,'index.start',corpus_id=scope,version_id=version)
    bad=copy.deepcopy(index_result);bad['receipt']['generation']=float(bad['receipt']['generation'])
    with pytest.raises(BridgeError):service._check_result(service._record(index_ticket['operation_id']),bad)
    generation=Library(service.root/'corpora'/scope).info()['generation']
    job(service,'dense.build',corpus_id=scope,expected_generation=generation,encoder_generation=selection['encoder_generation'])
    current=service.call('corpora.info',{'corpus_id':scope})
    assert current['generation']==current['dense_source_generation']==generation
    assert current['dense_encoder_fingerprint']==description['fingerprint']
    with monkeypatch.context() as bounded:
        bounded.setattr(module,'MAX_DENSE_MANIFEST',128)
        decode=module._decode
        def no_manifest_decode(value):
            if type(value) is str:pytest.fail('Oversize manifest reached Python JSON decoder')
            return decode(value)
        bounded.setattr(module,'_decode',no_manifest_decode)
        with pytest.raises(BridgeError):service.call('corpora.info',{'corpus_id':scope})
    other=corpus(service,'Other selected owned library');_,other_version,_=capture(service,tmp_path,other)
    job(service,'index.start',corpus_id=other,version_id=other_version)
    job(service,'dense.build',corpus_id=other,expected_generation=Library(service.root/'corpora'/other).info()['generation'],encoder_generation=1)
    ticket,found=job(service,'search',scopes=[scope,other],query='sunlight',encoder_generation=1,limit=20)
    assert {h['corpus_id'] for h in found['hits']}=={scope,other}
    record=service._record(ticket['operation_id'])
    corrupted=[]
    bad=copy.deepcopy(found);state=next(s for s in found['scopes'] if s['corpus_id']!=bad['hits'][0]['corpus_id'])
    bad['hits'][0].update(state);corrupted.append(bad)  # Both scopes are authorized; relabeling is still invalid.
    bad=copy.deepcopy(found);bad['hits'][0]['citation']=copy.deepcopy(bad['hits'][1]['citation']);corrupted.append(bad)
    bad=copy.deepcopy(found);bad['hits'][0]['dense_window']=copy.deepcopy(bad['hits'][1]['dense_window']);corrupted.append(bad)
    bad=copy.deepcopy(found);bad['hits'][0]['score']+=.001;corrupted.append(bad)
    bad=copy.deepcopy(found);bad['hits'][0]['dense_window']=None;corrupted.append(bad)
    bad=copy.deepcopy(found);bad['hits']=list(reversed(bad['hits']));corrupted.append(bad)
    bad=copy.deepcopy(found);bad['hits'].append(copy.deepcopy(bad['hits'][0]));corrupted.append(bad)
    bad=copy.deepcopy(found);bad['scopes'][0]['corpus_generation']=float(bad['scopes'][0]['corpus_generation']);corrupted.append(bad)
    for bad in corrupted:
        with pytest.raises(BridgeError):service._check_result(record,bad)
    citation=next(h['citation'] for h in found['hits'] if h['corpus_id']==scope)
    _,resolved=job(service,'citations.resolve',scopes=[scope],citation=citation)
    page_ticket,page=job(service,'pages.render',scopes=[scope],citation=citation,long_edge=512)
    assert page['page']['rotation']==90 and page['highlights']
    from suan.render.png import decode_png
    pixels=decode_png(base64.b64decode(page['image']['data_base64']))
    height,width=pixels.shape[:2]
    assert (width,height)==(page['image']['width'],page['image']['height'])
    assert width>height and max(width,height)<=512
    assert (pixels[:,:,:3]<200).any()
    assert all(-1<=p[0]<=width+1 and -1<=p[1]<=height+1 for h in page['highlights'] for p in h['quad'])
    # Passive result reads must never rerun any worker/model/render action.
    monkeypatch.setattr(module,'WorkerProcess',lambda *a,**k:pytest.fail('Result redispatched'))
    assert service.call('operations.result',{'operation_id':ticket['operation_id'],'expected_request_sha256':ticket['request_sha256']})['result']==found
    # Current catalog remapping must not silently change the original DB bind.
    state=service._state();old=copy.deepcopy(state)
    replacement=Library(tmp_path/'replacement')
    with replacement._db(write=True):pass
    target=Library(service.root/'corpora'/scope).path;saved=target.read_bytes()
    target.write_bytes(replacement.path.read_bytes())
    state['corpora'][scope]['database_id']=replacement.info()['database_id'];service._save_state(state)
    with pytest.raises(BridgeError):service.call('operations.result',{'operation_id':ticket['operation_id'],'expected_request_sha256':ticket['request_sha256']})
    target.write_bytes(saved);service._save_state(old)
    check_page=service._check_page
    def revoke_during_delivery(*args):
        check_page(*args)
        Library(service.root/'corpora'/scope).revoke(str(uuid4()),version)
    monkeypatch.setattr(service,'_check_page',revoke_during_delivery)
    with pytest.raises(BridgeError):service.call('operations.result',{'operation_id':page_ticket['operation_id'],'expected_request_sha256':page_ticket['request_sha256']})
    job(service,'versions.revoke',corpus_id=scope,version_id=version)
    stale=service.call('corpora.info',{'corpus_id':scope})
    assert stale['generation']>stale['dense_source_generation'] and stale['dense_generation']==current['dense_generation']
    for saved in (ticket,page_ticket):
        with pytest.raises(BridgeError):service.call('operations.result',{'operation_id':saved['operation_id'],'expected_request_sha256':saved['request_sha256']})
    assert service.call('operations.get',{'operation_id':ticket['operation_id']})['operation']['state']=='completed'
    # Metadata reads fail damaged retained manifests without repairing/rebuilding.
    library=Library(service.root/'corpora'/scope)
    with library._db(write=True) as db:
        db.execute("UPDATE dense_generations SET manifest='{}' WHERE id=?",(current['dense_generation'],))
    with pytest.raises(BridgeError):service.call('corpora.info',{'corpus_id':scope})
    service.shutdown()


def test_actual_known_qwen_profile_metadata_build_search_with_explicit_timeout(tmp_path,pdf_python):
    assets=os.environ.get('STK_LITERATURE_QWEN_ASSETS');python=os.environ.get('STK_LITERATURE_E5_PYTHON')
    if not assets or not python:pytest.skip('Requires explicit pinned Qwen assets and shared provisioned encoder interpreter')
    from suan.literature.encoder_profiles import profile_for_recipe, worker_identity_sha256
    service=LiteratureService(tmp_path,parser_python=pdf_python,encoder_python=python)
    reviewed,description=job(service,'encoder.review',assets=assets)
    assert profile_for_recipe(description['identity']['recipe'])['id']=='qwen3-0.6b-cpu-f32'
    assert description['identity']['runtime']['worker_sha256']==worker_identity_sha256()
    assert description['identity']['recipe']['dimensions']==1024
    job(service,'encoder.select',review_id=reviewed['operation_id'],review_sha256=checksum(description),expected_generation=0)
    scope=corpus(service);_,version,_=capture(service,tmp_path,scope)
    job(service,'index.start',corpus_id=scope,version_id=version)
    generation=service.call('corpora.info',{'corpus_id':scope})['generation']
    ticket,built=job(service,'dense.build',corpus_id=scope,expected_generation=generation,encoder_generation=1,timeout=3600)
    assert service._record(ticket['operation_id'])['request']['timeout']==3600
    assert built['receipt']['encoder_fingerprint']==description['fingerprint']
    _,found=job(service,'search',scopes=[scope],query='sunlight',encoder_generation=1,limit=20)
    assert found['retriever']=='local_collection_fts5_qwen3_rrf' and found['hits']
    service.shutdown()
