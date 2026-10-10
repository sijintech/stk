"""Simulation engines as templates (E0, docs/design/multiscale-engines.md): engine packages register through the
``stk.engines`` entry points, built-in identities are kept, broken plugins are reported, and editors learn which
templates run on a Runtime."""
import pytest

from suan.project import ProjectStore
from suan.workflows import templates


class FakeEngine:
    id = "fake-engine/1"
    name = "Fake engine"
    table_id = None
    remote = True
    field_ids = ()

    def describe(self, model, record_id, connection, options):
        return {"record_id": record_id, "label": "fake", "values": {}}

    def describe_values(self, model, record_id, connection, options):
        return {}

    def prepare(self, stk, project, record_id, connection, options, revision, identity=None):
        raise NotImplementedError

    def collect(self, stk, project, run_id):
        raise NotImplementedError

    @staticmethod
    def results_prefix(run_id):
        return f"results/fake/{run_id}/"

    @staticmethod
    def final_state(names):
        return list(names)


class Incomplete:
    id = "incomplete/1"
    name = "Incomplete"
    remote = True


class Impostor(FakeEngine):
    id = "muferro/1"


class Point:
    def __init__(self, name, value):
        self.name, self.value = name, value

    def load(self):
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


@pytest.fixture
def plugins(monkeypatch):
    """Entry points as an installed engine package would declare them; the registry is restored afterwards."""
    import importlib.metadata
    points = [Point("fake", FakeEngine), Point("incomplete", Incomplete), Point("impostor", Impostor()),
              Point("broken", ImportError("No module named fake_engine"))]
    monkeypatch.setattr(importlib.metadata, "entry_points",
                        lambda group=None: points if group == templates.ENTRY_POINT_GROUP else [])
    monkeypatch.setattr(templates, "TEMPLATES", dict(templates.BUILTIN_TEMPLATES))
    monkeypatch.setattr(templates, "LOCAL_TEMPLATES", dict(templates.LOCAL_TEMPLATES))
    monkeypatch.setattr(templates, "_loaded", False)
    monkeypatch.setattr(templates, "_problems", [])
    return points


def test_engine_packages_register_templates_and_problems_are_reported(plugins):
    registered = templates.workflow_templates()
    assert isinstance(registered["fake-engine/1"], FakeEngine)
    assert type(registered["muferro/1"]).__name__ == "MuFerroTemplate"  # a plugin cannot replace a built-in engine
    assert "incomplete/1" not in registered
    problems = {item["entry_point"]: item["error"] for item in templates.engine_diagnostics()}
    assert "missing" in problems["incomplete"] and "describe_values" in problems["incomplete"]
    assert "already registered" in problems["impostor"] and "No module named" in problems["broken"]
    assert templates.template("fake-engine/1").id == "fake-engine/1"  # batch-capable, as a remote template
    assert "fake-engine/1" in templates.remote_templates()
    templates.workflow_templates()
    assert len(templates.engine_diagnostics()) == 3  # loaded once


def test_editors_learn_which_templates_run_on_a_runtime(plugins, tmp_path):
    store = ProjectStore.create(tmp_path / "project", "Engines")
    listed = {item["id"]: item for item in store.workflows.choices()["templates"]}
    assert listed["muferro/1"]["remote"] and not listed["muferro/1"]["local"]
    assert listed["demo-synthetic/1"]["local"] and not listed["demo-synthetic/1"]["remote"]
    assert listed["fake-engine/1"] == {"id": "fake-engine/1", "name": "Fake engine", "table_id": None,
                                       "remote": True, "local": False}


def test_the_muferro_engine_provides_the_whole_remote_protocol():
    engine = templates.BUILTIN_TEMPLATES["muferro/1"]
    assert all(hasattr(engine, name) for name in templates._REMOTE_PROTOCOL)
    assert engine.results_prefix("r1") == "results/muferro/r1/" and len(engine.field_ids) == 7
