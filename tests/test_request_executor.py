"""Controlled adapters exercise one-send boundaries without network or credentials."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from uuid import uuid4

import pytest

from suan.project import ProjectError, ProjectStore
from suan.project.request_executor import (ConfirmedCancellation, DefinitiveFailure, RequestBusy,
                                          RequestExecutor, TextResponse, InvalidResponse, _RequestLock)
from test_project_contexts import model, capture, cell  # noqa: F401


def request(model, **configuration):
    store, _ = model
    context = capture(model)
    message = store.discussion.add("解释这组参数，不执行代码", message_id=str(uuid4()), context_id=context["id"])
    return store.requests.create(message["id"], request_id=str(uuid4()),
                                 configuration={"adapter": "controlled", "model": "text-test", **configuration})


def eventually(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    assert predicate(), "controlled worker did not reach its expected boundary"


def idle(executor):
    with executor._lock:
        return not executor._active


class ControlledAdapter:
    def __init__(self, result="Complete response", observe=None):
        self.result, self.observe = result, observe
        self.started, self.release = threading.Event(), threading.Event()
        self.inputs = []
        self.cancel_event = None

    def send(self, value, cancel_event):
        self.inputs.append(deepcopy(value))
        self.cancel_event = cancel_event
        if self.observe:
            self.observe()
        self.started.set()
        assert self.release.wait(8), "test adapter was not released"
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


@pytest.fixture
def executors():
    created = []
    def make(adapter=None):
        executor = RequestExecutor({"controlled": adapter} if adapter is not None else None)
        created.append((executor, adapter))
        return executor
    yield make
    for executor, adapter in created:
        executor.shutdown()
        if adapter is not None:
            adapter.release.set()
    for executor, _ in created:
        eventually(lambda: idle(executor))


def test_claim_is_durable_before_send_and_only_frozen_explicit_input_is_used(model, executors):
    store, ids = model
    saved = request(model, temperature=0.25)
    expected_input = store.requests.input(saved["id"])
    seen = []
    def observe():
        # A new connection sees the committed claim before the adapter begins.
        current = ProjectStore(store.directory).requests.get(saved["id"])
        seen.append((current["status"], current["executor_id"]))
    adapter = ControlledAdapter(TextResponse("结果说明；```python\nraise Exception()\n```",
                                            {"model": "actual-model", "remote_request_id": "reply-1", "output_tokens": 12}), observe)
    executor = executors(adapter)
    store.apply([cell(ids, "temperature", 450)], expected_revision=1)
    store.discussion.add("Later unselected message", message_id=str(uuid4()), context_id=saved["context_id"])
    before, history = store.snapshot(), store.history()
    started = executor.start(store, saved["id"])
    assert started["status"] == "running" and adapter.started.wait(5)
    assert seen == [("running", executor.executor_id)]
    assert adapter.inputs == [expected_input]
    assert adapter.inputs[0]["context"]["content"]["value"]["records"][0]["literals"][ids["temperature"]]["value"] == 300
    assert "Later unselected message" not in json.dumps(adapter.inputs)
    # The caller cannot change worker input through the returned claim.
    started["configuration"]["model"] = "caller-mutated"
    assert adapter.inputs[0]["configuration"]["model"] == "text-test"
    adapter.release.set()
    eventually(lambda: idle(executor))
    complete = store.requests.get(saved["id"])
    assert complete["status"] == "completed" and complete["result"]["metadata"]["output_tokens"] == 12
    assert store.discussion.get(complete["assistant_message_id"])["text"] == adapter.result.text
    assert store.snapshot() == before and store.history() == history


def test_duplicate_starts_across_executor_instances_send_once_and_live_recovery_is_refused(model, executors):
    store, _ = model
    saved = request(model)
    adapter = ControlledAdapter()
    first, second = executors(adapter), executors(adapter)
    barrier = threading.Barrier(2)
    def start(executor):
        barrier.wait(timeout=5)
        try:
            return executor.start(ProjectStore(store.directory), saved["id"])
        except RequestBusy:
            return None  # The first claimant has the lock but has not committed yet.
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(start, (first, second)))
    assert adapter.started.wait(5) and len(adapter.inputs) == 1
    assert any(item and item["status"] == "running" for item in results)
    assert second.start(store, saved["id"])["status"] == "running"
    with pytest.raises(RequestBusy, match="live executor"):
        second.recover(store, saved["id"])
    adapter.release.set()
    eventually(lambda: idle(first) and idle(second))
    assert first.start(store, saved["id"])["status"] == "completed"
    assert len(adapter.inputs) == 1 and len(store.discussion.list()["messages"]) == 2


def test_missing_adapter_and_cancel_before_start_never_claim_or_send(model, executors):
    store, _ = model
    saved = request(model)
    executor = executors()
    with pytest.raises(ProjectError, match="No trusted adapter"):
        executor.start(store, saved["id"])
    assert store.requests.get(saved["id"])["status"] == "pending"
    cancelled = executor.cancel(store, saved["id"])
    assert cancelled["status"] == "cancelled" and cancelled["executor_id"] is None
    assert executor.start(store, saved["id"]) == cancelled
    assert executor.recover(store, saved["id"]) == cancelled
    assert len(store.discussion.list()["messages"]) == 1


def test_cancellation_between_claim_and_dispatch_skips_adapter_send(model, executors, monkeypatch):
    store, _ = model
    saved = request(model)
    adapter = ControlledAdapter()
    executor = executors(adapter)
    dispatch, release = threading.Event(), threading.Event()
    original_run = executor._run
    def hold(job, adapter, frozen_input):
        dispatch.set()
        assert release.wait(5)
        original_run(job, adapter, frozen_input)
    monkeypatch.setattr(executor, "_run", hold)
    executor.start(store, saved["id"])
    assert dispatch.wait(5)
    try:
        assert executor.cancel(store, saved["id"])["status"] == "uncertain"
    finally:
        release.set()
    eventually(lambda: idle(executor))
    result = store.requests.get(saved["id"])
    assert result["status"] == "cancelled" and result["cancel_requested"]
    assert not adapter.started.is_set() and len(store.discussion.list()["messages"]) == 1


@pytest.mark.parametrize(("outcome", "status", "code"), [
    (DefinitiveFailure("secret-key-in-server-error"), "failed", "adapter_failed"),
    (TimeoutError("Bearer secret-key-in-server-error"), "uncertain", "transport_uncertain"),
    (RuntimeError("https://credential:secret-key-in-server-error@host"), "uncertain", "transport_uncertain"),
    (SystemExit("secret-key-in-server-error"), "uncertain", "transport_uncertain"),
    (None, "failed", "response_invalid"),
    ("", "failed", "response_invalid"),
    ("汉" * 21846, "failed", "response_invalid"),
    ("\ud800", "failed", "response_invalid"),
    (TextResponse("response", {"authorization": "secret-key-in-server-error"}), "failed", "response_invalid"),
    (TextResponse("response", {"output_tokens": True}), "failed", "response_invalid"),
], ids=["definitive-failure", "timeout", "unknown-failure", "interrupted-adapter", "missing-response",
        "empty-response", "oversized-response", "invalid-utf8", "credential-metadata", "boolean-token-count"])
def test_definite_failure_and_unknown_outcomes_have_safe_diagnostics_and_never_retry(model, executors, outcome, status, code):
    store, _ = model
    saved = request(model)
    adapter = ControlledAdapter(outcome)
    executor = executors(adapter)
    executor.start(store, saved["id"])
    assert adapter.started.wait(5)
    adapter.release.set()
    eventually(lambda: idle(executor))
    record = store.requests.get(saved["id"])
    assert record["status"] == status and record["error_code"] == code
    assert "secret-key-in-server-error" not in json.dumps(record)
    assert record["result"] is None and len(store.discussion.list()["messages"]) == 1
    assert executor.start(store, saved["id"]) == record and len(adapter.inputs) == 1


@pytest.mark.parametrize("confirmed", [False, True])
def test_cancel_intent_is_durable_and_only_confirmed_cancellation_claims_terminal_cancel(model, executors, confirmed):
    store, _ = model
    saved = request(model)
    adapter = ControlledAdapter(ConfirmedCancellation() if confirmed else TimeoutError())
    executor = executors(adapter)
    executor.start(store, saved["id"])
    assert adapter.started.wait(5)
    record = executor.cancel(store, saved["id"])
    assert record["status"] == "uncertain" and record["cancel_requested"] and adapter.cancel_event.is_set()
    assert store.requests.get(saved["id"])["cancel_requested"]
    adapter.release.set()
    eventually(lambda: idle(executor))
    record = store.requests.get(saved["id"])
    assert record["status"] == ("cancelled" if confirmed else "uncertain")
    assert record["cancel_requested"] and len(store.discussion.list()["messages"]) == 1


def test_valid_response_after_unconfirmed_cancel_is_linked_once_with_intent_preserved(model, executors):
    store, _ = model
    saved = request(model)
    adapter = ControlledAdapter()
    executor = executors(adapter)
    executor.start(store, saved["id"])
    assert adapter.started.wait(5)
    executor.cancel(store, saved["id"])
    adapter.release.set()
    eventually(lambda: idle(executor))
    complete = store.requests.get(saved["id"])
    assert complete["status"] == "completed" and complete["cancel_requested"]
    assert executor.cancel(store, saved["id"]) == complete
    assert len(store.discussion.list()["messages"]) == 2


def test_completed_result_wins_before_later_cancel_without_changing_message(model, executors):
    store, _ = model
    saved = request(model)
    adapter = ControlledAdapter()
    executor = executors(adapter)
    executor.start(store, saved["id"])
    assert adapter.started.wait(5)
    adapter.release.set()
    eventually(lambda: idle(executor))
    complete = store.requests.get(saved["id"])
    assert executor.cancel(store, saved["id"]) == complete
    assert not complete["cancel_requested"] and complete["status"] == "completed"


def test_shutdown_fences_late_responses_and_retains_lock_until_worker_exits(model, executors):
    store, _ = model
    saved = request(model)
    adapter = ControlledAdapter()
    executor = executors(adapter)
    executor.start(store, saved["id"])
    assert adapter.started.wait(5)
    executor.shutdown()
    stopped = store.requests.get(saved["id"])
    assert stopped["status"] == "uncertain" and stopped["error_code"] == "executor_lost"
    assert adapter.cancel_event.is_set()
    with pytest.raises(RequestBusy):
        _RequestLock(store, saved["id"])
    with pytest.raises(ProjectError, match="closed"):
        executor.start(store, saved["id"])
    adapter.release.set()
    eventually(lambda: idle(executor))
    assert store.requests.get(saved["id"]) == stopped
    assert len(store.discussion.list()["messages"]) == 1
    recovered = executors().recover(ProjectStore(store.directory), saved["id"])
    assert recovered == stopped
    lease = _RequestLock(store, saved["id"])
    lease.release()


def test_thread_dispatch_failure_records_proven_failure_without_calling_adapter(model, executors, monkeypatch):
    store, _ = model
    saved = request(model)
    adapter = ControlledAdapter()
    executor = executors(adapter)
    def unavailable(self):
        raise RuntimeError("secret from system")
    monkeypatch.setattr(threading.Thread, "start", unavailable)
    result = executor.start(store, saved["id"])
    assert result["status"] == "failed" and result["error_code"] == "dispatch_failed"
    assert not adapter.started.is_set() and idle(executor)
    assert len(store.discussion.list()["messages"]) == 1


def test_completion_storage_failure_leaves_no_half_message_or_resend(model, executors):
    store, _ = model
    saved = request(model)
    adapter = ControlledAdapter()
    executor = executors(adapter)
    executor.start(store, saved["id"])
    assert adapter.started.wait(5)
    with sqlite3.connect(store.path) as db:
        db.execute("""CREATE TRIGGER reject_completion BEFORE UPDATE ON project_requests
                      WHEN NEW.status = 'completed'
                      BEGIN SELECT RAISE(ABORT, 'storage unavailable'); END""")
    adapter.release.set()
    eventually(lambda: idle(executor))
    record = store.requests.get(saved["id"])
    assert record["status"] == "uncertain" and record["error_code"] == "local_save_failed"
    assert len(store.discussion.list()["messages"]) == 1
    with sqlite3.connect(store.path) as db:
        db.execute("DROP TRIGGER reject_completion")
    assert executor.start(store, saved["id"]) == record and len(adapter.inputs) == 1


def test_replaced_project_database_never_receives_old_completion(model, executors, tmp_path):
    store, _ = model
    saved = request(model)
    original_path = tmp_path / "original.sqlite3"
    replacement = ProjectStore.create(tmp_path / "replacement", "Other project")
    adapter = ControlledAdapter()
    executor = executors(adapter)
    executor.start(store, saved["id"])
    assert adapter.started.wait(5)
    shutil.copyfile(store.path, original_path)
    shutil.copyfile(replacement.path, store.path)
    adapter.release.set()
    eventually(lambda: idle(executor))
    other = ProjectStore(store.directory)
    assert other.info()["id"] == replacement.info()["id"] and other.requests.list()["requests"] == []
    assert other.discussion.list()["messages"] == []
    shutil.copyfile(original_path, store.path)
    reopened = ProjectStore(store.directory)
    assert reopened.requests.get(saved["id"])["status"] == "running"
    recovered = executors().recover(reopened, saved["id"])
    assert recovered["status"] == "uncertain" and recovered["error_code"] == "executor_lost"
    assert len(reopened.discussion.list()["messages"]) == 1


def test_recovery_does_not_send_after_process_death_and_live_process_holds_lock(model, executors, tmp_path):
    store, _ = model
    saved = request(model)
    marker = tmp_path / "adapter-entered"
    code = """
from pathlib import Path
import sys, threading
from suan.project import ProjectStore
from suan.project.request_executor import RequestExecutor
class Adapter:
    def send(self, frozen_input, cancel_event):
        Path(sys.argv[3]).write_text('entered', encoding='utf-8')
        threading.Event().wait()
executor = RequestExecutor({'controlled': Adapter()})
executor.start(ProjectStore(sys.argv[1]), sys.argv[2])
threading.Event().wait()
"""
    process = subprocess.Popen([sys.executable, "-c", code, str(store.directory), saved["id"], str(marker)],
                               cwd=Path(__file__).resolve().parents[1], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        eventually(lambda: marker.is_file() or process.poll() is not None)
        assert process.poll() is None, process.stderr.read().decode("utf-8")
        assert store.requests.get(saved["id"])["status"] == "running"
        executor = executors()
        with pytest.raises(RequestBusy):
            executor.recover(store, saved["id"])
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        process.stderr.close()
    # Opening and reading retain the journal verbatim; only explicit recover settles it.
    reopened = ProjectStore(store.directory)
    assert reopened.requests.get(saved["id"])["status"] == "running"
    executor = executors()
    recovered = executor.recover(reopened, saved["id"])
    assert recovered["status"] == "uncertain" and recovered["error_code"] == "executor_lost"
    assert executor.start(reopened, saved["id"]) == recovered
    assert len(reopened.discussion.list()["messages"]) == 1


def test_preflight_failure_keeps_pending_and_prepared_sender_captures_configuration(model, executors):
    saved = request(model)
    store, _ = model
    sender = ControlledAdapter()
    class Preparing:
        ready = False
        def send(self, value, cancel):
            raise AssertionError("unprepared sender called")
        def prepare(self, value):
            assert store.requests.get(saved["id"])["status"] == "pending"
            if not self.ready:
                raise ProjectError("Local configuration missing")
            return sender
    preparing = Preparing()
    executor = executors()
    executor._adapters["controlled"] = preparing
    with pytest.raises(ProjectError, match="configuration"):
        executor.start(store, saved["id"])
    assert store.requests.get(saved["id"])["status"] == "pending"
    assert store.requests.get(saved["id"])["executor_id"] is None
    preparing.ready = True
    try:
        assert executor.start(store, saved["id"])["status"] == "running"
        assert sender.started.wait(5)
    finally:
        sender.release.set()
    eventually(lambda: idle(executor))
    assert store.requests.get(saved["id"])["status"] == "completed"


def test_invalid_provider_response_is_known_failure_without_storing_raw_details(model, executors):
    store, _ = model
    saved = request(model)
    adapter = ControlledAdapter(InvalidResponse("sensitive response body"))
    executor = executors(adapter)
    executor.start(store, saved["id"])
    assert adapter.started.wait(5)
    adapter.release.set()
    eventually(lambda: idle(executor))
    result = store.requests.get(saved["id"])
    assert result["status"] == "failed" and result["error_code"] == "response_invalid"
    assert "sensitive" not in json.dumps(result) and result["result"] is None


def test_nonblocking_shutdown_fences_sends_before_waiting_for_database(model, executors, monkeypatch):
    store, _ = model
    saved = request(model)
    adapter = ControlledAdapter()
    executor = executors(adapter)
    executor.start(store, saved["id"])
    assert adapter.started.wait(5)
    entered, release = threading.Event(), threading.Event()
    original = executor._settle
    def delayed(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)
    monkeypatch.setattr(executor, "_settle", delayed)
    try:
        executor.shutdown(wait=False)
        assert executor._closing.is_set() and entered.wait(5)
        adapter.release.set()
    finally:
        release.set()
    eventually(lambda: idle(executor))
    result = store.requests.get(saved["id"])
    assert result["status"] == "uncertain" and result["result"] is None
    with pytest.raises(ProjectError, match="closed"):
        executor.start(store, saved["id"])


def test_worker_finishing_before_shutdown_thread_still_saves_uncertain(model, executors, monkeypatch):
    store, _ = model
    saved = request(model)
    adapter = ControlledAdapter('Must not publish after fence')
    executor = executors(adapter)
    executor.start(store, saved['id'])
    assert adapter.started.wait(5)
    entered, resume = threading.Event(), threading.Event()
    original = threading.Thread
    shutdown_threads = []
    def delayed_thread(*args, **kwargs):
        if kwargs.get('name') == 'stk-request-shutdown':
            target = kwargs['target']
            def delayed():
                entered.set()
                assert resume.wait(5)
                target()
            kwargs['target'] = delayed
        thread = original(*args, **kwargs)
        shutdown_threads.append(thread)
        return thread
    monkeypatch.setattr(threading, 'Thread', delayed_thread)
    try:
        executor.shutdown(wait=False)
        assert entered.wait(5)
        adapter.release.set()
        eventually(lambda: idle(executor))
        result = store.requests.get(saved['id'])
        assert result['status'] == 'uncertain' and result['result'] is None
        assert result['error_code'] == 'executor_lost'
    finally:
        resume.set()
        for thread in shutdown_threads:
            thread.join(5)
