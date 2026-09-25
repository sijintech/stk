"""Packaged agent skills: content, examples, the generated node reference and `suan skills list|export`."""
from importlib.resources import files
import json
from pathlib import Path
import re

from click.testing import CliRunner
import pytest
import toml

from suan.graph.catalog import catalog_document, default_registry, spec_catalog
from suan.graph.registry import Registry
from suan.graph.schema import validate_graph
from suan.skills import export_skills, list_skills, read_frontmatter, skill_names
from suan.skills.reference import nodes_markdown

ROOT = Path(__file__).resolve().parents[1]


def examples():
    folder = files("suan.skills").joinpath("stk-visualize").joinpath("examples")
    return sorted((entry.name, json.loads(entry.read_text(encoding="utf-8"))) for entry in folder.iterdir()
                  if entry.name.endswith(".json"))


def test_skills_ship_inside_the_package():
    assert skill_names() == ["stk-monitor", "stk-visualize"]
    for name in skill_names():
        text = files("suan.skills").joinpath(name).joinpath("SKILL.md").read_text(encoding="utf-8")
        meta = read_frontmatter(text)
        assert meta["name"] == name and 40 < len(meta["description"]) < 1024
    listed = {item["name"]: item for item in list_skills()}
    assert "reference/nodes.md" in listed["stk-visualize"]["files"]
    assert {f for f in listed["stk-visualize"]["files"] if f.startswith("examples/")} == {
        f"examples/{name}" for name, _ in examples()}
    # Poetry ships every file under the `suan` package unless excluded; nothing excludes the skills.
    project = toml.load(ROOT / "pyproject.toml")["tool"]["poetry"]
    assert {"include": "suan"} in project["packages"]
    for pattern in project.get("exclude", ()):
        assert not Path("suan/skills/stk-visualize/SKILL.md").match(pattern), pattern
        assert not Path("suan/skills/stk-visualize/examples/muferro-domains.json").match(pattern), pattern


def test_visualize_skill_teaches_the_workflow_and_honest_reporting():
    text = files("suan.skills").joinpath("stk-visualize").joinpath("SKILL.md").read_text(encoding="utf-8")
    order = [text.index(step) for step in ("**Find the run.**", "**Start from a preset", "**Bind the data",
                                           "**Validate.**", "**Render or evaluate.**", "**Report honestly**")]
    assert order == sorted(order)
    for tool in ("graph_catalog", "graph_validate", "graph_render", "graph_evaluate", "plot_table", "list_tasks"):
        assert f"`{tool}`" in text
    assert "Never infer physics from colours" in text
    assert "`unspecified`" in text and "`normalized`" in text and "`grid_index`" in text
    assert re.search(r"`-1` = unclassified", text) and re.search(r"`0` = substrate", text)
    assert "min_magnitude" in text and "denominator" in text
    assert "never contain filesystem paths" in text
    monitor = files("suan.skills").joinpath("stk-monitor").joinpath("SKILL.md").read_text(encoding="utf-8")
    assert "`get_task_events(" in monitor and "next_offset" in monitor and "Progress is not success" in monitor


def test_examples_are_valid_graphs():
    spec = spec_catalog()
    registry = Registry.from_catalog(spec) if spec else None
    live = default_registry()
    assert {name for name, _ in examples()} >= {"muferro-domains.json", "muferro-energy-plot.json",
                                                "muferro-polarization-glyphs.json",
                                                "muferro-polarization-isosurface.json",
                                                "muferro-polarization-volume.json"}
    for name, graph in examples():
        assert "/" not in json.dumps(graph["nodes"]).replace('"from"', ""), name  # bindings, never paths
        if registry is not None:
            assert validate_graph(graph, registry) == [], name
        # Against the installed catalog: every issue is only a node family not installed yet.
        issues = validate_graph(graph, live)
        assert all(issue.code == "unknown_type" for issue in issues if issue.severity == "error"), (name, issues)


def test_committed_node_reference_matches_the_spec_catalog():
    spec = spec_catalog()
    if spec is None:
        pytest.skip("the spec catalog ships only with a source checkout")
    committed = files("suan.skills").joinpath("stk-visualize").joinpath("reference").joinpath("nodes.md")
    assert committed.read_text(encoding="utf-8") == nodes_markdown(spec), \
        "regenerate: python -m suan.skills.reference --spec --output suan/skills/stk-visualize/reference/nodes.md"
    live = nodes_markdown(catalog_document())
    for node in catalog_document()["nodes"]:
        assert f"## `{node['id']}`" in live
    assert "| `binding` | string | **required** | data |" in live


def test_cli_lists_and_exports(tmp_path):
    from suan.cli.main import cli
    runner = CliRunner()
    listed = runner.invoke(cli, ["skills", "list"])
    assert listed.exit_code == 0, listed.output
    assert "stk-visualize" in listed.output and "stk-monitor" in listed.output
    as_json = json.loads(runner.invoke(cli, ["skills", "list", "--json"]).output)
    assert [item["name"] for item in as_json] == ["stk-monitor", "stk-visualize"]

    dest = tmp_path / "skills"
    exported = runner.invoke(cli, ["skills", "export", "--dest", str(dest)])
    assert exported.exit_code == 0, exported.output
    assert (dest / "stk-visualize" / "SKILL.md").read_bytes() == \
        files("suan.skills").joinpath("stk-visualize").joinpath("SKILL.md").read_bytes()
    reference = (dest / "stk-visualize" / "reference" / "nodes.md").read_text(encoding="utf-8")
    assert reference == nodes_markdown(catalog_document())  # regenerated from the installed catalog
    assert json.loads((dest / "stk-visualize" / "examples" / "muferro-domains.json").read_text(encoding="utf-8"))["schema"] == \
        "stk.graph/1"
    assert (dest / "stk-monitor" / "SKILL.md").is_file()
    assert not list(dest.rglob("__pycache__")) and not list(dest.rglob("*.py"))

    again = runner.invoke(cli, ["skills", "export", "--dest", str(dest)])
    assert again.exit_code != 0 and "--force" in again.output
    (dest / "stk-monitor" / "stale.md").write_text("old")
    forced = runner.invoke(cli, ["skills", "export", "--dest", str(dest), "--name", "stk-monitor", "--force"])
    assert forced.exit_code == 0, forced.output
    assert not (dest / "stk-monitor" / "stale.md").exists()
    unknown = runner.invoke(cli, ["skills", "export", "--dest", str(tmp_path / "x"), "--name", "nope"])
    assert unknown.exit_code != 0 and "Unknown skill" in unknown.output
    with pytest.raises(ValueError):
        export_skills(tmp_path / "y", ["nope"])


def test_forced_export_replaces_links_and_files_without_touching_their_targets(tmp_path):
    from suan.cli.main import cli
    runner = CliRunner()
    dest, shared = tmp_path / "skills", tmp_path / "shared-skill"
    dest.mkdir()
    shared.mkdir()
    (shared / "keep.md").write_text("mine")
    (dest / "stk-monitor").symlink_to(shared, target_is_directory=True)  # e.g. a skill linked from a repo
    (dest / "stk-visualize").write_text("a stray file")
    refused = runner.invoke(cli, ["skills", "export", "--dest", str(dest)])
    assert refused.exit_code != 0 and "--force" in refused.output
    forced = runner.invoke(cli, ["skills", "export", "--dest", str(dest), "--force"])
    assert forced.exit_code == 0, forced.output
    assert not (dest / "stk-monitor").is_symlink() and (dest / "stk-monitor" / "SKILL.md").is_file()
    assert (dest / "stk-visualize" / "SKILL.md").is_file()
    assert sorted(p.name for p in shared.iterdir()) == ["keep.md"]  # the link's target is untouched
    (dest / "stk-monitor").rename(tmp_path / "old")
    (dest / "stk-monitor").symlink_to(tmp_path / "missing", target_is_directory=True)  # a dangling link
    assert "--force" in runner.invoke(cli, ["skills", "export", "--dest", str(dest)]).output
    assert runner.invoke(cli, ["skills", "export", "--dest", str(dest), "--force"]).exit_code == 0
    assert (dest / "stk-monitor" / "SKILL.md").is_file()
    # Errors of the file system are reported as messages, not tracebacks.
    blocked = tmp_path / "file"
    blocked.write_text("a file where a directory is expected")
    failed = runner.invoke(cli, ["skills", "export", "--dest", str(blocked / "skills")])
    assert failed.exit_code == 1 and "Error:" in failed.output, failed.output
    assert isinstance(failed.exception, SystemExit)
