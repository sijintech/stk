"""Versioned skill catalog (stk.skill/1): definitions, identity, availability, bounded reads and every entry point."""
from importlib.resources import files
import json
import os
from pathlib import Path
import subprocess
import sys

from click.testing import CliRunner
import pytest
import toml

from suan.graph.catalog import NAMESPACES, default_registry
from suan.graph.nodes import builtin_modules
from suan.graph.registry import Registry
from suan.skills import catalog as skill_catalog
from suan.skills.catalog import SkillCatalogError, load_catalog, lock_document
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_desktop_scripts import execute, scripts  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "tests" / "data" / "skill-catalog.lock.json"
BUILTIN = ["stk.muferro.domains@1", "stk.muferro.energy_trace@1", "stk.visualize.scalar_volume@2"]


def builtin_definition(name):
    return json.loads(files("suan.skills").joinpath("definitions").joinpath(f"{name}.json").read_text(encoding="utf-8"))


def write(folder, name, value):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    if isinstance(value, bytes):
        path.write_bytes(value)
    else:
        path.write_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def test_builtin_catalog_is_valid_bilingual_and_pinned():
    catalog = load_catalog()
    assert catalog.problems == []
    assert [skill["ref"] for skill in catalog.skills] == BUILTIN
    assert lock_document(catalog) == json.loads(LOCK.read_text(encoding="utf-8")), (
        "A shipped skill's definition or graph template changed: bump its version (a new id@version) or, for a "
        "deliberate correction, regenerate with `python -m suan.skills.catalog --lock --output "
        "tests/data/skill-catalog.lock.json` and record why in docs/development-log.md")
    for skill in catalog.skills:
        texts = [skill["title"], skill["summary"], *(e["title"] for e in skill["examples"]),
                 *(d["purpose"] for d in skill["dependencies"]["python"] + skill["dependencies"]["runtime"])]
        assert all(set(text) == {"en", "zh_CN"} for text in texts), skill["ref"]
        assert skill["guide"]["pack"] == "stk-visualize" and skill["entry"]["operation"] == "graph.evaluate"
        # Availability depends on this environment (the Windows client CI has no VTK): derive it.
        python = skill["dependencies"]["python"]
        assert all(d["available"] == skill_catalog.module_available(d["module"]) for d in python)
        missing = [d for d in python if not d["available"]]
        assert [(i["code"], i["subject"]) for i in skill["availability"]["issues"]] == [
            ("missing_module", d["module"]) for d in missing], skill["availability"]
        expected = ("available" if not missing else "unavailable" if any(not d["outputs"] for d in missing)
                    else "limited")
        assert skill["availability"]["status"] == expected, skill["availability"]
        assert skill["dependencies"]["runtime"] == [] or all(not item["checked"]
                                                             for item in skill["dependencies"]["runtime"])
    domains = load_catalog().get("stk.muferro.domains")
    assert [i["name"] for i in domains["inputs"]] == ["run"]
    assert [p["name"] for p in domains["parameters"]][:2] == ["step", "min_magnitude"]
    assert {o["name"]: o["type"] for o in domains["outputs"]} == {
        "view": "scene", "image": "image", "fractions": "table", "families": "table", "energy": "plot"}
    assert all(node["available"] for node in domains["dependencies"]["nodes"])
    assert "stk.analysis.orientation_classify@1" in [node["type"] for node in domains["dependencies"]["nodes"]]


def test_definitions_ship_in_the_package_and_are_not_skill_packs():
    from suan.skills import skill_names
    assert skill_names() == ["stk-monitor", "stk-visualize"]  # SKILL.md packs are a separate thing
    project = toml.load(ROOT / "pyproject.toml")["tool"]["poetry"]
    assert {"include": "suan"} in project["packages"]
    for pattern in project.get("exclude", ()):
        assert not Path("suan/skills/definitions/stk.muferro.domains.json").match(pattern), pattern


def test_content_hash_covers_definition_and_template_not_formatting(tmp_path, monkeypatch):
    definition = builtin_definition("stk.visualize.scalar_volume")
    builtin = load_catalog().get("stk.visualize.scalar_volume")["content_sha256"]
    write(tmp_path / "a", "stk.visualize.scalar_volume.json", json.dumps(definition, indent=4, sort_keys=True))
    assert load_catalog(directories=[("test", tmp_path / "a")]).skills[0]["content_sha256"] == builtin
    changed = {**definition, "summary": {**definition["summary"], "en": "Different method text."}}
    write(tmp_path / "b", "stk.visualize.scalar_volume.json", changed)
    assert load_catalog(directories=[("test", tmp_path / "b")]).skills[0]["content_sha256"] != builtin

    from suan.graph import catalog as graph_catalog
    original = graph_catalog.preset_document

    def edited(preset_id):
        preset = original(preset_id)
        preset["graph"]["parameters"][0]["default"] = "other.npy"
        return preset
    monkeypatch.setattr(graph_catalog, "preset_document", edited)
    assert load_catalog().get("stk.visualize.scalar_volume")["content_sha256"] != builtin


def test_bad_definitions_are_explained_and_never_hide_valid_skills(tmp_path):
    good = builtin_definition("stk.muferro.energy_trace")
    folder = tmp_path / "defs"
    write(folder, "stk.muferro.energy_trace.json", good)
    write(folder, "broken.json", "{\"schema\": ")
    write(folder, "dupkey.json", '{"schema": "stk.skill/1", "schema": "stk.skill/1"}')
    write(folder, "nan.json", '{"version": NaN}')
    write(folder, "latin1.json", b"\xff\xfe")
    write(folder, "list.json", [])
    write(folder, "big.json", " " * (skill_catalog.MAX_DEFINITION_BYTES + 1))
    write(folder, "x.missing_title.json", {**{k: v for k, v in good.items() if k != "title"},
                                           "id": "x.missing_title"})
    write(folder, "Bad.Id.json", {**good, "id": "Bad.Id"})
    write(folder, "x.extra.json", {**good, "id": "x.extra", "colour": "red"})
    write(folder, "renamed.json", {**good, "id": "x.renamed"})
    write(folder, "x.preset.json", {**good, "id": "x.preset", "entry": {"kind": "graph.preset", "preset": "no-such"}})
    write(folder, "x.nopreset.json", {**good, "id": "x.nopreset", "entry": {"kind": "graph.preset"}})
    write(folder, "x.guide.json", {**good, "id": "x.guide", "guide": {"pack": "no-such-pack"}})
    write(folder, "x.kind.json", {**good, "id": "x.kind", "entry": {"kind": "batch.template", "preset": "energy-plot"}})
    write(folder, "x.param.json", {**good, "id": "x.param", "examples": [
        {"title": {"en": "t"}, "parameters": {"nope": 1}}]})
    write(folder, "x.value.json", {**good, "id": "x.value", "examples": [
        {"title": {"en": "t"}, "parameters": {"stats": "yes"}}]})
    write(folder, "x.output.json", {**good, "id": "x.output", "examples": [{"title": {"en": "t"}, "outputs": ["nope"]}]})
    write(folder, "x.dependency.json", {**good, "id": "x.dependency", "dependencies": {"python": [
        {"module": "numpy", "outputs": ["nope"], "purpose": {"en": "p"}}]}})
    catalog = load_catalog(directories=[("test", folder)])
    assert [skill["ref"] for skill in catalog.skills] == ["stk.muferro.energy_trace@1"]
    found = {problem["file"]: problem for problem in catalog.problems}
    expected = {
        "broken.json": ("invalid_json", ""), "dupkey.json": ("invalid_json", ""), "nan.json": ("invalid_json", ""),
        "latin1.json": ("invalid_json", ""), "list.json": ("invalid_definition", ""), "big.json": ("unreadable", ""),
        "x.missing_title.json": ("invalid_definition", "/title"), "Bad.Id.json": ("invalid_definition", "/id"),
        "x.extra.json": ("invalid_definition", "/colour"), "renamed.json": ("file_name_mismatch", "/id"),
        "x.preset.json": ("unknown_preset", "/entry/preset"), "x.nopreset.json": ("invalid_definition", "/entry"),
        "x.guide.json": ("unknown_guide", "/guide/pack"), "x.kind.json": ("unsupported_entry", "/entry/kind"),
        "x.param.json": ("invalid_reference", "/examples/0/parameters"),
        "x.value.json": ("invalid_reference", "/examples/0/parameters/stats"),
        "x.output.json": ("invalid_reference", "/examples/0/outputs"),
        "x.dependency.json": ("invalid_reference", "/dependencies/python/0/outputs"),
    }
    assert {name: (found[name]["code"], found[name]["path"]) for name in expected} == expected
    assert all(problem["source"] == "test" and problem["message"] for problem in catalog.problems)
    assert found["x.preset.json"]["id"] == "x.preset" and found["x.preset.json"]["version"] == 1
    assert "batch.template" in found["x.kind.json"]["message"]
    error = pytest.raises(SkillCatalogError, catalog.get, "x.preset").value
    assert error.code == "not_found" and error.data["known_versions"] == []
    assert error.data["problems"][0]["code"] == "unknown_preset" and "no usable definition" in str(error)


def test_duplicate_skills_across_sources_keep_the_first(tmp_path):
    good = builtin_definition("stk.muferro.energy_trace")
    write(tmp_path / "one", "stk.muferro.energy_trace.json", good)
    write(tmp_path / "two", "stk.muferro.energy_trace.json", good)
    catalog = load_catalog(directories=[("one", tmp_path / "one"), ("two", tmp_path / "two")])
    assert [s["source"] for s in catalog.skills] == ["one"]
    assert [(p["source"], p["code"]) for p in catalog.problems] == [("two", "duplicate_skill")]


def test_versions_and_unknown_ids_are_explicit(tmp_path):
    good = builtin_definition("stk.muferro.energy_trace")
    write(tmp_path / "v1", "stk.muferro.energy_trace.json", good)
    write(tmp_path / "v2", "stk.muferro.energy_trace.json", {**good, "version": 2})
    catalog = load_catalog(directories=[("v1", tmp_path / "v1"), ("v2", tmp_path / "v2")])
    assert [s["ref"] for s in catalog.skills] == ["stk.muferro.energy_trace@1", "stk.muferro.energy_trace@2"]
    assert catalog.get("stk.muferro.energy_trace")["version"] == 2
    assert catalog.get("stk.muferro.energy_trace", 1)["version"] == 1
    assert catalog.get("stk.muferro.energy_trace", 1)["content_sha256"] != \
        catalog.get("stk.muferro.energy_trace", 2)["content_sha256"]
    missing = pytest.raises(SkillCatalogError, catalog.get, "stk.muferro.energy_trace", 3).value
    assert missing.code == "not_found" and missing.data["known_versions"] == [1, 2] and "known versions: 1, 2" in str(missing)
    unknown = pytest.raises(SkillCatalogError, catalog.get, "stk.no.such").value
    assert unknown.code == "not_found" and unknown.data == {"id": "stk.no.such", "known_versions": [], "problems": []}
    for args in (("",), ("x" * 97,), ("stk.muferro.energy_trace", 0), ("stk.muferro.energy_trace", True),
                 ("stk.muferro.energy_trace", "1")):
        assert pytest.raises(SkillCatalogError, catalog.get, *args).value.code == "invalid_params"


def test_availability_follows_modules_and_node_types(monkeypatch):
    monkeypatch.setattr(skill_catalog, "module_available", lambda name: name != "matplotlib")
    catalog = load_catalog()
    domains = catalog.get("stk.muferro.domains")["availability"]
    assert domains["status"] == "limited" and domains["unavailable_outputs"] == ["energy"]
    assert [(i["code"], i["subject"], i["outputs"]) for i in domains["issues"]] == [
        ("missing_module", "matplotlib", ["energy"])]
    assert catalog.get("stk.muferro.energy_trace")["availability"]["unavailable_outputs"] == ["energy"]
    assert catalog.get("stk.visualize.scalar_volume")["availability"]["status"] == "available"
    summaries = {s["ref"]: s["availability"]["status"] for s in catalog.page()["skills"]}
    assert summaries["stk.muferro.domains@1"] == "limited"

    monkeypatch.setattr(skill_catalog, "module_available", lambda name: name not in ("vtk", "matplotlib"))
    domains = load_catalog().get("stk.muferro.domains")["availability"]
    assert domains["status"] == "limited" and domains["unavailable_outputs"] == ["view", "image", "energy"]

    monkeypatch.setattr(skill_catalog, "module_available", lambda name: name != "numpy")
    assert {s["availability"]["status"] for s in load_catalog().skills} == {"unavailable"}

    monkeypatch.setattr(skill_catalog, "module_available", lambda name: True)
    registry = Registry(namespaces=NAMESPACES)
    for module in builtin_modules():
        if not module.__name__.endswith(".plot"):
            registry.register(module)
    energy = load_catalog(registry).get("stk.muferro.energy_trace")
    assert energy["availability"]["status"] == "unavailable"
    assert [(i["code"], i["subject"]) for i in energy["availability"]["issues"]] == [
        ("missing_node_type", "stk.plot.line@1")]
    assert {n["type"]: n["available"] for n in energy["dependencies"]["nodes"]} == {
        "stk.plot.line@1": False, "stk.source.muferro_run@1": True}
    assert next(o for o in energy["outputs"] if o["name"] == "energy")["type"] is None  # unknown without the node


def test_pages_and_queries_are_bounded():
    catalog = load_catalog()
    first = catalog.page(limit=1)
    assert [s["ref"] for s in first["skills"]] == BUILTIN[:1] and first["total"] == 3 and first["next_offset"] == 1
    last = catalog.page(offset=2, limit=1)
    assert [s["ref"] for s in last["skills"]] == BUILTIN[2:] and last["next_offset"] is None
    assert catalog.page(offset=10)["skills"] == [] and catalog.page(offset=10)["next_offset"] is None
    assert catalog.page(query="  MUFERRO ")["total"] == 2
    assert [s["id"] for s in catalog.page(query="铁电")["skills"]] == ["stk.muferro.domains"]
    assert [s["id"] for s in catalog.page(query="scalar-volume")["skills"]] == ["stk.visualize.scalar_volume"]
    assert catalog.page(query="no such text")["total"] == 0
    assert set(first["skills"][0]) == {"id", "version", "ref", "content_sha256", "source", "title", "summary", "entry",
                                       "availability"}
    for kwargs in ({"limit": 0}, {"limit": 201}, {"limit": True}, {"offset": -1}, {"offset": 1.0},
                   {"query": "x" * 201}, {"query": 3}):
        assert pytest.raises(SkillCatalogError, catalog.page, **kwargs).value.code == "invalid_params"


BLOCKED_EVALUATION = r'''
import importlib.abc, sys, tempfile
from pathlib import Path
blocked, preset, outputs, data = sys.argv[1], sys.argv[2], sys.argv[3].split(","), sys.argv[4]
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] == blocked:
            raise ModuleNotFoundError(f"blocked {name}", name=name)
sys.meta_path.insert(0, Block())
from suan.graph.catalog import build_registry
from suan.graph.resolve import LocalDirResolver
from suan.graph.service import MemoryBlobSink, evaluate_request
binding = "data" if preset == "scalar-volume" else "run"
params = {"path": "field.npy", "field": "field"} if preset == "scalar-volume" else {}
with tempfile.TemporaryDirectory() as cache:
    try:
        result = evaluate_request({"preset": preset, "outputs": outputs, "parameters": params},
                                  registry=build_registry(entry_points=False), resolver=LocalDirResolver({binding: data}),
                                  cache_dir=Path(cache), blob_sink=MemoryBlobSink())
    except Exception as exc:
        print("FAIL", type(exc).__name__, exc)
    else:
        print("OK" if sorted(result["outputs"]) == sorted(outputs) and not result.get("errors") else "PARTIAL")
'''


def test_declared_module_scopes_match_real_evaluation(tmp_path):
    """Each declared Python dependency is needed exactly where the definition says (offscreen PNG excluded)."""
    np = pytest.importorskip("numpy")
    pytest.importorskip("vtk")
    pytest.importorskip("matplotlib")
    from mupro_fake import write_domain_run
    write_domain_run(tmp_path / "run", grid=(8, 7, 6), steps=2, interval=1)
    (tmp_path / "field").mkdir()
    np.save(tmp_path / "field" / "field.npy", np.arange(24.0).reshape(2, 3, 4) - 7.25)
    catalog = load_catalog()
    for skill in catalog.skills:
        offline = [o["name"] for o in skill["outputs"] if o["name"] != "image"]  # PNG needs offscreen OpenGL
        data = tmp_path / ("field" if skill["entry"]["preset"] == "scalar-volume" else "run")
        for dependency in skill["dependencies"]["python"]:
            scoped = [name for name in offline if not dependency["outputs"] or name in dependency["outputs"]]
            others = [name for name in offline if name not in scoped]
            for outputs, expected in ((scoped[:1], "FAIL"), (others, "OK")):
                if not outputs:
                    continue
                run = subprocess.run([sys.executable, "-c", BLOCKED_EVALUATION, dependency["module"],
                                      skill["entry"]["preset"], ",".join(outputs), str(data)],
                                     capture_output=True, text=True, timeout=300, cwd=ROOT,
                                     env={**os.environ, "PYTHONPATH": str(ROOT)})
                assert run.stdout.split(" ", 1)[0].strip() == expected, (skill["ref"], dependency["module"], outputs,
                                                                         run.stdout, run.stderr[-2000:])


def test_bridge_methods_are_read_only_and_schema_checked(inproc):
    harness = inproc()
    hello = harness.call("hello", {"protocol": 1})
    assert {"skills.list", "skills.get"} <= set(hello["methods"])
    page = harness.call("skills.list", {"limit": 2})
    assert [s["ref"] for s in page["skills"]] == BUILTIN[:2] and page["total"] == 3 and page["next_offset"] == 2
    assert page["problems"] == [] and page["problem_count"] == 0
    assert [s["id"] for s in harness.call("skills.list", {"query": "ENERGY_OUT"})["skills"]] == ["stk.muferro.energy_trace"]
    skill = harness.call("skills.get", {"id": "stk.muferro.domains"})["skill"]
    assert skill == json.loads(json.dumps(load_catalog(default_registry()).get("stk.muferro.domains")))
    assert harness.call("skills.get", {"id": "stk.muferro.domains", "version": 1})["skill"]["ref"] == \
        "stk.muferro.domains@1"
    missing = harness.error("skills.get", {"id": "stk.muferro.domains", "version": 9})
    assert missing["code"] == "not_found" and missing["data"]["known_versions"] == [1]
    assert harness.error("skills.get", {"id": "nope"})["code"] == "not_found"
    for params in ({"limit": 0}, {"limit": 201}, {"offset": -1}, {"query": "x" * 201}, {"extra": 1}):
        assert harness.error("skills.list", params)["code"] == "invalid_params", params
    assert harness.error("skills.get", {})["code"] == "invalid_params"
    # Reading the catalog never starts the graph worker or opens a project.
    assert harness.bridge.graphs.worker._child is None
    assert harness.call("project.list")["projects"] == []
    assert not harness.violations
    harness.close()


def test_console_reads_the_same_catalog(scripts):
    session = scripts.call("script.open")["session"]
    result = execute(scripts, session, '''
page = stk.skills.list(limit=1, query='muferro')
assert page['total'] == 2 and page['next_offset'] == 1, page
skill = stk.skills.get(page['skills'][0]['id'], version=1)
assert skill['ref'] == page['skills'][0]['ref'] and skill['content_sha256'] == page['skills'][0]['content_sha256']
assert {'skills.list', 'skills.get'} <= set(stk.operations()['operations'])
from suan.scripting import ScriptError
try:
    stk.skills.get('stk.muferro.domains', version=2)
except ScriptError as error:
    assert error.code == 'not_found' and error.data['known_versions'] == [1]
else:
    raise AssertionError('unknown version accepted')
print(skill['ref'])
''')
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})["text"]
    assert "stk.muferro.domains@1" in scripts.call("script.read", {"session": session})["text"]
    assert not scripts.violations


def test_cli_catalog_and_show():
    from suan.cli.main import cli
    runner = CliRunner()
    listed = runner.invoke(cli, ["skills", "catalog"])
    assert listed.exit_code == 0, listed.output
    assert [line.split()[0] for line in listed.output.splitlines()] == BUILTIN
    page = json.loads(runner.invoke(cli, ["skills", "catalog", "--json", "--query", "volume"]).output)
    assert [s["ref"] for s in page["skills"]] == ["stk.visualize.scalar_volume@2"]
    shown = runner.invoke(cli, ["skills", "show", "stk.muferro.domains@1"])
    assert shown.exit_code == 0 and "graph.preset muferro-domains via graph.evaluate" in shown.output
    assert "not checked: offscreen_rendering for image" in shown.output
    as_json = json.loads(runner.invoke(cli, ["skills", "show", "stk.muferro.domains", "--json"]).output)
    assert as_json["ref"] == "stk.muferro.domains@1"
    for args, text in ((["show", "stk.muferro.domains@2"], "known versions: 1"), (["show", "x@y"], "Invalid version"),
                       (["catalog", "--limit", "0"], "limit")):
        failed = runner.invoke(cli, ["skills", *args])
        assert failed.exit_code != 0 and text in failed.output, failed.output
    assert runner.invoke(cli, ["skills", "list"]).exit_code == 0  # the SKILL.md pack listing is unchanged


def test_lock_command_writes_the_pinned_document(tmp_path):
    output = tmp_path / "lock.json"
    assert skill_catalog.main(["--lock", "--output", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8")) == json.loads(LOCK.read_text(encoding="utf-8"))
