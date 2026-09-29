"""Explicit provider execution through the bridge, with controlled non-network adapters."""
import json
from uuid import uuid4

import pytest

from suan.project import ProjectStore
from suan.project.aliyun import ALIYUN_ADAPTER, API_KEY_ENV, MODEL_ENV, BASE_URL
from suan.project.request_executor import ConfirmedCancellation
from suan.scripting import Project
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_project_contexts import model, capture  # noqa: F401
from test_request_executor import ControlledAdapter, eventually, idle
from test_desktop_scripts import scripts, execute  # noqa: F401


def prepare(harness, model):
    store, _ = model
    context = capture(model)
    message = store.discussion.add('Explain saved values', message_id=str(uuid4()), context_id=context['id'])
    info = harness.call('project.open', {'directory': str(store.directory)})['project']
    p = Project(lambda method, params: harness.call(method, params), info['handle'])
    saved = p.requests.create(message['id'], request_id=str(uuid4()),
                             configuration={'adapter': ALIYUN_ADAPTER, 'model': 'fixture-model'})
    return p, saved


def test_missing_credentials_status_and_closed_handles_never_claim(inproc, model, monkeypatch):
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    monkeypatch.setenv(MODEL_ENV, 'fixture-model')
    h = inproc()
    p, saved = prepare(h, model)
    store, _ = model
    before, history = store.snapshot(), store.history()
    assert p.requests.provider() == {'adapter': ALIYUN_ADAPTER, 'base_url': BASE_URL,
        'key_env': API_KEY_ENV, 'model_env': MODEL_ENV, 'configured': False, 'model': 'fixture-model'}
    error = h.error('project.requests.start', {'handle': p.handle, 'request_id': saved['id']})
    assert error['code'] == 'invalid_params'
    assert p.requests.get(saved['id']) == saved
    assert p.requests.recover(saved['id']) == saved
    assert h.call('project.close', {'handle': p.handle})['closed']
    for method, extra in [('provider', {}), ('start', {'request_id': saved['id']}), ('recover', {'request_id': saved['id']})]:
        assert h.error('project.requests.' + method, {'handle': p.handle, **extra})['code'] == 'not_found'
    assert store.snapshot() == before and store.history() == history
    assert h.events_of('project.changed') == [] and not h.violations


def test_provider_status_never_returns_key_or_connects(inproc, model, monkeypatch):
    monkeypatch.setenv(API_KEY_ENV, 'test-local-placeholder-credential')
    monkeypatch.setenv(MODEL_ENV, 'https://invalid.example')
    h = inproc()
    p, _ = prepare(h, model)
    result = p.requests.provider()
    assert result['configured'] and result['model'] == ''
    assert 'test-local-placeholder-credential' not in json.dumps(result)
    assert not h.violations


@pytest.mark.parametrize('cancel', [False, True], ids=['complete-after-close', 'cancel-before-close'])
def test_explicit_start_once_cancel_and_close_pin_original_store(inproc, model, cancel):
    h = inproc()
    p, saved = prepare(h, model)
    adapter = ControlledAdapter(ConfirmedCancellation('redacted') if cancel else 'Only the saved context was used')
    executor = h.bridge.projects._executor
    executor._adapters[ALIYUN_ADAPTER] = adapter
    store, _ = model
    before, history = store.snapshot(), store.history()
    try:
        assert p.requests.start(saved['id'])['status'] == 'running'
        assert adapter.started.wait(5)
        assert p.requests.start(saved['id'])['status'] == 'running'
        assert h.error('project.requests.recover', {'handle': p.handle, 'request_id': saved['id']})['code'] == 'busy'
        if cancel:
            assert p.requests.cancel(saved['id'])['status'] == 'uncertain'
            assert adapter.cancel_event.is_set()
        assert h.call('project.close', {'handle': p.handle})['closed']
        other = h.call('project.create', {'directory': str(store.directory.parent / 'other'), 'name': 'Other'})['project']
    finally:
        adapter.release.set()
    eventually(lambda: idle(executor))
    reopened = ProjectStore(store.directory)
    result = reopened.requests.get(saved['id'])
    assert result['status'] == ('cancelled' if cancel else 'completed')
    assert len(adapter.inputs) == 1
    assert h.call('project.requests.list', {'handle': other['handle']})['requests'] == []
    assert reopened.snapshot() == before and reopened.history() == history
    assert not h.violations


def test_bridge_shutdown_fences_late_completion_and_reopen_does_not_resend(inproc, model):
    h = inproc()
    p, saved = prepare(h, model)
    adapter = ControlledAdapter('Late text must not be saved')
    executor = h.bridge.projects._executor
    executor._adapters[ALIYUN_ADAPTER] = adapter
    p.requests.start(saved['id'])
    assert adapter.started.wait(5)
    h.bridge.shutdown()
    adapter.release.set()
    eventually(lambda: idle(executor))
    store, _ = model
    record = store.requests.get(saved['id'])
    assert record['status'] == 'uncertain' and record['result'] is None
    second = inproc(state='second')
    info = second.call('project.open', {'directory': str(store.directory)})['project']
    params = {'handle': info['handle'], 'request_id': saved['id']}
    assert second.call('project.requests.recover', params)['request'] == record
    assert second.call('project.requests.start', params)['request'] == record
    assert len(store.discussion.list()['messages']) == 1 and not second.violations


def test_real_script_worker_provider_facade_and_local_preflight(scripts, model, monkeypatch):
    # ProcessBridge inherits the configured test environment before this function;
    # it uses an unregistered adapter to guarantee no external request for any host env.
    store, _ = model
    info = scripts.call('project.open', {'directory': str(store.directory)})['project']
    session = scripts.call('script.open')['session']
    result = execute(scripts, session, '''
from uuid import uuid4
from suan.scripting import ScriptError
p = stk.project
provider = p.requests.provider()
assert provider['adapter'] == 'aliyun-token-plan/1'
assert set(provider) == {'adapter','base_url','key_env','model_env','configured','model'}
s = p.snapshot()
t = s['tables'][0]
c = p.contexts.capture(t['id'], [t['records'][0]['id']], [t['fields'][0]['id']],
    expected_revision=s['project']['revision'], title='Explicit', context_id=str(uuid4()))
m = p.discussion.add('Question', message_id=str(uuid4()), context_id=c['id'])
r = p.requests.create(m['id'], request_id=str(uuid4()), configuration={'adapter':'test-unregistered','model':'fixture'})
try:
    p.requests.start(r['id'])
    raise AssertionError('unregistered adapter started')
except ScriptError:
    pass
assert p.requests.get(r['id']) == r
assert p.requests.recover(r['id']) == r
''', project_handle=info['handle'])
    assert result['run']['state'] == 'succeeded', scripts.call('script.read', {'session': session})['text']
    assert not scripts.violations


@pytest.mark.parametrize('outcome,status,code', [
    ('complete', 'completed', None),
    ('truncated', 'failed', 'response_invalid'),
    ('rejected', 'failed', 'adapter_failed'),
    ('server-uncertain', 'uncertain', 'transport_uncertain'),
])
def test_registered_provider_wire_to_saved_result(inproc, model, monkeypatch, outcome, status, code):
    import http.client
    from suan.project import aliyun
    from test_aliyun import WireSocket, completion
    key = 'sk-sp-isolated-test-credential'
    monkeypatch.setenv(API_KEY_ENV, key)
    payload = completion()
    if outcome == 'truncated':
        payload['choices'][0]['finish_reason'] = 'length'
    http_status = {'rejected': 401, 'server-uncertain': 503}.get(outcome, 200)
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    socket = WireSocket((f'HTTP/1.1 {http_status} fixture\r\nContent-Type: application/json\r\n'
                         f'Content-Length: {len(body)}\r\n\r\n').encode('ascii') + body)
    connections = []
    def connection():
        conn = http.client.HTTPSConnection('token-plan.cn-beijing.maas.aliyuncs.com')
        conn.connect = lambda: setattr(conn, 'sock', socket)
        connections.append(conn)
        return conn
    monkeypatch.setattr(aliyun, '_connection', connection)
    h = inproc()
    p, saved = prepare(h, model)
    store, _ = model
    before, history = store.snapshot(), store.history()
    assert p.requests.start(saved['id'])['status'] == 'running'
    eventually(lambda: idle(h.bridge.projects._executor))
    result = p.requests.get(saved['id'])
    assert result['status'] == status and result['error_code'] == code
    if status == 'completed':
        message = p.discussion.get(result['result']['message_id'])
        assert message['text'] == payload['choices'][0]['message']['content']
        assert message['context_id'] == saved['context_id']
        assert result['result']['metadata']['remote_request_id'] == payload['id']
    else:
        assert result['result'] is None and len(p.discussion.list()['messages']) == 1
    assert p.requests.start(saved['id']) == result and len(connections) == 1
    headers, sent = b''.join(socket.sent).split(b'\r\n\r\n', 1)
    assert headers.startswith(b'POST /compatible-mode/v1/chat/completions HTTP/1.1')
    assert json.loads(sent)['model'] == 'fixture-model' and key.encode() not in sent
    assert key not in json.dumps(result) and store.snapshot() == before and store.history() == history
    assert not h.violations and h.events_of('project.changed') == []
