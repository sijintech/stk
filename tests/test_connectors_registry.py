"""Connector registry: built-ins, entry points, priority, allowlist and diagnostics."""
import pytest

from suan.connectors import registry as registry_module
from suan.connectors.api import Connector, ConnectorError, InputConnector, Match
from suan.connectors.mupro import MuFerroConnector
from suan.connectors.registry import ConnectorRegistry, allowed, default_registry


class Private:
    """A stand-in for the private stk-mupro connector (same id, priority 10)."""

    id = "mupro.muferro"
    version = "9.0.0"
    api = 1

    def info(self):
        return {"id": self.id, "version": self.version, "api": 1, "priority": 10}

    def sniff(self, run):
        return Match(self.id, 0.99, "mupro.muferro", "private")


class Other:
    id = "lab.code"
    version = "1.0"
    api = 1

    def info(self):
        return {"id": self.id, "priority": 0}

    def sniff(self, run):
        return Match(self.id, 0.5, None, "other")


class FutureApi(Other):
    id = "lab.future"
    api = 2


class FakePoint:
    def __init__(self, name, value, obj=None, error=None):
        self.name, self.value, self._obj, self._error = name, value, obj, error
        self.dist = type("Dist", (), {"name": "lab-plugins"})()

    def load(self):
        if self._error:
            raise self._error
        return self._obj


def test_builtins_are_registered_without_entry_points():
    registry = ConnectorRegistry(entry_points=False)
    assert registry.ids() == ["mupro.muferro", "stk.numpy", "stk.vtk"]
    assert isinstance(registry.get("mupro.muferro"), MuFerroConnector)
    assert all(isinstance(c, Connector) for c in registry.connectors())
    assert isinstance(registry.inputs("mupro.muferro"), InputConnector)
    assert {"id": "mupro.muferro", "version": "0.1.0"} in registry.enabled()
    with pytest.raises(ConnectorError) as error:
        registry.get("nope")
    assert error.value.code == "unsupported"


def test_priority_allowlist_and_diagnostics():
    registry = ConnectorRegistry(entry_points=False, allow=["stk.*", "mupro.*"])
    registry.register(Private)
    assert isinstance(registry.get("mupro.muferro"), Private)
    candidates = [d for d in registry.diagnostics()["connectors"] if d["id"] == "mupro.muferro"]
    assert [(d["source"], d["priority"], d["active"]) for d in candidates] == [("builtin", 0, False),
                                                                                ("manual", 10, True)]
    registry.register(Other)
    with pytest.raises(ConnectorError) as error:
        registry.get("lab.code")
    assert error.value.code == "not_allowed"
    assert "lab.code" not in [c.id for c in registry.connectors()]
    assert allowed("stk.vtk", ["stk.*"]) and not allowed("lab.code", ["stk.*"]) and allowed("x", None)
    assert not allowed("stk.vtk", [])
    with pytest.raises(ConnectorError) as error:
        registry.register(FutureApi)
    assert error.value.code == "unsupported"
    # Registering the same class again (built-in and entry point) is not a duplicate candidate.
    registry.register(MuFerroConnector)
    assert len([d for d in registry.diagnostics()["connectors"] if d["id"] == "mupro.muferro"]) == 2


def test_entry_points_and_broken_plugins(monkeypatch):
    points = {"stk.connectors": [FakePoint("lab.code", "lab:Other", Other),
                                 FakePoint("mupro.muferro", "suan.connectors.mupro:MuFerroConnector", MuFerroConnector),
                                 FakePoint("broken", "lab:Broken", error=ImportError("no module lab"))],
              "stk.inputs": []}
    monkeypatch.setattr(registry_module, "_entry_points", lambda group: points.get(group, []))
    registry = ConnectorRegistry()
    assert registry.ids() == ["lab.code", "mupro.muferro", "stk.numpy", "stk.vtk"]
    diagnostics = registry.diagnostics()
    assert [d["source"] for d in diagnostics["connectors"] if d["id"] == "lab.code"] == ["entry_point:lab-plugins"]
    assert len([d for d in diagnostics["connectors"] if d["id"] == "mupro.muferro"]) == 1
    error = diagnostics["errors"][0]
    assert error["reference"] == "lab:Broken" and "no module lab" in error["error"]


def test_numpy_free_parts(tmp_path):
    """The hub and the Windows client import catalogs, registries and the light half without NumPy."""
    import subprocess
    import sys
    from mupro_fake import write_case
    write_case(tmp_path / "case", grid=(4, 3, 2))
    code = (
        "import sys; sys.modules['numpy'] = None\n"
        "from suan.connectors.registry import ConnectorRegistry\n"
        "from suan.connectors.files import LocalFiles\n"
        "from suan.graph.registry import Registry\n"
        "from suan.graph.nodes import sources\n"
        "from suan.analysis import palettes\n"
        "from suan.analysis.orientation import cubic26\n"
        "from suan.data.manifest import validate_result\n"
        "registry = ConnectorRegistry(entry_points=False)\n"
        "inputs = registry.inputs('mupro.muferro')\n"
        "case = inputs.read_case(LocalFiles(sys.argv[1]))\n"
        "spec = inputs.task_spec(case, {'ranks': 2}, workspace_id='w' * 32)\n"
        "assert len(Registry([sources])) == 4 and len(cubic26('stk-legacy')) == 26\n"
        "assert palettes.to_hex(palettes.cubic26_color((1, 0, 0))) == '#ff0000'\n"
        "print(case['app'], spec['resources']['ranks'], registry.get('mupro.muferro').sniff(LocalFiles(sys.argv[1])))\n"
    )
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path / "case")], capture_output=True, text=True,
                            timeout=120)
    assert result.returncode == 0, result.stderr[-3000:]
    assert result.stdout.startswith("mupro.muferro 2 Match(")


def test_sniff_orders_by_confidence(tmp_path):
    from mupro_fake import write_case, write_outputs
    from suan.connectors.files import LocalFiles
    write_case(tmp_path)
    write_outputs(tmp_path)
    registry = ConnectorRegistry(entry_points=False)
    registry.register(Other)
    matches = registry.sniff(LocalFiles(tmp_path))
    assert [c.id for c, _ in matches] == ["mupro.muferro", "lab.code", "stk.numpy"]
    assert matches[0][1].confidence == 0.95
    connector, match = registry.best(LocalFiles(tmp_path))
    assert connector.id == "mupro.muferro" and match.app == "mupro.muferro"
    assert default_registry() is default_registry() and default_registry(allow=["stk.*"]) is not default_registry()
