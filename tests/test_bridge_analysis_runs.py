"""Registered bridge requests keep local analysis execution explicit and project-scoped."""
from pathlib import Path
import threading
import time
from uuid import uuid4

import pytest

from suan.desktop_bridge.protocol import BridgeError
from suan.project import ProjectStore
from test_analysis_run_executor import prepared, settled, Worker, value_result, another
from test_desktop_bridge import bridge_env, inproc  # noqa: F401


def opened(h,tmp_path):
    store,run,source=prepared(tmp_path)
    info=h.call('project.open',{'directory':str(store.directory)})['project']
    return store,run,source,info['handle']


def test_registered_methods_reads_and_explicit_start_preserve_edit_history(inproc,tmp_path):
    h=inproc();store,run,source,handle=opened(h,tmp_path)
    worker=Worker();h.bridge.analysis_executor.worker=worker
    before,history=store.snapshot(),store.history()
    methods={'project.analysis_runs.'+name for name in ('prepare','get','list','start','cancel','recover','result')}
    assert methods <= set(h.call('hello',{'protocol':1})['methods'])
    assert methods <= set(h.call('script.catalog')['operations'])
    params={'handle':handle,'run_id':run['id']}
    assert h.call('project.analysis_runs.get',params)['run']==run
    listed=h.call('project.analysis_runs.list',{'handle':handle})
    assert listed['runs'][0]['id']==run['id'] and 'document' not in listed['runs'][0]
    assert h.call('project.analysis_runs.recover',params)['run']==run and not worker.calls
    assert h.error('project.analysis_runs.result',params)['code']=='conflict'
    assert h.call('project.analysis_runs.start',params)['run']['status']=='running'
    final=settled(h.bridge.analysis_executor,store,run)
    assert h.call('project.analysis_runs.result',params)['result']['outputs']['value']['value']==42
    assert h.call('project.analysis_runs.start',params)['run']==final and len(worker.calls)==1
    assert store.snapshot()==before and store.history()==history and h.events_of('project.changed')==[]
    assert not h.violations


def test_prepare_retries_use_the_original_frozen_identity_and_never_start(inproc,tmp_path):
    h=inproc();store,run,source,handle=opened(h,tmp_path);worker=Worker();h.bridge.analysis_executor.worker=worker
    params={'handle':handle,'analysis_id':run['analysis_id'],'snapshot_id':run['snapshot_id'],
            'bindings':{'data':{path:item['record_id'] for path,item in run['bindings']['data'].items()}},
            'run_id':str(uuid4()),'expected_revision':3}
    saved=h.call('project.analysis_runs.prepare',params)['run']
    store.analyses.update(run['analysis_id'],'Changed',run['document'],expected_revision=3)
    assert h.call('project.analysis_runs.prepare',params)['run']==saved
    assert h.error('project.analysis_runs.prepare',{**params,'expected_revision':4})['code']=='conflict'
    assert not worker.calls and not h.violations


def test_running_worker_does_not_hold_global_session_lock_and_close_stops_only_its_project(inproc,tmp_path):
    h=inproc();store,run,source,handle=opened(h,tmp_path);entered=threading.Event()
    def wait(work,cancel):entered.set();assert cancel.wait(4);raise BridgeError('cancelled','stopped')
    worker=Worker(wait);h.bridge.analysis_executor.worker=worker
    h.call('project.analysis_runs.start',{'handle':handle,'run_id':run['id']});assert entered.wait(2)
    other=h.call('project.create',{'directory':str(tmp_path/'other'),'name':'Other'},timeout=2)['project']
    assert h.call('project.snapshot',{'handle':other['handle']},timeout=2)['snapshot']['project']['revision']==0
    assert h.call('project.close',{'handle':handle},timeout=2)['closed']
    assert settled(h.bridge.analysis_executor,store,run)['status']=='cancelled'
    assert h.error('project.analysis_runs.get',{'handle':handle,'run_id':run['id']})['code']=='not_found'
    reopened=h.call('project.open',{'directory':str(store.directory)})['project']['handle']
    assert reopened != handle
    assert h.call('project.analysis_runs.start',{'handle':reopened,'run_id':run['id']})['run']['status']=='cancelled'
    assert len(worker.calls)==1 and not h.violations


def test_archive_verification_does_not_hold_global_session_lock(inproc,tmp_path,monkeypatch):
    from suan.desktop_bridge import analysis_runs as module
    h=inproc();store,run,source,handle=opened(h,tmp_path);h.bridge.analysis_executor.worker=Worker()
    h.call('project.analysis_runs.start',{'handle':handle,'run_id':run['id']});settled(h.bridge.analysis_executor,store,run)
    entered,release=threading.Event(),threading.Event();original=module._copy_verified
    def held(source,target,*args,**kwargs):
        if target is None and source.name=='graph-result.json':entered.set();assert release.wait(4)
        return original(source,target,*args,**kwargs)
    monkeypatch.setattr(module,'_copy_verified',held)
    request=h.request('project.analysis_runs.result',{'handle':handle,'run_id':run['id']});assert entered.wait(2)
    try:assert h.call('project.close',{'handle':handle},timeout=1)['closed']
    finally:release.set()
    assert h.response(request,timeout=3)['result']['run']['id']==run['id']
    assert not h.violations
