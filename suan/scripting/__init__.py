"""Python operation facade injected as ``stk`` in the desktop's isolated console.

The facade uses the same project commands and revision checks as the native table editor.
It holds IDs, never C++ window pointers. See ``docs/scripting.md`` for the supported coverage.
"""
from pathlib import Path

from .runtime import Connections, Runtime, Transfers
from .viewer import Viewer
from .graph import Graph


class ScriptError(RuntimeError):
    """An operation failed; ``code`` and ``data`` retain its structured bridge error."""

    def __init__(self, error):
        super().__init__(f"{error['code']}: {error['message']}")
        self.code = error["code"]
        self.data = error.get("data")
        self.retryable = error.get("retryable", False)


class Project:
    def __init__(self, call, handle):
        self._call = call
        self.handle = handle

    def snapshot(self):
        return self._call("project.snapshot", {"handle": self.handle})["snapshot"]

    def apply(self, commands, *, expected_revision):
        """One atomic edit, with an explicit base revision; never retried automatically."""
        return self._call("project.apply", {"handle": self.handle, "commands": commands,
                                            "expected_revision": expected_revision})

    def preview(self, commands, *, expected_revision):
        """Evaluate a hypothetical edit without saving; apply its normalized commands explicitly."""
        return self._call("project.preview", {"handle": self.handle, "commands": commands,
                                              "expected_revision": expected_revision})

    def review(self, commands, *, expected_revision):
        """Ask the visible desktop to preview this edit for explicit user application.

        Returns acceptance, not preview completion or a saved edit. The desktop must already
        show this project at the supplied revision and have no pending review draft.
        """
        return self._call("ui.project.review", {"handle": self.handle, "commands": commands,
                                               "expected_revision": expected_revision})

    def history(self):
        return self._call("project.history", {"handle": self.handle})["history"]

    def backup(self):
        """Consistent database backup; does not include external assets or execute code."""
        return self._call("project.backup", {"handle": self.handle})

    def upgrade(self, *, expected_revision):
        """Explicit format upgrade after creating a verified pre-migration database backup."""
        return self._call("project.upgrade", {"handle": self.handle, "expected_revision": expected_revision})

    def close(self):
        return self._call("project.close", {"handle": self.handle})["closed"]

    def undo(self, *, expected_revision):
        """Undo the latest active edit batch as a new revision; not an external side-effect rollback."""
        return self._call("project.undo", {"handle": self.handle, "expected_revision": expected_revision})

    def redo(self, *, expected_revision):
        """Reapply the next undone batch; new edits discard the redo stack."""
        return self._call("project.redo", {"handle": self.handle, "expected_revision": expected_revision})

    @property
    def csv(self):
        return ProjectCSV(self._call, self.handle)

    @property
    def files(self):
        return ProjectFiles(self._call, self.handle)

    @property
    def runs(self):
        return ProjectRuns(self._call, self.handle)

    @property
    def snapshots(self):
        return ProjectSnapshots(self._call, self.handle)


class ProjectCSV:
    def __init__(self, call, handle):
        self._call, self.handle = call, handle

    def import_file(self, source, *, name, expected_revision, types=None, units=None, delimiter=","):
        params = {"handle": self.handle, "source": str(Path(source).expanduser().absolute()),
                  "name": name, "expected_revision": expected_revision, "delimiter": delimiter}
        if types is not None:
            params["types"] = types
        if units is not None:
            params["units"] = units
        return self._call("project.csv.import", params)

    def export_file(self, table_id, destination, *, expected_revision, delimiter=","):
        return self._call("project.csv.export", {"handle": self.handle, "table_id": table_id,
            "destination": str(Path(destination).expanduser().absolute()),
            "expected_revision": expected_revision, "delimiter": delimiter})


class ProjectRuns:
    def __init__(self, call, handle):
        self._call, self.handle = call, handle

    def prepare(self, entries, *, connection, expected_revision, node=None):
        """Freeze explicit per-row TaskSpecs; this does not upload files or start execution."""
        params = {"handle": self.handle, "entries": entries, "connection": connection,
                  "expected_revision": expected_revision}
        if node is not None:
            params["node"] = node
        return self._call("project.runs.prepare", params)

    def list(self, *, offset=0, limit=100):
        return self._call("project.runs.list", {"handle": self.handle, "offset": offset, "limit": limit})

    def get(self, run_id):
        return self._call("project.runs.get", {"handle": self.handle, "run_id": run_id})["run"]

    def submit(self, run_id, *, allow_stale=False):
        """Explicit submission/recovery; repeat the same run ID after a lost response."""
        return self._call("project.runs.submit", {"handle": self.handle, "run_id": run_id,
                                                "allow_stale": allow_stale})["run"]

    def refresh(self, run_id):
        return self._call("project.runs.refresh", {"handle": self.handle, "run_id": run_id})["run"]

    def cancel(self, run_id):
        return self._call("project.runs.cancel", {"handle": self.handle, "run_id": run_id})["run"]


class ProjectSnapshots:
    def __init__(self, call, handle):
        self._call, self.handle = call, handle

    def list(self):
        return self._call("project.snapshots.list", {"handle": self.handle})

    def capture(self, record_ids, *, expected_revision, max_bytes=256 * 1024 * 1024):
        """Explicitly copy selected input bytes; immutable manifests are outside table undo."""
        return self._call("project.snapshots.capture", {"handle": self.handle, "record_ids": record_ids,
                         "expected_revision": expected_revision, "max_bytes": max_bytes})

    def get(self, snapshot_id):
        return self._call("project.snapshots.get", {"handle": self.handle, "snapshot_id": snapshot_id})["snapshot"]

    def verify(self, snapshot_id):
        return self._call("project.snapshots.verify", {"handle": self.handle, "snapshot_id": snapshot_id})

    def resolve(self, snapshot_id, record_id):
        """Verify frozen bytes and return their path, irrespective of later source/index edits."""
        return self._call("project.snapshots.resolve", {"handle": self.handle, "snapshot_id": snapshot_id,
                                                       "record_id": record_id})


class ProjectFiles:
    def __init__(self, call, handle):
        self._call, self.handle = call, handle

    def list(self):
        return self._call("project.files.list", {"handle": self.handle})

    def index(self, paths, *, expected_revision):
        if isinstance(paths, (str, bytes)):
            raise TypeError("paths must be a sequence of paths, not a single string")
        return self._call("project.files.index", {"handle": self.handle, "paths": [str(path) for path in paths],
                                                   "expected_revision": expected_revision})

    def refresh(self, record_ids, *, expected_revision):
        return self._call("project.files.refresh", {"handle": self.handle, "record_ids": record_ids,
                                                     "expected_revision": expected_revision})

    def resolve(self, record_id, *, expected_revision):
        """Check and return the current local path; never launches an external application."""
        return self._call("project.files.resolve", {"handle": self.handle, "record_id": record_id,
                                                     "expected_revision": expected_revision})


class Projects:
    def __init__(self, call):
        self._call = call

    def open(self, directory, *, expected_id=None):
        params = {"directory": str(Path(directory).expanduser().resolve())}
        if expected_id is not None:
            params["expected_id"] = expected_id
        info = self._call("project.open", params)["project"]
        return Project(self._call, info["handle"])

    def create(self, directory, name):
        info = self._call("project.create", {"directory": str(Path(directory).resolve()), "name": name})["project"]
        return Project(self._call, info["handle"])

    def list(self):
        return self._call("project.list", {})["projects"]

    def recent(self):
        """Return saved metadata and a possible persistence warning; does not open projects."""
        return self._call("project.recent", {})

    def forget(self, directory):
        """Remove only a history entry; never closes or deletes the project."""
        return self._call("project.forget", {"directory": str(Path(directory).expanduser().absolute())})["removed"]


class Desktop:
    def __init__(self, call):
        self._call = call

    def layout(self):
        return self._call("ui.layout.get", {})["layout"]

    def apply_layout(self, layout):
        """Validate and replace the desktop layout on its UI thread; invalid input keeps it intact."""
        return self._call("ui.layout.apply", {"layout": layout})

    def editors(self):
        return self._call("ui.editors.list", {})["editors"]

    def current_project(self):
        return self._call("ui.project.current", {})["project"]

    def open_project(self, directory):
        return self._call("ui.project.open", {"directory": str(Path(directory).resolve())})["project"]

    def close_project(self):
        return self._call("ui.project.close", {})


class API:
    def __init__(self, call):
        self._call = call
        self._project_handle = None
        self.projects = Projects(call)
        self.ui = Desktop(call)
        self.connections = Connections(call)
        self.transfers = Transfers(call)
        self.viewer = Viewer(call)
        self.graph = Graph(call)

    def runtime(self, connection, *, node=None):
        """Use a saved Runtime profile, optionally routed through a Hub execution node."""
        return Runtime(self._call, connection, node=node)

    @property
    def batches(self):
        """Save explicit case selections and prepare/submit/refresh/collect them independently."""
        from suan.workflows.batches import Batches
        return Batches(self)

    @property
    def muferro(self):
        """Import native cases, prepare immutable plans, collect results and open their 3D view."""
        from suan.workflows.muferro import MuFerro
        return MuFerro(self)

    @property
    def project(self):
        """Project selected when this execution started; close/switch never retargets a held handle."""
        if self._project_handle is None:
            raise ScriptError({"code": "not_found", "message": "No project was selected for this execution"})
        return Project(self._call, self._project_handle)

    def call(self, operation, **params):
        """Invoke an operation in ``operations()`` with named parameters."""
        return self._call(operation, params)

    def operations(self):
        return self._call("operations", {})

    def help(self):
        """Print the currently supported operation names and parameter schemas."""
        import json
        print(json.dumps(self.operations(), ensure_ascii=False, indent=2))


__all__ = ["API", "Connections", "Desktop", "Graph", "Project", "ProjectCSV", "ProjectFiles", "ProjectSnapshots", "ProjectRuns", "Projects", "Runtime", "ScriptError", "Transfers", "Viewer"]
