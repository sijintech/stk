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


class StreamingAdapter(ControlledAdapter):
    """A controlled delta sender; no network, credentials, or background emitter."""

    def __init__(self, chunks=("partial",), result=None):
        super().__init__("".join(chunks) if result is None and all(isinstance(x, str) for x in chunks) else result)
        self.chunks = chunks
        self.on_text = None
        self.emitted = threading.Event()

    def send(self, value, cancel_event):
        raise AssertionError("The optional streaming method should be preferred")

    def send_stream(self, value, cancel_event, on_text):
        self.inputs.append(deepcopy(value))
        self.cancel_event, self.on_text = cancel_event, on_text
        self.started.set()
        for chunk in self.chunks:
            on_text(chunk)
        self.emitted.set()
        assert self.release.wait(8), "test stream was not released"
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def test_progress_returns_bounded_utf8_snapshots_and_only_completion_publishes(model, executors):
    store, _ = model
    saved = request(model)
    chunks = ["你", "好", "\n", "🙂"]
    adapter = StreamingAdapter(chunks)
    executor = executors(adapter)
    before, history = store.snapshot(), store.history()
    assert executor.progress(store, saved["id"]) == {"request": saved, "progress": None}
    executor.start(store, saved["id"])
    assert adapter.emitted.wait(5)
    observed = executor.progress(store, saved["id"])
    assert observed["request"]["status"] == "running" and observed["request"]["result"] is None
    assert observed["progress"] == {"executor_id": executor.executor_id, "sequence": 4,
                                    "text": "你好\n🙂", "text_bytes": 11}
    assert len(store.discussion.list()["messages"]) == 1
    assert executor.progress(store, saved["id"]) == observed
    adapter.on_text("")
    assert executor.progress(store, saved["id"]) == observed
    observed["progress"]["text"] = "caller mutation"
    assert executor.progress(store, saved["id"])["progress"]["text"] == "你好\n🙂"
    adapter.release.set()
    eventually(lambda: idle(executor))
    result = executor.progress(store, saved["id"])
    assert result["progress"] is None and result["request"]["status"] == "completed"
    assert store.discussion.get(saved["assistant_message_id"])["text"] == "你好\n🙂"
    assert store.snapshot() == before and store.history() == history


def test_progress_starts_with_sequence_zero_and_never_crosses_executor_or_path(model, executors, tmp_path):
    store, _ = model
    saved = request(model)
    adapter = StreamingAdapter((), "complete")
    executor, foreign = executors(adapter), executors()
    executor.start(store, saved["id"])
    assert adapter.emitted.wait(5)
    snapshot = executor.progress(store, saved["id"])
    assert snapshot["progress"] == {"executor_id": executor.executor_id, "sequence": 0, "text": "", "text_bytes": 0}
    assert foreign.progress(store, saved["id"]) == {"request": snapshot["request"], "progress": None}
    copied = tmp_path / "copied"
    copied.mkdir()
    shutil.copyfile(store.path, copied / "project.sqlite3")
    assert executor.progress(ProjectStore(copied), saved["id"]) == {"request": snapshot["request"], "progress": None}
    # A new store object for the same original path may read this live owner's buffer.
    assert executor.progress(ProjectStore(store.directory), saved["id"]) == snapshot
    adapter.on_text("complete")
    assert executor.progress(store, saved["id"])["progress"]["sequence"] == 1
    adapter.release.set()
    eventually(lambda: idle(executor))


def test_nonstreaming_request_progress_is_always_null(model, executors):
    store, _ = model
    saved = request(model)
    adapter = ControlledAdapter()
    executor = executors(adapter)
    executor.start(store, saved["id"])
    assert adapter.started.wait(5)
    result = executor.progress(store, saved["id"])
    assert result["progress"] is None and result["request"]["status"] == "running"
    adapter.release.set()
    eventually(lambda: idle(executor))
    assert executor.progress(store, saved["id"])["progress"] is None


def test_cancel_hides_progress_but_valid_late_full_response_can_still_complete(model, executors):
    store, _ = model
    saved = request(model)
    adapter = StreamingAdapter(["before"], "beforeafter")
    executor = executors(adapter)
    executor.start(store, saved["id"])
    assert adapter.emitted.wait(5)
    assert executor.progress(store, saved["id"])["progress"]["text"] == "before"
    cancelled = executor.cancel(store, saved["id"])
    assert cancelled["status"] == "uncertain" and cancelled["cancel_requested"]
    adapter.on_text("after")
    assert executor.progress(store, saved["id"]) == {"request": cancelled, "progress": None}
    adapter.release.set()
    eventually(lambda: idle(executor))
    completed = executor.progress(store, saved["id"])
    assert completed["progress"] is None and completed["request"]["status"] == "completed"
    assert completed["request"]["cancel_requested"]
    assert store.discussion.get(saved["assistant_message_id"])["text"] == "beforeafter"


def test_external_cancel_or_confirmed_terminal_hides_live_buffer(model, executors):
    store, _ = model
    saved = request(model)
    adapter = StreamingAdapter()
    executor = executors(adapter)
    executor.start(store, saved["id"])
    assert adapter.emitted.wait(5)
    assert executor.progress(store, saved["id"])["progress"] is not None
    store.requests.cancel(saved["id"])
    assert not adapter.cancel_event.is_set()  # Different callers cannot signal this worker.
    assert executor.progress(store, saved["id"])["progress"] is None
    cancelled = store.requests._settle(saved["id"], executor_id=executor.executor_id,
                                       status="cancelled", code="cancel_confirmed")
    assert executor.progress(store, saved["id"]) == {"request": cancelled, "progress": None}
    adapter.release.set()
    eventually(lambda: idle(executor))
    assert len(store.discussion.list()["messages"]) == 1


def test_shutdown_hides_and_fences_stream_but_retains_lock_until_worker_exits(model, executors):
    store, _ = model
    saved = request(model)
    adapter = StreamingAdapter()
    executor = executors(adapter)
    executor.start(store, saved["id"])
    assert adapter.emitted.wait(5)
    job = next(iter(executor._active.values()))
    executor.shutdown(wait=False)
    adapter.on_text("must be ignored")
    assert executor.progress(store, saved["id"])["progress"] is None
    with pytest.raises(RequestBusy):
        _RequestLock(store, saved["id"])
    adapter.release.set()
    eventually(lambda: idle(executor))
    adapter.on_text("\ud800")  # Even malformed retained callbacks are ignored after closure.
    assert not job.text and not job.accepting.is_set()
    assert store.requests.get(saved["id"])["status"] == "uncertain"
    assert len(store.discussion.list()["messages"]) == 1


def test_stream_callback_closes_before_complete_response_validation(model, executors, monkeypatch):
    import suan.project.request_executor as module
    store, _ = model
    saved = request(model)
    adapter = StreamingAdapter()
    executor = executors(adapter)
    executor.start(store, saved["id"])
    assert adapter.emitted.wait(5)
    entered, release = threading.Event(), threading.Event()
    original = module._validate_metadata
    def block(metadata):
        entered.set()
        assert release.wait(5)
        return original(metadata)
    monkeypatch.setattr(module, "_validate_metadata", block)
    adapter.release.set()
    try:
        assert entered.wait(5)
        adapter.on_text("late after adapter returned")
        snapshot = executor.progress(store, saved["id"])
        assert snapshot["progress"] is None and snapshot["request"]["status"] == "running"
    finally:
        release.set()
    eventually(lambda: idle(executor))
    assert store.requests.get(saved["id"])["status"] == "completed"
    assert store.discussion.get(saved["assistant_message_id"])["text"] == "partial"


@pytest.mark.parametrize("chunks", [[None], [123], ["\ud800"], ["x" * 65537], ["汉" * 21846],
                                    ["a" * 65536, "b"]],
                         ids=["null", "integer", "invalid-utf8", "large-chunk", "utf8-limit", "cumulative-limit"])
def test_invalid_or_oversized_stream_is_failed_without_partial_message(model, executors, chunks):
    store, _ = model
    saved = request(model)
    adapter = StreamingAdapter(chunks, "safe final cannot hide invalid chunks")
    executor = executors(adapter)
    executor.start(store, saved["id"])
    eventually(lambda: idle(executor))
    record = store.requests.get(saved["id"])
    assert record["status"] == "failed" and record["error_code"] == "response_invalid"
    assert executor.progress(store, saved["id"])["progress"] is None
    assert len(store.discussion.list()["messages"]) == 1


def test_swallowed_callback_error_or_mismatched_final_cannot_publish(model, executors):
    from suan.project.request_executor import InvalidResponse
    store, _ = model
    class Swallowing(StreamingAdapter):
        def send_stream(self, value, cancel_event, on_text):
            try:
                on_text(None)
            except InvalidResponse:
                pass
            return "apparently complete"
    for adapter in (Swallowing(), StreamingAdapter(["observed"], "different final")):
        saved = request(model)
        executor = executors(adapter)
        executor.start(store, saved["id"])
        adapter.release.set()
        eventually(lambda: idle(executor))
        assert store.requests.get(saved["id"])["error_code"] == "response_invalid"
    assert len(store.discussion.list()["messages"]) == 2  # Only the two saved user messages.


def test_stream_limit_accepts_exact_utf8_boundary_and_cleanup_releases_buffer(model, executors):
    store, _ = model
    saved = request(model)
    text = "🙂" * 16384
    adapter = StreamingAdapter([text])
    executor = executors(adapter)
    executor.start(store, saved["id"])
    assert adapter.emitted.wait(5)
    job = next(iter(executor._active.values()))
    progress = executor.progress(store, saved["id"])["progress"]
    assert progress["text_bytes"] == 65536 and progress["text"] == text
    adapter.release.set()
    eventually(lambda: idle(executor))
    assert not job.text and store.discussion.get(saved["assistant_message_id"])["text"] == text


def test_progress_validates_replaced_database_before_returning_cached_text(model, executors, tmp_path):
    store, _ = model
    saved = request(model)
    adapter = StreamingAdapter()
    executor = executors(adapter)
    executor.start(store, saved["id"])
    assert adapter.emitted.wait(5)
    original = tmp_path / "original.sqlite3"
    shutil.copyfile(store.path, original)
    other = ProjectStore.create(tmp_path / "other", "Other")
    shutil.copyfile(other.path, store.path)
    try:
        with pytest.raises(ProjectError, match="replaced"):
            executor.progress(store, saved["id"])
    finally:
        shutil.copyfile(original, store.path)
        adapter.release.set()
    eventually(lambda: idle(executor))


def test_capacity_limit_preserves_pending_and_cancelled_live_workers_keep_their_slot(model, executors):
    from suan.project.request_executor import MAX_ACTIVE_REQUESTS
    store, _ = model
    saved = [request(model) for _ in range(MAX_ACTIVE_REQUESTS + 1)]
    adapter = ControlledAdapter()
    executor = executors(adapter)
    for item in saved[:-1]:
        assert executor.start(store, item["id"])["status"] == "running"
    eventually(lambda: len(adapter.inputs) == MAX_ACTIVE_REQUESTS)
    # Repeated starts at capacity still return the one saved attempt.
    assert executor.start(store, saved[0]["id"])["status"] == "running"
    with pytest.raises(RequestBusy, match="8 active"):
        executor.start(store, saved[-1]["id"])
    assert executor.progress(store, saved[-1]["id"]) == {"request": saved[-1], "progress": None}
    executor.cancel(store, saved[0]["id"])
    with pytest.raises(RequestBusy, match="8 active"):
        executor.start(store, saved[-1]["id"])
    adapter.release.set()
    eventually(lambda: idle(executor))
    executor.start(store, saved[-1]["id"])
    eventually(lambda: idle(executor))
    assert len(adapter.inputs) == MAX_ACTIVE_REQUESTS + 1
    assert store.requests.get(saved[-1]["id"])["status"] == "completed"


def test_preflight_and_dispatch_failures_never_leak_capacity_slots(model, executors, monkeypatch):
    from suan.project.request_executor import MAX_ACTIVE_REQUESTS
    store, _ = model
    class PreparationFailure(ControlledAdapter):
        def prepare(self, frozen_input):
            raise ProjectError("local preflight failed")
    executor = executors(PreparationFailure())
    for _ in range(MAX_ACTIVE_REQUESTS + 1):
        saved = request(model)
        with pytest.raises(ProjectError, match="preflight"):
            executor.start(store, saved["id"])
        assert store.requests.get(saved["id"]) == saved and idle(executor)
    adapter = ControlledAdapter()
    executor._adapters["controlled"] = adapter
    with monkeypatch.context() as patch:
        def fail_start(self):
            raise RuntimeError("dispatch failure")
        patch.setattr(threading.Thread, "start", fail_start)
        for _ in range(MAX_ACTIVE_REQUESTS + 1):
            saved = request(model)
            assert executor.start(store, saved["id"])["error_code"] == "dispatch_failed"
            assert idle(executor)
            lease = _RequestLock(store, saved["id"])
            lease.release()
    adapter.release.set()
    saved = request(model)
    executor.start(store, saved["id"])
    eventually(lambda: idle(executor))
    assert store.requests.get(saved["id"])["status"] == "completed"


def test_prepared_stream_only_sender_is_supported_without_a_send_method(model, executors):
    store, _ = model
    saved = request(model)
    class StreamOnly(StreamingAdapter):
        send = None
    prepared = StreamOnly()
    class Factory:
        release = prepared.release
        def prepare(self, frozen_input):
            assert frozen_input == store.requests.input(saved["id"])
            return prepared
    executor = executors(Factory())
    executor.start(store, saved["id"])
    assert prepared.emitted.wait(5)
    assert executor.progress(store, saved["id"])["progress"]["text"] == "partial"
    prepared.release.set()
    eventually(lambda: idle(executor))
    assert store.requests.get(saved["id"])["status"] == "completed"


def test_shutdown_preserves_complete_response_already_accepted_for_atomic_save(model, executors, monkeypatch):
    from suan.project.requests import Requests
    store, _ = model
    saved = request(model)
    adapter = StreamingAdapter()
    executor = executors(adapter)
    executor.start(store, saved["id"])
    assert adapter.emitted.wait(5)
    entered, release = threading.Event(), threading.Event()
    original = Requests._complete
    def pending_commit(self, request_id, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(self, request_id, **kwargs)
    monkeypatch.setattr(Requests, "_complete", pending_commit)
    adapter.release.set()
    try:
        assert entered.wait(5)
        assert store.requests.get(saved["id"])["status"] == "running"
        executor.shutdown(wait=False)
        assert executor._closing.is_set()
        # Streaming acceptance ended before the response entered atomic save.
        adapter.on_text("too late")
    finally:
        release.set()
    eventually(lambda: idle(executor))
    result = store.requests.get(saved["id"])
    assert result["status"] == "completed"
    assert store.discussion.get(result["assistant_message_id"])["text"] == "partial"
    assert executor.progress(store, saved["id"])["progress"] is None


def test_uncertain_owner_observation_hides_stream_without_discarding_valid_completion(model, executors):
    store, _ = model
    saved = request(model)
    adapter = StreamingAdapter()
    executor = executors(adapter)
    executor.start(store, saved["id"])
    assert adapter.emitted.wait(5)
    uncertain = store.requests._settle(saved["id"], executor_id=executor.executor_id,
                                       status="uncertain", code="transport_uncertain")
    assert not uncertain["cancel_requested"]
    assert executor.progress(store, saved["id"]) == {"request": uncertain, "progress": None}
    adapter.release.set()
    eventually(lambda: idle(executor))
    assert store.requests.get(saved["id"])["status"] == "completed"
