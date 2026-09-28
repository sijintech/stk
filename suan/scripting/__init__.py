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


__all__ = ["API", "Desktop", "Project", "Projects", "ScriptError"]
