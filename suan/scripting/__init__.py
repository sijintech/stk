"""Python operation facade injected as ``stk`` in the desktop's isolated console.

The facade uses the same project commands and revision checks as the native table editor.
It holds IDs, never C++ window pointers. See ``docs/scripting.md`` for the supported coverage.
"""
from pathlib import Path


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
    def files(self):
        return ProjectFiles(self._call, self.handle)


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

    def open(self, directory):
        info = self._call("project.open", {"directory": str(Path(directory).resolve())})["project"]
        return Project(self._call, info["handle"])

    def create(self, directory, name):
        info = self._call("project.create", {"directory": str(Path(directory).resolve()), "name": name})["project"]
        return Project(self._call, info["handle"])

    def list(self):
        return self._call("project.list", {})["projects"]


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


__all__ = ["API", "Desktop", "Project", "ProjectFiles", "Projects", "ScriptError"]
