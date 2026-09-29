"""The real console persists selected context and plain-text provenance without executing it."""

from test_desktop_bridge import bridge_env  # noqa: F401
from test_desktop_scripts import scripts, execute  # noqa: F401
from test_project_values import model  # noqa: F401


def test_python_context_and_discussion_facades_preserve_provenance_across_workers(scripts, model, tmp_path):
    store, ids = model
    project = scripts.call("project.open", {"directory": str(store.directory)})["project"]
    baseline, history = store.snapshot(), store.history()
    session = scripts.call("script.open")["session"]
    marker = tmp_path / "must-not-execute"
    source = f'''
from uuid import uuid4
from suan.scripting import ScriptError
p = stk.project
ids = {ids!r}
context_id, message_id, draft_id, proposal_id = (str(uuid4()) for _ in range(4))
context = p.contexts.capture(ids['inputs'], [ids['input_row']], [ids['temperature']],
                            expected_revision=1, title='Selected temperature', context_id=context_id)
assert context['source_revision'] == 1
assert context['content']['value']['records'][0]['literals'][ids['temperature']]['value'] == 300
assert p.contexts.get(context_id) == context
assert p.contexts.list(limit=1)['contexts'][0]['id'] == context_id
text = {f"__import__('pathlib').Path({str(marker)!r}).write_text('unexpected execution')"!r}
message = p.discussion.add(text, message_id=message_id, context_id=context_id, role='assistant')
assert message['role'] == 'assistant' and message['text'] == text
assert p.discussion.get(message_id) == message
assert p.discussion.list()['messages'][0]['text_bytes'] == len(text.encode('utf-8'))
draft = p.drafts.save([{{'op':'set_cell', 'table_id':ids['inputs'], 'record_id':ids['input_row'],
                       'field_id':ids['temperature'], 'value':350}}],
                      expected_revision=1, title='Proposal', draft_id=draft_id)
proposal = p.discussion.link_draft(message_id, draft_id, proposal_id=proposal_id)
assert proposal['context_id'] == context_id and proposal['base_revision'] == 1
assert p.discussion.link_draft(message_id, draft_id, proposal_id=proposal_id) == proposal
assert p.discussion.proposals(draft_id=draft_id)['proposals'] == [proposal]
assert p.discussion.proposals(offset=1)['proposals'] == []
assert p.drafts.get(draft_id)['status'] == 'pending'
assert p.snapshot()['project']['revision'] == 1
p.close()
try:
    p.contexts.get(context_id)
except ScriptError as error:
    assert error.code == 'not_found'
else:
    raise AssertionError('closed pinned project was accepted')
'''
    result = execute(scripts, session, source, project_handle=project["handle"])
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})["text"]
    assert not marker.exists()
    assert store.snapshot() == baseline and store.history() == history
    assert scripts.events_of("project.changed") == []
    assert scripts.call("script.close", {"session": session})["closed"]
    session = scripts.call("script.open")["session"]
    result = execute(scripts, session, f'''
p = stk.projects.open({str(store.directory)!r})
summaries = p.contexts.list()['contexts']
assert len(summaries) == 1
context = p.contexts.get(summaries[0]['id'])
summary = p.discussion.list()['messages'][0]
message = p.discussion.get(summary['id'])
assert message['context_id'] == context['id'] and message['role'] == 'assistant'
proposal = p.discussion.proposals()['proposals'][0]
assert proposal['message_id'] == message['id'] and proposal['context_id'] == context['id']
assert p.drafts.get(proposal['draft_id'])['status'] == 'pending'
assert p.snapshot()['project']['revision'] == 1
''')
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})["text"]
    assert not marker.exists()
    assert store.snapshot() == baseline and store.history() == history
    assert scripts.events_of("project.changed") == []
    assert not scripts.violations
