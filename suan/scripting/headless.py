"""``stk`` without the desktop: the console facade in a terminal, a script or Jupyter.

    from suan.scripting.headless import connect
    stk = connect()
    p = stk.use(stk.projects.create("~/STK Projects/demo", "Demo"))   # now also stk.project
    print(p.snapshot()["project"]["revision"])
    stk.close()

``python -m suan.scripting.headless [PROJECT_DIR]`` opens an interactive console with ``stk``
defined (and the project in use when a directory is given).

A private STK Python service runs inside this process, with no window. Operations are exactly
the desktop console's (projects, tables, sweeps, files, snapshots, runs, batches, analyses,
graphs, skills, Runtime connections and transfers), checked against the same protocol schema.
Desktop-only operations (``stk.ui``, ``stk.viewer``, ``Project.review/select/selection``) fail
with ``ScriptError`` code ``unavailable``. The service keeps its own state folder (default
``~/.stk/headless``) so it can run while the desktop is open; saved Runtime profiles are shared
with the desktop and ``suan connect``. Closing never cancels submitted Runtime tasks.
"""
import atexit
from pathlib import Path
import threading

from . import API, Project, ScriptError

__all__ = ["HeadlessAPI", "connect", "default_state_dir"]


def default_state_dir():
    return Path.home() / ".stk" / "headless"


class _Discard:
    """Events (project changes, transfer progress) have no subscriber without a desktop."""

    def write(self, data):
        return len(data)

    def flush(self):
        pass


class HeadlessAPI(API):
    def __init__(self, bridge):
        self._bridge = bridge
        self._cancelled = threading.Event()
        super().__init__(self._dispatch)
        atexit.register(self.close)

    def _dispatch(self, operation, params):
        from suan.desktop_bridge.protocol import BridgeError
        if self._bridge is None:
            raise ScriptError({"code": "shutting_down", "message": "This headless STK session is closed"})
        try:
            return self._bridge.script_call(operation, params, self._cancelled)
        except BridgeError as exc:
            raise ScriptError(exc.to_json()) from None

    def use(self, project):
        """Make ``project`` (from ``stk.projects.open/create``) the one ``stk.project`` and workflows use."""
        if not isinstance(project, Project):
            raise TypeError("use() takes a Project from stk.projects.open() or stk.projects.create()")
        self._project_handle = project.handle
        return project

    def close(self):
        """Stop the private service (finishing requests; Runtime tasks keep running). Idempotent."""
        bridge, self._bridge = self._bridge, None
        if bridge is not None:
            bridge.shutdown()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def connect(state_dir=None, *, project=None):
    """Start a headless session; with ``project`` (a directory) open it and put it in use."""
    from suan.desktop_bridge.protocol import BridgeError
    from suan.desktop_bridge.server import Bridge
    state = Path(state_dir).expanduser() if state_dir else default_state_dir()
    try:
        bridge = Bridge(state, None, writer=_Discard())
    except BridgeError as exc:
        if exc.code == "busy":
            raise ScriptError({"code": "busy", "message": f"Another STK session uses {state}; pass connect(state_dir=...) "
                               "with a different folder or close that session"}) from None
        raise ScriptError(exc.to_json()) from None
    api = HeadlessAPI(bridge)
    if project is not None:
        api.use(api.projects.open(project))
    return api


def _main(argv=None):
    import argparse
    import code
    parser = argparse.ArgumentParser(prog="python -m suan.scripting.headless",
                                     description="Interactive STK console without the desktop (stk is predefined).")
    parser.add_argument("project", nargs="?", help="Project directory to open and use as stk.project")
    parser.add_argument("--state-dir", help=f"Private service state folder (default {default_state_dir()})")
    args = parser.parse_args(argv)
    with connect(args.state_dir, project=args.project) as stk:
        banner = ("STK headless console: `stk` is ready" +
                  (f"; stk.project is {args.project}" if args.project else "; stk.use(stk.projects.open(dir)) selects a project") +
                  ". stk.help() lists operations; Ctrl+D exits.")
        code.interact(banner=banner, local={"stk": stk}, exitmsg="")


if __name__ == "__main__":
    _main()
