"""Single-attempt local analyses use frozen copies and independently verified archives."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from uuid import uuid4

import pytest

from suan.desktop_bridge import analysis_runs as module
from suan.desktop_bridge.analysis_runs import AnalysisRunExecutor, _Lease
from suan.desktop_bridge.graph_worker import GraphWorker
from suan.desktop_bridge.protocol import BridgeError
from suan.graph.schema import graph_hash
from suan.project import ProjectError, ProjectStore


def prepared(tmp_path, *, document=None, content=b'frozen input', filename='nested/input.txt'):
    store = ProjectStore.create(tmp_path / 'project', 'Analysis runs')
    source = store.directory / 'input.txt'; source.write_bytes(content)
    record_id = store.files.index([str(source)], expected_revision=0)['record_ids'][0]
    snapshot = store.snapshots.capture([record_id], expected_revision=1)['snapshot']
    document = document or {'format': 'stk.analysis-document/1', 'graph': {'schema':'stk.graph/1',
        'nodes':[{'id':'n','type':'fixture.test.value@1'}], 'outputs':{'value':'n.value'}},
        'parameters':{}, 'outputs':['value']}
    analysis_id = str(uuid4())
    store.analyses.create('Saved', document, analysis_id=analysis_id, expected_revision=2)
    run = store.analysis_runs.prepare(analysis_id, snapshot['id'], {'data':{filename:record_id}},
                                     run_id=str(uuid4()), expected_revision=3)
    return store, run, source


def another(store, run):
    selection = {binding:{path:item['record_id'] for path,item in files.items()} for binding,files in run['bindings'].items()}
    return store.analysis_runs.prepare(run['analysis_id'], run['snapshot_id'], selection,
        run_id=str(uuid4()), expected_revision=store.info()['revision'])


def value_result(graph, **extra):
    digest = graph_hash(graph)
    return {'schema':'stk.graph-result/1','graph_hash':digest,'graph_sha256':digest[7:],
            'outputs':{'value':{'type':'value','value':42}}, 'parameters':{}, **extra}


class Worker:
    def __init__(self, callback=None):
        self.calls=[]; self.callback=callback
    def evaluate(self, identity, work, cancel, events):
        self.calls.append((identity,deepcopy(work)))
        if self.callback: return self.callback(work,cancel)
        return value_result(work['request']['graph'])


def settled(executor,store,run, timeout=5):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        record=store.analysis_runs.get(run['id'])
        with executor._lock: active=executor._key(store,run['id']) in executor._jobs
        if not active: return record
        time.sleep(.01)
    pytest.fail('analysis did not settle')


def test_frozen_copies_no_hardlinks_and_exact_configuration_survive_original_edits(tmp_path):
    store,run,source=prepared(tmp_path)
    before,history=store.snapshot(),store.history()
    original=Path(store.snapshots.resolve(run['snapshot_id'], next(iter(run['bindings']['data'].values()))['record_id'])['path'])
    source.write_bytes(b'changed original')
    stages=[]
    def evaluate(work,cancel):
        stage=Path(work['local_bindings']['data']);stages.append(stage)
        copied=stage/'nested/input.txt'
        assert copied.read_bytes()==b'frozen input'
        assert not os.path.samefile(copied,original)
        copied.write_bytes(b'worker changed its private copy')
        assert original.read_bytes()==b'frozen input'
        assert work['request']=={'graph':run['document']['graph'],'parameters':{},'outputs':['value'],
                                 'profile':'desktop','budget':run['budget']}
        return value_result(work['request']['graph'])
    worker=Worker(evaluate); executor=AnalysisRunExecutor(worker,tmp_path/'cache')
    assert executor.start(store,run['id'])['status']=='running'
    final=settled(executor,store,run)
    assert final['status']=='succeeded' and final['result']['has_payload'] is False
    assert not stages[0].exists() and len(worker.calls)==1
    assert executor.start(store,run['id'])==final
    output=executor.result(store,run['id'])
    assert output['result']['outputs']['value']['value']==42
    assert Path(output['blob_dir']).is_dir()
    assert store.snapshot()==before and store.history()==history
    assert ProjectStore(store.directory).analysis_runs.get(run['id'])==final


def test_duplicate_starts_and_cross_executor_recovery_cannot_replay_active_run(tmp_path):
    store,run,_=prepared(tmp_path); entered=threading.Event(); release=threading.Event()
    def evaluate(work,cancel):
        entered.set(); assert release.wait(5); return value_result(work['request']['graph'])
    worker=Worker(evaluate); executor=AnalysisRunExecutor(worker,tmp_path/'cache')
    other=AnalysisRunExecutor(Worker(),tmp_path/'other')
    try:
        with ThreadPoolExecutor(2) as pool:
            records=list(pool.map(lambda _:executor.start(store,run['id']),range(2)))
        assert entered.wait(2) and all(r['status']=='running' for r in records)
        assert other.start(store,run['id'])['status']=='running'
        with pytest.raises(BridgeError) as exc: other.recover(store,run['id'])
        assert exc.value.code=='busy' and len(worker.calls)==1 and not other.worker.calls
    finally: release.set()
    assert settled(executor,store,run)['status']=='succeeded'


def test_abandoned_claim_recovers_unknown_without_adopting_or_replaying(tmp_path):
    store,run,_=prepared(tmp_path);worker=Worker();executor=AnalysisRunExecutor(worker,tmp_path/'cache')
    store.analysis_runs._claim(run['id'],executor_id=str(uuid4()))
    archive=store.directory/'.stk/analysis-runs'/run['id']/'result';archive.mkdir(parents=True)
    (archive/'untrusted.txt').write_text('remnant')
    result=executor.recover(store,run['id'])
    assert result['status']=='unknown' and result['result'] is None
    assert executor.start(store,run['id'])==result and not worker.calls
    with pytest.raises(BridgeError) as exc:executor.result(store,run['id'])
    assert exc.value.code=='conflict' and (archive/'untrusted.txt').read_text()=='remnant'


@pytest.mark.parametrize('damage',['missing','bytes','symlink'])
def test_bad_frozen_input_never_dispatches_or_falls_back_to_original(tmp_path,damage):
    store,run,source=prepared(tmp_path)
    item=next(iter(run['bindings']['data'].values()));obj=store.snapshots._object(item['sha256'])
    if damage=='missing':obj.unlink()
    elif damage=='bytes':obj.write_bytes(b'corrupt bytes')
    else:
        if os.name=='nt':pytest.skip('Windows symbolic links require privileges')
        obj.unlink();obj.symlink_to(source)
    worker=Worker();executor=AnalysisRunExecutor(worker,tmp_path/'cache')
    executor.start(store,run['id']); final=settled(executor,store,run)
    assert final['status']=='failed' and final['result'] is None and not worker.calls


def test_partial_outputs_are_failed_but_verified_result_remains_readable(tmp_path):
    store,run,_=prepared(tmp_path)
    worker=Worker(lambda work,cancel:value_result(work['request']['graph'],errors=[{'code':'node_error','message':'one output failed'}]))
    executor=AnalysisRunExecutor(worker,tmp_path/'cache');executor.start(store,run['id'])
    final=settled(executor,store,run)
    assert final['status']=='failed' and final['result']['has_errors'] and final['error']['code']=='partial_outputs'
    assert executor.result(store,run['id'])['result']['errors'][0]['code']=='node_error'


@pytest.mark.parametrize('damage',['cache_bytes','missing_blob','wrong_hash','wrong_size','existing_archive'])
def test_cache_corruption_and_inconsistent_results_do_not_publish_success(tmp_path,damage):
    store,run,_=prepared(tmp_path);cache=tmp_path/'cache';body=b'archive bytes';digest=hashlib.sha256(body).hexdigest()
    target=cache/digest[:2]/digest;target.parent.mkdir(parents=True);target.write_bytes(body)
    result=value_result(run['document']['graph'],outputs={'value':{'type':'file','name':'data.bin','media_type':'application/octet-stream','blob':digest,'size':len(body)}})
    if damage=='cache_bytes':target.write_bytes(b'wrong bytes!!')
    elif damage=='missing_blob':target.unlink()
    elif damage=='wrong_hash':result['graph_hash']='sha256:'+'a'*64
    elif damage=='wrong_size':result['outputs']['value']['size']+=1
    else:(store.directory/'.stk/analysis-runs'/run['id']/'result').mkdir(parents=True)
    executor=AnalysisRunExecutor(Worker(lambda work,cancel:result),cache);executor.start(store,run['id'])
    final=settled(executor,store,run)
    assert final['status']=='failed' and final['result'] is None


def test_archive_is_independent_of_cache_and_each_read_verifies_every_blob(tmp_path):
    store,run,_=prepared(tmp_path);cache=tmp_path/'cache';body=b'archive bytes';digest=hashlib.sha256(body).hexdigest()
    target=cache/digest[:2]/digest;target.parent.mkdir(parents=True);target.write_bytes(body)
    result=value_result(run['document']['graph'],outputs={'value':{'type':'file','name':'data.bin','media_type':'application/octet-stream','blob':digest,'size':len(body)}})
    executor=AnalysisRunExecutor(Worker(lambda work,cancel:result),cache);executor.start(store,run['id'])
    assert settled(executor,store,run)['status']=='succeeded'
    output=executor.result(store,run['id']);archived=Path(output['blob_dir'])/digest[:2]/digest
    assert archived.read_bytes()==body and not os.path.samefile(target,archived)
    target.write_bytes(b'cache now bad')
    assert executor.result(store,run['id'])['result']==result
    archived.write_bytes(b'archive bad!!')
    with pytest.raises(ProjectError):executor.result(store,run['id'])


def test_cancel_before_start_and_owned_project_close_have_no_replay(tmp_path):
    store,run,_=prepared(tmp_path);worker=Worker();executor=AnalysisRunExecutor(worker,tmp_path/'cache')
    assert executor.cancel(store,run['id'])['status']=='cancelled'
    assert executor.start(store,run['id'])['status']=='cancelled' and not worker.calls
    second=another(store,run);entered=threading.Event()
    def wait(work,cancel):
        entered.set();assert cancel.wait(3);raise BridgeError('cancelled','stopped')
    worker.callback=wait;executor.start(store,second['id']);assert entered.wait(2)
    executor.close_project(store)
    assert settled(executor,store,second)['status']=='cancelled'


def test_capacity_is_rejected_before_claim_and_shutdown_is_immediate(tmp_path,monkeypatch):
    monkeypatch.setattr(module,'MAX_ACTIVE_RUNS',1)
    store,run,_=prepared(tmp_path);other=another(store,run);entered=threading.Event()
    def wait(work,cancel):entered.set();assert cancel.wait(3);raise BridgeError('cancelled','stopped')
    executor=AnalysisRunExecutor(Worker(wait),tmp_path/'cache');executor.start(store,run['id']);assert entered.wait(2)
    with pytest.raises(BridgeError) as exc:executor.start(store,other['id'])
    assert exc.value.code=='busy' and store.analysis_runs.get(other['id'])['status']=='prepared'
    started=time.monotonic();executor.shutdown();assert time.monotonic()-started<.3
    assert settled(executor,store,run)['status']=='cancelled'
    with pytest.raises(BridgeError) as exc:executor.start(store,other['id'])
    assert exc.value.code=='shutting_down'


def test_cross_process_lease_is_not_just_an_in_memory_guard(tmp_path):
    import subprocess,sys
    store,run,_=prepared(tmp_path);lease=_Lease(store,run['id'])
    script='''
import sys
from suan.project import ProjectStore
from suan.desktop_bridge.analysis_runs import _Lease
from suan.desktop_bridge.protocol import BridgeError
try: lease=_Lease(ProjectStore(sys.argv[1]),sys.argv[2])
except BridgeError as exc:
 assert exc.code=='busy'
else:
 lease.release();raise AssertionError('acquired held OS lease')
'''
    try:subprocess.run([sys.executable,'-c',script,str(store.directory),run['id']],check=True,timeout=15)
    finally:lease.release()


def test_real_local_worker_runs_frozen_graph_with_empty_output_selection(tmp_path):
    graph={'schema':'stk.graph/1','nodes':[{'id':'n','type':'stk.source.file@1','params':{'binding':'data','path':'nested/input.txt'}}],'outputs':{'data':'n.out'}}
    store,run,_=prepared(tmp_path,document={'format':'stk.analysis-document/1','graph':graph,'parameters':{},'outputs':[]})
    worker=GraphWorker(tmp_path/'cache');executor=AnalysisRunExecutor(worker,tmp_path/'cache/blobs')
    try:
        executor.start(store,run['id']);final=settled(executor,store,run,timeout=20)
        assert final['status']=='succeeded',final
        assert executor.result(store,run['id'])['result']['outputs']=={}
    finally:executor.shutdown(wait=True);worker.close()


def test_large_result_over_editable_document_limit_round_trips_with_no_execution(tmp_path):
    store,run,_=prepared(tmp_path);result=value_result(run['document']['graph'])
    result['outputs']['value']['value']='x'*(512*1024)
    worker=Worker(lambda work,cancel:result);executor=AnalysisRunExecutor(worker,tmp_path/'cache')
    executor.start(store,run['id']);assert settled(executor,store,run)['status']=='succeeded'
    assert executor.result(store,run['id'])['result']==result and len(worker.calls)==1


@pytest.mark.parametrize('damage',['extra','missing','parameter_shape','graph_identity','deep','nonfinite'])
def test_unmatched_or_malformed_receipts_cannot_be_published(tmp_path,damage):
    store,run,_=prepared(tmp_path);result=value_result(run['document']['graph'])
    if damage=='extra':result['outputs']['unexpected']={'type':'value','value':1}
    elif damage=='missing':result['outputs']={}
    elif damage=='parameter_shape':result['parameters']={'x':0}
    elif damage=='graph_identity':result['graph_sha256']='0'*64
    elif damage=='nonfinite':result['outputs']['value']['value']=float('nan')
    else:
        value=0
        for _ in range(70):value=[value]
        result['outputs']['value']['value']=value
    executor=AnalysisRunExecutor(Worker(lambda work,cancel:result),tmp_path/'cache')
    executor.start(store,run['id']);assert settled(executor,store,run)['status']=='failed'


def test_cancel_intent_is_durable_before_worker_observes_it(tmp_path):
    store,run,_=prepared(tmp_path);entered=threading.Event();observed=[]
    def wait(work,cancel):
        entered.set();assert cancel.wait(3)
        observed.append(store.analysis_runs.get(run['id']))
        raise BridgeError('cancelled','stopped')
    executor=AnalysisRunExecutor(Worker(wait),tmp_path/'cache');executor.start(store,run['id']);assert entered.wait(2)
    executor.cancel(store,run['id']);final=settled(executor,store,run)
    assert final['status']=='cancelled' and final['cancel_requested_at']
    assert observed[0]['status']=='cancel_requested' and observed[0]['cancel_requested_at']


def test_shutdown_during_claim_does_not_dispatch_and_does_not_wait_for_claim(tmp_path,monkeypatch):
    from suan.project.analysis_runs import AnalysisRuns
    store,run,_=prepared(tmp_path);entered=threading.Event();release=threading.Event()
    original=AnalysisRuns._claim
    def held(self,*args,**kwargs):
        result=original(self,*args,**kwargs);entered.set();assert release.wait(3);return result
    monkeypatch.setattr(AnalysisRuns,'_claim',held)
    executor=AnalysisRunExecutor(Worker(),tmp_path/'cache')
    with ThreadPoolExecutor(1) as pool:
        future=pool.submit(executor.start,store,run['id']);assert entered.wait(2)
        start=time.monotonic();executor.shutdown();assert time.monotonic()-start<.3
        release.set();assert future.result(3)['status']=='cancelled'
    assert not executor.worker.calls


def test_close_during_sql_wait_fences_success_after_archive_publication(tmp_path,monkeypatch):
    import sqlite3
    store,run,_=prepared(tmp_path);executor=AnalysisRunExecutor(Worker(),tmp_path/'cache')
    reached=threading.Event();proceed=threading.Event();original=executor._archive
    def archive(*args):
        result=original(*args);reached.set();assert proceed.wait(3);return result
    monkeypatch.setattr(executor,'_archive',archive)
    executor.start(store,run['id']);assert reached.wait(2)
    db=sqlite3.connect(store.path,isolation_level=None);db.execute('BEGIN IMMEDIATE')
    try:
        proceed.set();executor.close_project(store)
    finally:db.rollback();db.close()
    final=settled(executor,store,run)
    assert final['status']=='cancelled' and final['result'] is None
    assert (store.directory/'.stk/analysis-runs'/run['id']/'result/graph-result.json').exists()


def test_explicit_wall_budget_cancels_only_this_attempt(tmp_path,monkeypatch):
    monkeypatch.setattr(module,'MAX_SECONDS',.1)
    store,run,_=prepared(tmp_path)
    def wait(work,cancel):assert cancel.wait(2);raise BridgeError('cancelled','stopped')
    executor=AnalysisRunExecutor(Worker(wait),tmp_path/'cache');executor.start(store,run['id'])
    final=settled(executor,store,run)
    assert final['status']=='failed' and final['error']['code']=='time_budget_exceeded'


def test_real_payload_archive_decodes_signed_values_after_worker_cache_is_removed(tmp_path):
    import io,shutil
    np=pytest.importorskip('numpy')
    from suan.graph.catalog import load_preset
    from suan.render.payload import decode
    values=np.arange(24,dtype=np.float64).reshape(2,3,4)-15
    data=io.BytesIO();np.save(data,values)
    document={'format':'stk.analysis-document/1','graph':load_preset('scalar-volume'),
              'parameters':{'path':'field.npy','field':'field','unit':'K'},'outputs':['view']}
    store,run,source=prepared(tmp_path,document=document,content=data.getvalue(),filename='field.npy')
    source.unlink();worker=GraphWorker(tmp_path/'cache');executor=AnalysisRunExecutor(worker,tmp_path/'cache/blobs')
    try:
        executor.start(store,run['id']);final=settled(executor,store,run,timeout=20)
        assert final['status']=='succeeded',final['error']
        assert final['result']['has_payload']
        worker.close();shutil.rmtree(tmp_path/'cache')
        result=executor.result(store,run['id']);manifest=result['result']['outputs']['view']['manifest']
        blobs={b['sha256']:(Path(result['blob_dir'])/b['sha256'][:2]/b['sha256']).read_bytes() for b in manifest['buffers']}
        payload=decode(manifest,blobs);volume=payload.layer('volume')
        np.testing.assert_array_equal(payload.array(volume['data']),values.transpose(2,1,0).astype('float32').ravel())
        assert result['result']['parameters']['unit']['value']=='K'
    finally:executor.shutdown(wait=True);worker.close()


def test_worker_loss_settles_unknown_and_start_cannot_retry(tmp_path):
    store,run,_=prepared(tmp_path)
    def crash(work,cancel):raise BridgeError('unavailable','worker exited')
    worker=Worker(crash);executor=AnalysisRunExecutor(worker,tmp_path/'cache')
    executor.start(store,run['id']);final=settled(executor,store,run)
    assert final['status']=='unknown' and executor.start(store,run['id'])==final
    assert executor.recover(store,run['id'])==final and len(worker.calls)==1


from test_desktop_graph_worker import worker_command  # noqa: E402,F401


def test_queued_attempt_watchdog_does_not_kill_an_unrelated_active_graph(tmp_path,worker_command,monkeypatch):
    monkeypatch.setattr(module,'MAX_SECONDS',1)
    store,run,_=prepared(tmp_path);worker=GraphWorker(tmp_path/'cache',command=worker_command)
    outside_cancel,entered,queued=threading.Event(),threading.Event(),threading.Event()
    evaluate=worker.evaluate
    def tracked(identity,*args):
        if identity.startswith('analysis-'):queued.set()
        return evaluate(identity,*args)
    monkeypatch.setattr(worker,'evaluate',tracked)
    executor=AnalysisRunExecutor(worker,tmp_path/'cache/blobs')
    try:
        with ThreadPoolExecutor(1) as pool:
            active=pool.submit(worker.evaluate,'unrelated',{'request':{'parameters':{'mode':'block'}}},outside_cancel,lambda event:entered.set())
            try:
                assert entered.wait(5);child=worker._child
                executor.start(store,run['id']);assert queued.wait(2)
                final=settled(executor,store,run)
                assert final['status']=='failed' and final['error']['code']=='time_budget_exceeded'
                assert child.process.poll() is None and not active.done() and worker._child is child
            finally:
                outside_cancel.set()
                with pytest.raises(BridgeError) as exc:active.result(5)
                assert exc.value.code=='cancelled'
    finally:executor.shutdown(wait=True);worker.close()


def test_start_reply_cannot_mutate_the_frozen_job(tmp_path,monkeypatch):
    store,run,_=prepared(tmp_path);worker=Worker();executor=AnalysisRunExecutor(worker,tmp_path/'cache')
    entered,release=threading.Event(),threading.Event();original=executor._stage
    def held(job):
        staged=original(job);entered.set();assert release.wait(3);return staged
    monkeypatch.setattr(executor,'_stage',held)
    reply=executor.start(store,run['id']);assert entered.wait(2)
    reply['document']['graph']['nodes'][0]['type']='fixture.wrong.type@1'
    reply['document']['outputs'].clear();reply['bindings'].clear()
    release.set()
    assert settled(executor,store,run)['status']=='succeeded'
    assert worker.calls[0][1]['request']['graph']==run['document']['graph']
    assert worker.calls[0][1]['request']['outputs']==['value']


@pytest.mark.parametrize('limit',['manifest','archive'])
def test_result_byte_caps_reject_before_publication(tmp_path,monkeypatch,limit):
    store,run,_=prepared(tmp_path);result=value_result(run['document']['graph'])
    result['outputs']['value']['value']='x'*5000
    monkeypatch.setattr(module,'MAX_RESULT_BYTES' if limit=='manifest' else 'MAX_BYTES',4096)
    executor=AnalysisRunExecutor(Worker(lambda work,cancel:result),tmp_path/'cache')
    executor.start(store,run['id']);final=settled(executor,store,run)
    assert final['status']=='failed' and final['result'] is None
    assert not (store.directory/'.stk/analysis-runs'/run['id']/'result').exists()


def test_missing_manifest_reports_unavailable_without_reexecuting(tmp_path):
    store,run,_=prepared(tmp_path);worker=Worker();executor=AnalysisRunExecutor(worker,tmp_path/'cache')
    executor.start(store,run['id']);final=settled(executor,store,run)
    path=store.directory/final['result']['directory']/'graph-result.json';path.unlink()
    with pytest.raises(BridgeError) as exc:executor.result(store,run['id'])
    assert exc.value.code=='unavailable' and len(worker.calls)==1 and not path.exists()
