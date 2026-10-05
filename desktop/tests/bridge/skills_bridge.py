"""Test-only real bridge with a controlled skill catalog; production never imports it.

    skills_bridge.py legacy [bridge arguments]            the bridge predates skills.list/get
    skills_bridge.py catalog DIR [bridge arguments]       built-in skills plus the definitions in DIR
"""

import sys
from pathlib import Path

from suan.desktop_bridge import server
from suan.desktop_bridge.__main__ import main

mode = sys.argv.pop(1)
if mode == "legacy":
    original_init = server.Bridge.__init__

    def legacy_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        del self.methods["skills.list"]
        del self.methods["skills.get"]

    server.Bridge.__init__ = legacy_init
elif mode == "catalog":
    from suan.skills import catalog

    fixtures = Path(sys.argv.pop(1))
    original_load = catalog.load_catalog

    def load_with_fixtures(registry=None, *, directories=None):
        return original_load(registry, directories=[("builtin", catalog._builtin_root()), ("fixture", fixtures)])

    catalog.load_catalog = load_with_fixtures
else:
    raise SystemExit(f"unknown mode {mode!r}")

main()
