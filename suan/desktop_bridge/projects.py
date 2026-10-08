"""Local project sessions. Handles belong to one bridge lifetime, not to a file or Runtime task.

The session lock serializes close/open/edit, so a close cannot acknowledge while an earlier
accepted edit still uses its handle. SQLite revisions arbitrate external CLI writers too.
"""

from contextlib import contextmanager
from pathlib import Path
import threading
from uuid import uuid4

from suan.project import ProjectError, ProjectStore, RevisionConflict
from suan.project.store import DATABASE_NAME, UnsupportedProjectFormat
from suan.project.analyses import AnalysisNotFound
from suan.project.analysis_runs import AnalysisRunNotFound
from suan.project.workflows import WorkflowNotFound
from suan.project.workflow_runs import WorkflowRunNotFound
from suan.project.aliyun import ALIYUN_ADAPTER, AliyunTokenPlanAdapter, TokenPlanCredentials, provider_info
from suan.project.request_executor import RequestBusy, RequestExecutor

from .protocol import BridgeError
from .attention import AttentionViews
from .recent_projects import RecentProjects


class ProjectSessions:
    def __init__(self, state_dir=None, *, analysis_executor=None, workflow_executor=None):
        self._recent = RecentProjects(state_dir)
        self._viewed = AttentionViews(state_dir)
        self._lock = threading.RLock()
        self._stores = {}
        self._closed = False
        self._credentials = TokenPlanCredentials(state_dir)
        self._executor = RequestExecutor({ALIYUN_ADAPTER: AliyunTokenPlanAdapter(self._credentials)})
        self._analysis_executor = analysis_executor
        self._workflow_executor = workflow_executor

    @contextmanager
    def _operation(self):
        with self._lock:
            if self._closed:
                raise BridgeError("shutting_down", "Project sessions are closed")
            with self._errors():
                yield

    @contextmanager
    def _errors(self):
        try:
            yield
        except RevisionConflict as exc:
            raise BridgeError("conflict", str(exc)) from None
        except (AnalysisNotFound, AnalysisRunNotFound, WorkflowNotFound, WorkflowRunNotFound) as exc:
            raise BridgeError("not_found", str(exc)) from None
        except RequestBusy:
            raise BridgeError("busy", "A live executor owns this request or the local executor has reached its 8-request limit") from None
        except UnsupportedProjectFormat as exc:
            raise BridgeError("unsupported", str(exc)) from None
        except FileExistsError:
            raise BridgeError("conflict", "A project database already exists at this location; open it instead") from None
        except FileNotFoundError:
            raise BridgeError("not_found", "Project database or archived file not found") from None
        except PermissionError:
            raise BridgeError("unavailable", "Project location is not accessible", retryable=False) from None
        except (ProjectError, OSError) as exc:
            raise BridgeError("invalid_params", str(exc)) from None

    @staticmethod
    def _directory(value):
        path = Path(value)
        if not path.is_absolute():
            raise BridgeError("invalid_params", "Project directory must be an absolute path")
        return path.resolve()

    def _get(self, handle):
        if handle not in self._stores:
            raise BridgeError("not_found", "Project handle is closed or belongs to an earlier bridge session")
        return self._stores[handle]

    @staticmethod
    def _info(handle, store):
        return {"handle": handle, "directory": str(store.directory), **store.info()}

    def _register(self, store):
        for handle, existing in self._stores.items():
            if existing.path == store.path:
                result = self._info(handle, existing)
                self._recent.remember(result)
                return result
        handle = uuid4().hex
        result = self._info(handle, store)
        self._stores[handle] = store
        self._recent.remember(result)
        return result

    def create(self, params):
        with self._operation():
            store = ProjectStore.create(self._directory(params["directory"]), params["name"])
            return {"project": self._register(store)}

    def open(self, params):
        with self._operation():
            directory = self._directory(params["directory"])
            if not (directory / DATABASE_NAME).is_file():
                raise FileNotFoundError
            store = ProjectStore(directory)
            if params.get("expected_id") is not None and store.info()["id"] != params["expected_id"]:
                raise BridgeError("conflict", "The project at this location has been replaced; open its directory explicitly")
            return {"project": self._register(store)}

    def recent(self, params):
        with self._operation():
            return self._recent.list()

    def forget(self, params):
        with self._operation():
            # Do not resolve a historical path again: a removed symlink must still be forgettable.
            directory = Path(params["directory"])
            if not directory.is_absolute():
                raise BridgeError("invalid_params", "Project directory must be an absolute path")
            return self._recent.forget(str(directory))

    def list(self, params):
        with self._operation():
            return {"projects": [self._info(handle, store) for handle, store in self._stores.items()]}

    def close(self, params):
        with self._operation():
            store = self._stores.pop(params["handle"], None)
            if store is not None and self._workflow_executor is not None:
                self._workflow_executor.close_project(store)
            if store is not None and self._analysis_executor is not None:
                self._analysis_executor.close_project(store)
            return {"closed": store is not None}

    def snapshot(self, params):
        with self._operation():
            return {"snapshot": self._get(params["handle"]).snapshot()}

    def apply(self, params):
        with self._operation():
            store = self._get(params["handle"])
            return store.apply(params["commands"], expected_revision=params["expected_revision"])

    def credentials(self, action, params):
        """Set or forget the Token Plan key; replies report only where a key comes from."""
        with self._errors():
            if action == "set":
                self._credentials.set(params["key"], remember=params.get("remember", False))
            else:
                self._credentials.clear()
            return {"provider": provider_info(self._credentials)}

    def sweep_plan(self, params):
        from suan.project.sweep import plan_sweep
        with self._operation():
            snapshot = self._get(params["handle"]).snapshot()
            plan = plan_sweep(snapshot, params["table_id"], params["axes"], params.get("base_record_id"),
                              params.get("mode", "product"))
            return {"plan": plan, "revision": snapshot["project"]["revision"]}

    def preview(self, params):
        with self._operation():
            return self._get(params["handle"]).preview(params["commands"], expected_revision=params["expected_revision"])

    def drafts(self, action, params):
        with self._operation():
            drafts = self._get(params["handle"]).drafts
            if action == "save":
                return {"draft": drafts.save(params["commands"], expected_revision=params["expected_revision"],
                                             title=params["title"], draft_id=params["draft_id"])}
            if action == "list":
                return drafts.list(offset=params.get("offset", 0), limit=params.get("limit", 100))
            if action == "apply":
                return drafts.apply(params["draft_id"], expected_revision=params["expected_revision"])
            if action == "discard":
                return {"draft": drafts.discard(params["draft_id"])}
            return {"draft": drafts.get(params["draft_id"])}

    def contexts(self, action, params):
        with self._operation():
            contexts = self._get(params["handle"]).contexts
            if action == "capture":
                return {"context": contexts.capture(params["table_id"], params["record_ids"], params["field_ids"],
                    expected_revision=params["expected_revision"], title=params["title"], context_id=params["context_id"])}
            if action == "list":
                return contexts.list(offset=params.get("offset", 0), limit=params.get("limit", 100))
            return {"context": contexts.get(params["context_id"])}

    def discussion(self, action, params):
        with self._operation():
            discussion = self._get(params["handle"]).discussion
            if action == "add":
                return {"message": discussion.add(params["text"], message_id=params["message_id"],
                    context_id=params["context_id"], role=params.get("role", "user"))}
            if action == "get":
                return {"message": discussion.get(params["message_id"])}
            if action == "link_draft":
                return {"proposal": discussion.link_draft(params["message_id"], params["draft_id"],
                                                           proposal_id=params["proposal_id"])}
            if action == "proposals":
                return discussion.proposals(offset=params.get("offset", 0), limit=params.get("limit", 100),
                                            draft_id=params.get("draft_id"))
            return discussion.list(offset=params.get("offset", 0), limit=params.get("limit", 100))

    def history(self, params):
        with self._operation():
            return {"history": self._get(params["handle"]).history()}

    def analyses(self, action, params):
        with self._operation():
            analyses = self._get(params["handle"]).analyses
            if action == "create":
                return analyses.create(params["name"], params["document"], analysis_id=params["analysis_id"],
                                       expected_revision=params["expected_revision"])
            if action == "update":
                return analyses.update(params["analysis_id"], params["name"], params["document"],
                                       expected_revision=params["expected_revision"])
            if action == "list":
                return analyses.list(offset=params.get("offset", 0), limit=params.get("limit", 50))
            return analyses.get(params["analysis_id"])

    def workflows(self, action, params):
        with self._operation():
            workflows = self._get(params["handle"]).workflows
            if action == "create":
                return workflows.create(params["name"], params["document"], workflow_id=params["workflow_id"],
                                        expected_revision=params["expected_revision"])
            if action == "update":
                return workflows.update(params["workflow_id"], params["name"], params["document"],
                                        expected_revision=params["expected_revision"])
            if action == "list":
                return workflows.list(offset=params.get("offset", 0), limit=params.get("limit", 50))
            if action == "validate":
                return workflows.validate(params["document"])
            if action == "choices":
                return workflows.choices()
            return workflows.get(params["workflow_id"])

    def search(self, params):
        """Names and text of the project matching a query; reads only (UX package U3)."""
        from suan.project.search import search
        with self._operation():
            return search(self._get(params["handle"]), params["query"], limit=params.get("limit", 100))

    def attention(self, action, params):
        """The project's attention items with this person's viewed marks, or mark some as viewed."""
        from suan.project.attention import collect
        with self._operation():
            store = self._get(params["handle"])
            project_id = store._project_id
            if action == "viewed":
                return {"viewed": self._viewed.mark(project_id, list(dict.fromkeys(params["keys"])))}
            result = collect(store)
            viewed = self._viewed.viewed(project_id)
            for item in result["items"]:
                item["viewed"] = item["key"] in viewed
            counts = {"needs_you": sum(1 for i in result["items"] if i["group"] == "needs_you" and not i["viewed"]),
                      "running": sum(1 for i in result["items"] if i["group"] == "running"),
                      "unviewed_done": sum(1 for i in result["items"] if i["group"] == "done" and not i["viewed"])}
            return {**result, "counts": counts}

    def handles_of(self, store):
        """Open handles of this exact store (for announcing background project edits)."""
        with self._lock:
            return [handle for handle, candidate in self._stores.items() if candidate is store]

    def workflow_runs(self, action, params):
        with self._operation():
            store = self._get(params["handle"])
            runs = store.workflow_runs
            if action == "prepare":
                return {"run": runs.prepare(params["workflow_id"], params["rows"], run_id=params["run_id"],
                                            expected_revision=params["expected_revision"],
                                            simulation=params.get("simulation"))}
            if action == "get":
                return {"run": runs.get(params["run_id"])}
            if action == "list":
                return runs.list(offset=params.get("offset", 0), limit=params.get("limit", 50),
                                 workflow_id=params.get("workflow_id"))
            if action == "stale":
                return runs.stale(params["run_id"])
            if self._workflow_executor is None:
                raise BridgeError("unsupported", "No local workflow executor is installed")
            if action == "recover":
                return {"run": self._workflow_executor.recover(store, params["run_id"], force=params.get("force", False))}
            return {"run": getattr(self._workflow_executor, action)(store, params["run_id"])}

    def analysis_runs(self, action, params):
        with self._operation():
            store = self._get(params["handle"])
            runs = store.analysis_runs
            if action == "prepare":
                return {"run": runs.prepare(params["analysis_id"], params["snapshot_id"], params["bindings"],
                    run_id=params["run_id"], expected_revision=params["expected_revision"],
                    parameter_overrides=params.get("parameter_overrides"))}
            if action == "get":
                return {"run": runs.get(params["run_id"])}
            if action == "list":
                return runs.list(offset=params.get("offset", 0), limit=params.get("limit", 50))
            if self._analysis_executor is None:
                raise BridgeError("unsupported", "No local analysis executor is installed")
            if action in {"start", "cancel", "recover"}:
                return {"run": getattr(self._analysis_executor, action)(store, params["run_id"])}
        # Reading a potentially large artifact must not block close or unrelated project edits.
        # Its original store remains pinned; a closed handle is never rebound to another project.
        with self._errors():
            return self._analysis_executor.result(store, params["run_id"])

    def requests(self, action, params):
        with self._operation():
            store = self._get(params["handle"])
            requests = store.requests
            if action == "provider":
                if store.info()["format_version"] < 8:
                    raise UnsupportedProjectFormat("Upgrade this project before using model requests")
                return {"provider": provider_info(self._credentials)}
            if action in {"start", "cancel", "recover"}:
                return {"request": getattr(self._executor, action)(store, params["request_id"])}
            if action == "progress":
                return self._executor.progress(store, params["request_id"])
            if action == "create":
                return {"request": requests.create(params["message_id"], request_id=params["request_id"],
                                                    configuration=params["configuration"],
                                                    prompt_version=params.get("prompt_version", "stk.text/1"))}
            if action == "propose_edits":
                return requests.propose_edits(params["request_id"], expected_revision=params["expected_revision"])
            if action == "edit_proposal":
                return requests.edit_proposal(params["request_id"])
            if action == "list":
                return requests.list(offset=params.get("offset", 0), limit=params.get("limit", 100))
            if action == "usage":
                return requests.usage()
            return {"request": requests.get(params["request_id"])}

    def backup(self, params):
        with self._operation():
            return self._get(params["handle"]).backup()

    def upgrade(self, params):
        with self._operation():
            return self._get(params["handle"]).upgrade(expected_revision=params["expected_revision"])

    def undo(self, params):
        with self._operation():
            return self._get(params["handle"]).undo(expected_revision=params["expected_revision"])

    def redo(self, params):
        with self._operation():
            return self._get(params["handle"]).redo(expected_revision=params["expected_revision"])

    def csv(self, action, params):
        with self._operation():
            exchange = self._get(params["handle"]).csv
            args = {key: value for key, value in params.items() if key != "handle"}
            try:
                return exchange.import_file(**args) if action == "import" else exchange.export_file(**args)
            except FileExistsError:
                raise BridgeError("conflict", "CSV destination already exists; choose a new file") from None
            except FileNotFoundError:
                raise BridgeError("not_found", "CSV source or destination directory does not exist") from None

    def files(self, action, params):
        with self._operation():
            index = self._get(params["handle"]).files
            if action == "list":
                return index.list()
            revision = params["expected_revision"]
            if action == "index":
                return index.index(params["paths"], expected_revision=revision)
            if action == "refresh":
                return index.refresh(params["record_ids"], expected_revision=revision)
            return index.resolve(params["record_id"], expected_revision=revision)

    def snapshots(self, action, params):
        with self._operation():
            snapshots = self._get(params["handle"]).snapshots
            if action == "list":
                return snapshots.list()
            if action == "capture":
                kwargs = {"expected_revision": params["expected_revision"]}
                if "max_bytes" in params:
                    kwargs["max_bytes"] = params["max_bytes"]
                return snapshots.capture(params["record_ids"], **kwargs)
            if action == "get":
                return {"snapshot": snapshots.get(params["snapshot_id"])}
            if action == "verify":
                return snapshots.verify(params["snapshot_id"])
            return snapshots.resolve(params["snapshot_id"], params["record_id"])

    @contextmanager
    def use(self, handle):
        """Keep a handle alive through an accepted service operation, including its observations."""
        with self._operation():
            yield self._get(handle)

    def shutdown(self):
        # The bridge already waited its grace period. Do not wait again on a database
        # lock or a slow filesystem; process exit rolls back any unfinished transaction.
        self._closed = True
        if self._workflow_executor is not None:
            self._workflow_executor.shutdown(wait=False)
        if self._analysis_executor is not None:
            self._analysis_executor.shutdown(wait=False)
        self._executor.shutdown(wait=False)
        if self._lock.acquire(blocking=False):
            try:
                self._stores.clear()
            finally:
                self._lock.release()
