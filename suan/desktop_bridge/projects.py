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

from .protocol import BridgeError
from .recent_projects import RecentProjects


class ProjectSessions:
    def __init__(self, state_dir=None):
        self._recent = RecentProjects(state_dir)
        self._lock = threading.RLock()
        self._stores = {}
        self._closed = False

    @contextmanager
    def _operation(self):
        with self._lock:
            if self._closed:
                raise BridgeError("shutting_down", "Project sessions are closed")
            try:
                yield
            except RevisionConflict as exc:
                raise BridgeError("conflict", str(exc)) from None
            except UnsupportedProjectFormat as exc:
                raise BridgeError("unsupported", str(exc)) from None
            except FileExistsError:
                raise BridgeError("conflict", "A project database already exists at this location; open it instead") from None
            except FileNotFoundError:
                raise BridgeError("not_found", "Project database not found") from None
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
            return {"closed": self._stores.pop(params["handle"], None) is not None}

    def snapshot(self, params):
        with self._operation():
            return {"snapshot": self._get(params["handle"]).snapshot()}

    def apply(self, params):
        with self._operation():
            store = self._get(params["handle"])
            return store.apply(params["commands"], expected_revision=params["expected_revision"])

    def history(self, params):
        with self._operation():
            return {"history": self._get(params["handle"]).history()}

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
        if self._lock.acquire(blocking=False):
            try:
                self._stores.clear()
            finally:
                self._lock.release()
