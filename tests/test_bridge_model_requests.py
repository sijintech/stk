"""Explicit provider execution through the bridge, with controlled non-network adapters."""
import json
from uuid import uuid4

import pytest

from suan.project import ProjectStore
from suan.desktop_bridge.schema import validate_outgoing, validate_params
from suan.project.aliyun import ALIYUN_ADAPTER, API_KEY_ENV, MODEL_ENV, BASE_URL
from suan.project.request_executor import ConfirmedCancellation
from suan.scripting import Project
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_project_contexts import model, capture  # noqa: F401
from test_request_executor import ControlledAdapter, StreamingAdapter, eventually, idle
from test_desktop_scripts import scripts, execute  # noqa: F401


def prepare(harness, model, *, prompt_version="stk.text/1"):
    store, _ = model
    context = capture(model)
    message = store.discussion.add('Explain saved values', message_id=str(uuid4()), context_id=context['id'])
    info = harness.call('project.open', {'directory': str(store.directory)})['project']
    p = Project(lambda method, params: harness.call(method, params), info['handle'])
    saved = p.requests.create(message['id'], request_id=str(uuid4()),
                             configuration={'adapter': ALIYUN_ADAPTER, 'model': 'fixture-model'},
                             prompt_version=prompt_version)
    return p, saved


def parameter_reply(model, saved, *, value=320):
    _, ids = model
    return json.dumps({'format': 'stk.parameter-edits/1', 'context_id': saved['context_id'],
        'base_revision': saved['source_revision'], 'summary': 'Inspect a higher temperature.',
        'edits': [{'record_id': ids['first'], 'field_id': ids['temperature'], 'value': value}]})


def completed_parameter(harness, model, *, prompt_version='stk.parameter-edits/1', text=None):
    p, saved = prepare(harness, model, prompt_version=prompt_version)
    store, _ = model
    owner = str(uuid4())
    assert store.requests._claim(saved['id'], executor_id=owner)[1]
    store.requests._complete(saved['id'], executor_id=owner,
                             text=parameter_reply(model, saved) if text is None else text)
    return p, saved


def test_parameter_reply_requires_explicit_conversion_and_separate_apply(inproc, model):
    h = inproc()
    p, saved = prepare(h, model, prompt_version='stk.parameter-edits/1')
    store, ids = model
    before, history = store.snapshot(), store.history()
    executor = h.bridge.projects._executor
    adapter = ControlledAdapter(parameter_reply(model, saved))
    executor._adapters[ALIYUN_ADAPTER] = adapter
    try:
        assert p.requests.edit_proposal(saved['id']) == {'request_id': saved['id'], 'draft': None, 'proposal': None}
        assert p.requests.start(saved['id'])['status'] == 'running'
        assert adapter.started.wait(5)
    finally:
        adapter.release.set()
    eventually(lambda: idle(executor))
    assert len(adapter.inputs) == 1
    assert adapter.inputs[0]['prompt_version'] == 'stk.parameter-edits/1'
    assert p.requests.get(saved['id'])['status'] == 'completed'
    assert p.drafts.list()['drafts'] == []
    assert p.requests.edit_proposal(saved['id']) == {'request_id': saved['id'], 'draft': None, 'proposal': None}
    result = p.requests.propose_edits(saved['id'], expected_revision=1)
    assert result['replayed'] is False and result['draft']['status'] == 'pending'
    assert result['draft']['commands'] == [{'op': 'set_cell', 'table_id': ids['table'],
        'record_id': ids['first'], 'field_id': ids['temperature'], 'value': 320}]
    assert result['proposal']['message_id'] == saved['assistant_message_id']
    assert result['proposal']['context_id'] == saved['context_id']
    assert result['proposal']['draft_id'] == result['draft']['id']
    assert p.requests.edit_proposal(saved['id']) == {k: v for k, v in result.items() if k != 'replayed'}
    assert p.requests.propose_edits(saved['id'], expected_revision=1) == {**result, 'replayed': True}
    assert store.snapshot() == before and store.history() == history
    assert h.events_of('project.changed') == []
    with store._connect() as db:
        assert db.execute('SELECT count(*) FROM run_plans').fetchone()[0] == 0
    assert p.drafts.apply(result['draft']['id'], expected_revision=1)['revision'] == 2
    assert store.snapshot()['tables'][0]['records'][0]['values'][ids['temperature']] == 320
    assert len(adapter.inputs) == 1 and not h.violations


@pytest.mark.parametrize('terminal', ['applied', 'discarded'])
def test_parameter_pair_reopens_and_recovers_terminal_receipt_without_rebase(inproc, model, terminal):
    h = inproc()
    p, saved = completed_parameter(h, model)
    store, _ = model
    pair = p.requests.propose_edits(saved['id'], expected_revision=1)
    if terminal == 'applied':
        p.drafts.apply(pair['draft']['id'], expected_revision=1)
        p.undo(expected_revision=2)
    else:
        p.drafts.discard(pair['draft']['id'])
        p.apply([{'op': 'rename_table', 'id': model[1]['table'], 'name': 'Changed'}], expected_revision=1)
    before, history = store.snapshot(), store.history()
    h.call('project.close', {'handle': p.handle})
    second = inproc(state='reopened')
    info = second.call('project.open', {'directory': str(store.directory)})['project']
    p = Project(lambda method, params: second.call(method, params), info['handle'])
    restored = p.requests.edit_proposal(saved['id'])
    assert restored['draft']['id'] == pair['draft']['id'] and restored['draft']['status'] == terminal
    assert restored['proposal'] == pair['proposal']
    assert p.requests.propose_edits(saved['id'], expected_revision=1) == {**restored, 'replayed': True}
    assert p.drafts.list()['drafts'][0]['status'] == terminal
    assert store.snapshot() == before and store.history() == history
    assert second.events_of('project.changed') == [] and not second.violations


@pytest.mark.parametrize('scenario,code', [
    ('pending', 'conflict'), ('text', 'invalid_params'), ('malformed', 'invalid_params'),
    ('stale', 'conflict'), ('wrong-revision', 'conflict'), ('foreign-project', 'invalid_params'),
])
def test_parameter_conversion_errors_preserve_project_and_create_no_pair(inproc, model, scenario, code):
    h = inproc()
    if scenario == 'pending':
        p, saved = prepare(h, model, prompt_version='stk.parameter-edits/1')
    else:
        p, saved = completed_parameter(h, model,
            prompt_version='stk.text/1' if scenario == 'text' else 'stk.parameter-edits/1',
            text='```json\n{}\n```' if scenario == 'malformed' else None)
    store, ids = model
    if scenario == 'stale':
        store.apply([{'op': 'rename_table', 'id': ids['table'], 'name': 'Changed externally'}], expected_revision=1)
    before, history = store.snapshot(), store.history()
    handle = p.handle
    if scenario == 'foreign-project':
        handle = h.call('project.create', {'directory': str(store.directory.parent / 'other'), 'name': 'Other'})['project']['handle']
    assert h.error('project.requests.propose_edits', {'handle': handle, 'request_id': saved['id'],
        'expected_revision': 2 if scenario == 'wrong-revision' else 1})['code'] == code
    assert p.requests.edit_proposal(saved['id']) == {'request_id': saved['id'], 'draft': None, 'proposal': None}
    assert store.drafts.list()['drafts'] == [] and store.discussion.proposals()['proposals'] == []
    assert store.snapshot() == before and store.history() == history
    assert h.events_of('project.changed') == [] and not h.violations


def test_parameter_contract_rejects_extra_fields_invalid_preconditions_and_partial_pairs(inproc, model):
    h = inproc()
    p, saved = completed_parameter(h, model)
    params = {'handle': p.handle, 'request_id': saved['id'], 'expected_revision': 1}
    for invalid in (None, True, -1, 1.5, 2**63, '1'):
        malformed = {**params, 'expected_revision': invalid}
        assert validate_params('project.requests.propose_edits', malformed)
        assert h.error('project.requests.propose_edits', malformed)['code'] == 'invalid_params'
    for key, value in [('commands', []), ('draft_id', str(uuid4())), ('force', True), ('api_key', 'never-stored')]:
        assert h.error('project.requests.propose_edits', {**params, key: value})['code'] == 'invalid_params'
    assert h.error('project.requests.edit_proposal', params)['code'] == 'invalid_params'
    pair = p.requests.propose_edits(saved['id'], expected_revision=1)
    read = {k: v for k, v in pair.items() if k != 'replayed'}
    for method, result in [('project.requests.propose_edits', pair), ('project.requests.edit_proposal', read)]:
        assert not validate_outgoing({'id': 'schema-check', 'result': result}, method)
        for key in ('draft', 'proposal'):
            assert validate_outgoing({'id': 'schema-check', 'result': {**result, key: {}}}, method)
            assert validate_outgoing({'id': 'schema-check', 'result': {**result, key: None}}, method)
            assert validate_outgoing({'id': 'schema-check', 'result': {**result, key: {**result[key], 'extra': True}}}, method)
    assert not h.violations


def test_missing_credentials_status_and_closed_handles_never_claim(inproc, model, monkeypatch):
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    monkeypatch.setenv(MODEL_ENV, 'fixture-model')
    h = inproc()
    p, saved = prepare(h, model)
    store, _ = model
    before, history = store.snapshot(), store.history()
    assert p.requests.provider() == {'adapter': ALIYUN_ADAPTER, 'base_url': BASE_URL,
        'key_env': API_KEY_ENV, 'model_env': MODEL_ENV, 'configured': False, 'model': 'fixture-model',
        'key_source': '', 'can_remember': True}
    error = h.error('project.requests.start', {'handle': p.handle, 'request_id': saved['id']})
    assert error['code'] == 'invalid_params'
    assert p.requests.get(saved['id']) == saved
    assert p.requests.recover(saved['id']) == saved
    assert h.call('project.close', {'handle': p.handle})['closed']
    for method, extra in [('provider', {}), ('start', {'request_id': saved['id']}), ('recover', {'request_id': saved['id']}),
                          ('progress', {'request_id': saved['id']})]:
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
assert set(provider) == {'adapter','base_url','key_env','model_env','configured','model','key_source','can_remember'}
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
assert p.requests.progress(r['id']) == {'request': r, 'progress': None}
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
    from test_aliyun import WireSocket, stream_records, sse_body
    key = 'sk-sp-isolated-test-credential'
    monkeypatch.setenv(API_KEY_ENV, key)
    payload = stream_records()
    if outcome == 'truncated':
        payload[1]['choices'][0]['finish_reason'] = 'length'
    http_status = {'rejected': 401, 'server-uncertain': 503}.get(outcome, 200)
    body = sse_body(payload)
    socket = WireSocket((f'HTTP/1.1 {http_status} fixture\r\nContent-Type: text/event-stream\r\n'
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
        assert message['text'] == '温度 300 K。'
        assert message['context_id'] == saved['context_id']
        assert result['result']['metadata']['remote_request_id'] == payload[0]['id']
    else:
        assert result['result'] is None and len(p.discussion.list()['messages']) == 1
    assert p.requests.start(saved['id']) == result and len(connections) == 1
    headers, sent = b''.join(socket.sent).split(b'\r\n\r\n', 1)
    assert headers.startswith(b'POST /compatible-mode/v1/chat/completions HTTP/1.1')
    assert json.loads(sent)['model'] == 'fixture-model' and json.loads(sent)['stream'] is True and key.encode() not in sent
    assert key not in json.dumps(result) and store.snapshot() == before and store.history() == history
    assert not h.violations and h.events_of('project.changed') == []


def test_bridge_progress_tracks_original_handle_owner_and_never_publishes_partial_messages(inproc, model, monkeypatch):
    h = inproc()
    p, saved = prepare(h, model)
    adapter = StreamingAdapter(["正在", "分析"], "正在分析，完成")
    executor = h.bridge.projects._executor
    executor._adapters[ALIYUN_ADAPTER] = adapter
    store, _ = model
    before, history = store.snapshot(), store.history()
    monkeypatch.setenv(API_KEY_ENV, 'test-credential-never-in-progress')
    assert p.requests.progress(saved['id']) == {'request': saved, 'progress': None}
    try:
        p.requests.start(saved['id'])
        assert adapter.emitted.wait(5)
        observed = p.requests.progress(saved['id'])
        assert observed['progress'] == {'executor_id': executor.executor_id, 'sequence': 2,
                                         'text': '正在分析', 'text_bytes': 12}
        assert len(p.discussion.list()['messages']) == 1
        assert 'test-credential-never-in-progress' not in json.dumps(observed)
        other_bridge = inproc(state='other-progress-owner')
        foreign = other_bridge.call('project.open', {'directory': str(store.directory)})['project']
        assert other_bridge.call('project.requests.progress', {'handle': foreign['handle'], 'request_id': saved['id']}) == {
            'request': observed['request'], 'progress': None}
        assert h.call('project.close', {'handle': p.handle})['closed']
        assert h.error('project.requests.progress', {'handle': p.handle, 'request_id': saved['id']})['code'] == 'not_found'
        other_project = h.call('project.create', {'directory': str(store.directory.parent / 'other'), 'name': 'Other'})['project']
        assert h.error('project.requests.progress', {'handle': other_project['handle'], 'request_id': saved['id']})['code'] == 'invalid_params'
        reopened = h.call('project.open', {'directory': str(store.directory)})['project']
        assert reopened['handle'] != p.handle
        p = Project(lambda method, params: h.call(method, params), reopened['handle'])
        assert p.requests.progress(saved['id']) == observed
        cancelled = p.requests.cancel(saved['id'])
        adapter.on_text('，完成')
        assert p.requests.progress(saved['id']) == {'request': cancelled, 'progress': None}
    finally:
        adapter.release.set()
    eventually(lambda: idle(executor))
    result = p.requests.progress(saved['id'])
    assert result['progress'] is None and result['request']['status'] == 'completed'
    assert result['request']['cancel_requested'] and p.discussion.get(saved['assistant_message_id'])['text'] == '正在分析，完成'
    assert store.snapshot() == before and store.history() == history
    assert not h.events_of('project.changed') and not h.violations and not other_bridge.violations


def test_bridge_progress_after_shutdown_is_empty_in_a_new_executor(inproc, model):
    h = inproc()
    p, saved = prepare(h, model)
    adapter = StreamingAdapter()
    executor = h.bridge.projects._executor
    executor._adapters[ALIYUN_ADAPTER] = adapter
    p.requests.start(saved['id'])
    assert adapter.emitted.wait(5)
    assert p.requests.progress(saved['id'])['progress'] is not None
    h.bridge.shutdown()
    adapter.on_text('late ignored')
    adapter.release.set()
    eventually(lambda: idle(executor))
    second = inproc(state='after-progress-shutdown')
    store, _ = model
    reopened = second.call('project.open', {'directory': str(store.directory)})['project']
    result = second.call('project.requests.progress', {'handle': reopened['handle'], 'request_id': saved['id']})
    assert result['progress'] is None and result['request']['status'] == 'uncertain'
    assert len(store.discussion.list()['messages']) == 1 and len(adapter.inputs) == 1
    assert not second.violations


def test_bridge_capacity_error_leaves_ninth_request_pending(inproc, model):
    from suan.project.request_executor import MAX_ACTIVE_REQUESTS
    h = inproc()
    prepared = [prepare(h, model) for _ in range(MAX_ACTIVE_REQUESTS + 1)]
    adapter = ControlledAdapter()
    executor = h.bridge.projects._executor
    executor._adapters[ALIYUN_ADAPTER] = adapter
    try:
        for p, saved in prepared[:-1]:
            assert p.requests.start(saved['id'])['status'] == 'running'
        p, saved = prepared[-1]
        error = h.error('project.requests.start', {'handle': p.handle, 'request_id': saved['id']})
        assert error['code'] == 'busy' and '8-request limit' in error['message']
        assert p.requests.progress(saved['id']) == {'request': saved, 'progress': None}
    finally:
        adapter.release.set()
    eventually(lambda: idle(executor))
    assert not h.violations


def test_usage_reads_receipts_through_the_bridge_and_scripting(inproc, model):
    h = inproc()
    p, saved = prepare(h, model)
    store, _ = model
    owner = str(uuid4())
    assert store.requests._claim(saved['id'], executor_id=owner)[1]
    store.requests._complete(saved['id'], executor_id=owner, text='ok',
                             metadata={'model': 'fixture-model', 'input_tokens': 42, 'output_tokens': 7})
    before = store.snapshot()
    usage = p.requests.usage()
    assert usage == {'requests': 1, 'completed': 1, 'reported': 1, 'input_tokens': 42, 'output_tokens': 7,
                     'models': [{'model': 'fixture-model', 'requests': 1, 'input_tokens': 42, 'output_tokens': 7}]}
    assert store.snapshot() == before and not h.violations


def test_sweep_proposals_convert_through_the_bridge(inproc, model):
    h = inproc()
    p, saved = prepare(h, model, prompt_version='stk.parameter-sweep/1')
    store, ids = model
    owner = str(uuid4())
    assert store.requests._claim(saved['id'], executor_id=owner)[1]
    reply = {'format': 'stk.parameter-sweep/1', 'context_id': saved['context_id'], 'base_revision': saved['source_revision'],
             'summary': 'Three temperatures.', 'base_record_id': ids['first'],
             'axes': [{'field_id': ids['temperature'], 'values': [300, 320, 340]}], 'mode': 'product'}
    store.requests._complete(saved['id'], executor_id=owner, text=json.dumps(reply))
    converted = p.requests.propose_edits(saved['id'], expected_revision=saved['source_revision'])
    assert sum(command['op'] == 'add_record' for command in converted['draft']['commands']) == 3
    assert p.requests.edit_proposal(saved['id'])['draft']['id'] == converted['draft']['id']
    assert not h.violations
