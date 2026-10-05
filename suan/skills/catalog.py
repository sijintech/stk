"""Versioned STK skill catalog (``stk.skill/1``, experimental and not frozen).

STK keeps three things apart:

* **SKILL.md packs** (``suan skills list|export``): method instructions for a model;
* the **node catalog** (``stk.catalog/1``): executable node types;
* **skills** (this module): a citable unit ``<id>@<version>`` that binds one executable entry to its
  inputs, parameters, outputs, dependencies and examples, optionally pointing at a SKILL.md pack as
  its method guide. The first entry kind is ``graph.preset``: a shipped graph preset that the
  ``graph.evaluate`` operation runs; the catalog itself never runs it.

Built-in definitions are ``suan/skills/definitions/<id>.json``. Reading the catalog never evaluates a
graph, starts a worker, imports a dependency or calls a model: node types come from the registry,
Python modules are looked up with :func:`importlib.util.find_spec`, and runtime capabilities such as
offscreen rendering are listed as declared but not probed. A broken definition is reported in
``problems`` and skipped; it never hides the other skills.

``content_sha256`` hashes the definition and its graph template (canonical JSON). Changing either
requires a new ``version``; ``tests/data/skill-catalog.lock.json`` pins the shipped pairs
(``python -m suan.skills.catalog --lock``). Standard library only.
"""
import argparse
import hashlib
from importlib import resources
import importlib.util
import json
from pathlib import Path
import sys

__all__ = ["DEFAULT_LIMIT", "MAX_LIMIT", "SCHEMA", "SkillCatalog", "SkillCatalogError", "load_catalog",
           "lock_document", "module_available"]

SCHEMA = "stk.skill/1"
DEFAULT_LIMIT = 50
MAX_LIMIT = 200
MAX_QUERY = 200
MAX_OFFSET = 1_000_000
MAX_VERSION = 1_000_000
MAX_PROBLEMS = 50
MAX_DEFINITION_BYTES = 256 * 1024
ENTRY_KINDS = ("graph.preset",)
RUNTIME_CAPABILITIES = ("offscreen_rendering",)
SKILL_ID_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,3}$"


def _localized(max_length):
    text = {"type": "string", "minLength": 1, "maxLength": max_length}
    return {"type": "object", "properties": {"en": text, "zh_CN": text}, "required": ["en"],
            "additionalProperties": False}


_NAMES = {"type": "array", "maxItems": 32, "uniqueItems": True,
          "items": {"type": "string", "minLength": 1, "maxLength": 64}}

DEFINITION_SCHEMA = {
    "type": "object",
    "properties": {
        "schema": {"const": SCHEMA},
        "id": {"type": "string", "maxLength": 96, "pattern": SKILL_ID_PATTERN},
        "version": {"type": "integer", "minimum": 1, "maximum": MAX_VERSION},
        "title": _localized(120),
        "summary": _localized(1000),
        "guide": {"type": "object", "properties": {"pack": {"type": "string", "pattern": r"^[a-z0-9][a-z0-9-]{0,63}$"}},
                  "required": ["pack"], "additionalProperties": False},
        "entry": {"type": "object",
                  "properties": {"kind": {"type": "string", "minLength": 1, "maxLength": 64},
                                 "preset": {"type": "string", "pattern": r"^[a-z0-9][a-z0-9_-]{0,63}$"}},
                  "required": ["kind"], "additionalProperties": False},
        "dependencies": {
            "type": "object",
            "properties": {
                "python": {"type": "array", "maxItems": 16, "items": {
                    "type": "object",
                    "properties": {"module": {"type": "string", "pattern": r"^[A-Za-z_][A-Za-z0-9_]{0,63}$"},
                                   "outputs": _NAMES, "purpose": _localized(300)},
                    "required": ["module", "purpose"], "additionalProperties": False}},
                "runtime": {"type": "array", "maxItems": 8, "items": {
                    "type": "object",
                    "properties": {"capability": {"enum": list(RUNTIME_CAPABILITIES)}, "outputs": _NAMES,
                                   "purpose": _localized(300)},
                    "required": ["capability", "purpose"], "additionalProperties": False}},
            },
            "additionalProperties": False,
        },
        "examples": {"type": "array", "maxItems": 8, "items": {
            "type": "object",
            "properties": {"title": _localized(200), "parameters": {"type": "object", "maxProperties": 64},
                           "outputs": _NAMES},
            "required": ["title"], "additionalProperties": False}},
    },
    "required": ["schema", "id", "version", "title", "summary", "entry"],
    "additionalProperties": False,
}


class SkillCatalogError(Exception):
    """A request the catalog cannot answer; ``code`` is a desktop-bridge error code."""

    def __init__(self, code, message, data=None):
        super().__init__(message)
        self.code = code
        self.data = data or {}


def module_available(name):
    """Whether top-level module ``name`` can be found, without importing it."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _strict_load(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    def constant(name):
        raise ValueError(f"{name} is not JSON")
    return json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)


def _builtin_root():
    return resources.files(__package__).joinpath("definitions")


def _definition_files(root):
    try:
        entries = sorted(root.iterdir(), key=lambda entry: entry.name)
    except (FileNotFoundError, NotADirectoryError):
        return []
    return [entry for entry in entries if entry.name.endswith(".json") and not entry.name.startswith(".")
            and entry.is_file()]


class _Problems:
    def __init__(self):
        self.items = []

    def add(self, source, file, code, message, path="", definition=None):
        item = {"source": source, "file": file, "code": code, "message": message, "path": path}
        if isinstance(definition, dict):
            if isinstance(definition.get("id"), str):
                item["id"] = definition["id"][:96]
            if type(definition.get("version")) is int:
                item["version"] = definition["version"]
        self.items.append(item)


def _text_values(value):
    return [text for text in value.values() if isinstance(text, str)] if isinstance(value, dict) else []


def _output_port_type(graph, reference, registry):
    node_id, _, port_name = str(reference).partition(".")
    node = next((n for n in graph.get("nodes") or () if isinstance(n, dict) and n.get("id") == node_id), None)
    node_type = registry.get(node.get("type")) if node and registry is not None else None
    port = node_type.output(port_name) if node_type is not None else None
    if port is None:
        return None
    return port.type if isinstance(port.type, str) else " | ".join(port.type)


def _resolve(definition, registry, guides, problems, source, file):
    """The served skill document, or ``None`` after reporting why the definition cannot be used."""
    from suan.graph.catalog import describe_preset, preset_document
    from suan.graph.schema import GraphError, check_value, parameter_schema, validate_graph

    entry = definition["entry"]
    if entry["kind"] not in ENTRY_KINDS:
        problems.add(source, file, "unsupported_entry",
                     f"Entry kind {entry['kind']!r} is not supported by this STK (supported: {', '.join(ENTRY_KINDS)})",
                     "/entry/kind", definition)
        return None
    if "preset" not in entry:
        problems.add(source, file, "invalid_definition", "A graph.preset entry needs 'preset'", "/entry", definition)
        return None
    try:
        preset = preset_document(entry["preset"])
    except GraphError as exc:
        problems.add(source, file, "unknown_preset", exc.message, "/entry/preset", definition)
        return None
    except (OSError, ValueError) as exc:
        problems.add(source, file, "unknown_preset", f"Preset {entry['preset']!r} cannot be read: {exc}",
                     "/entry/preset", definition)
        return None
    guide = None
    if "guide" in definition:
        pack = definition["guide"]["pack"]
        if pack not in guides:
            problems.add(source, file, "unknown_guide", f"Guide pack {pack!r} is not installed", "/guide/pack",
                         definition)
            return None
        guide = {"pack": pack, "description": guides[pack]}

    graph = preset["graph"]
    described = describe_preset(preset, registry)
    declarations = {p.get("name"): p for p in described["parameters"] if isinstance(p, dict)}
    output_names = list((graph.get("outputs") or {}).keys())
    dependencies = definition.get("dependencies") or {}
    bad = False
    for kind in ("python", "runtime"):
        for index, dependency in enumerate(dependencies.get(kind, ())):
            for name in dependency.get("outputs", ()):
                if name not in output_names:
                    problems.add(source, file, "invalid_reference", f"Dependency output {name!r} is not a graph output",
                                 f"/dependencies/{kind}/{index}/outputs", definition)
                    bad = True
    for index, example in enumerate(definition.get("examples", ())):
        for name, value in (example.get("parameters") or {}).items():
            if name not in declarations:
                problems.add(source, file, "invalid_reference", f"Example parameter {name!r} is not a graph parameter",
                             f"/examples/{index}/parameters", definition)
                bad = True
                continue
            try:
                issues = check_value(value, parameter_schema(declarations[name]))
            except ValueError as exc:
                issues = [("", str(exc))]
            if issues:
                problems.add(source, file, "invalid_reference",
                             f"Example value for {name!r} does not fit the parameter: {issues[0][1]}",
                             f"/examples/{index}/parameters/{name}", definition)
                bad = True
        for name in example.get("outputs", ()):
            if name not in output_names:
                problems.add(source, file, "invalid_reference", f"Example output {name!r} is not a graph output",
                             f"/examples/{index}/outputs", definition)
                bad = True
    if bad:
        return None

    issues = []
    node_types = sorted({n.get("type") for n in graph.get("nodes") or () if isinstance(n, dict)
                         and isinstance(n.get("type"), str)})
    template_issues = [issue for issue in validate_graph(graph, registry) if issue.severity == "error"]
    # Missing node types are reported once per type below; their nodes' follow-on issues add nothing.
    unknown_nodes = {issue.node for issue in template_issues if issue.code == "unknown_type"}
    for issue in template_issues:
        if issue.code != "unknown_type" and (issue.node is None or issue.node not in unknown_nodes):
            issues.append({"code": "invalid_template", "message": issue.message, "subject": issue.path,
                           "outputs": []})
    nodes = [{"type": node_type, "available": node_type in registry} for node_type in node_types]
    issues.extend({"code": "missing_node_type", "message": f"Node type {n['type']} is not installed",
                   "subject": n["type"], "outputs": []} for n in nodes if not n["available"])
    python = []
    for dependency in dependencies.get("python", ()):
        available = module_available(dependency["module"])
        python.append({"module": dependency["module"], "outputs": list(dependency.get("outputs", ())),
                       "purpose": dependency["purpose"], "available": available})
        if not available:
            issues.append({"code": "missing_module", "message": f"Python module {dependency['module']} is not installed",
                           "subject": dependency["module"], "outputs": list(dependency.get("outputs", ()))})
    runtime = [{"capability": d["capability"], "outputs": list(d.get("outputs", ())), "purpose": d["purpose"],
                "checked": False} for d in dependencies.get("runtime", ())]
    if any(not issue["outputs"] for issue in issues):
        status, limited = "unavailable", []
    else:
        limited = [name for name in output_names if any(name in issue["outputs"] for issue in issues)]
        status = "limited" if limited else "available"

    outputs = [{"name": name, "from": reference, "type": _output_port_type(graph, reference, registry)}
               for name, reference in (graph.get("outputs") or {}).items()]
    digest = hashlib.sha256(_canonical({"definition": definition, "template": preset}).encode("utf-8")).hexdigest()
    return {
        "schema": SCHEMA,
        "id": definition["id"],
        "version": definition["version"],
        "ref": f"{definition['id']}@{definition['version']}",
        "content_sha256": digest,
        "source": source,
        "title": definition["title"],
        "summary": definition["summary"],
        "guide": guide,
        "entry": {"kind": entry["kind"], "preset": entry["preset"], "operation": "graph.evaluate",
                  "name": described["name"]},
        "inputs": [{"name": b["name"], "kind": "binding", "description": b["description"]}
                   for b in described["bindings"]],
        "parameters": described["parameters"],
        "outputs": outputs,
        "dependencies": {"nodes": nodes, "python": python, "runtime": runtime},
        "examples": [{"title": e["title"], "parameters": dict(e.get("parameters") or {}),
                      "outputs": list(e.get("outputs", ()))} for e in definition.get("examples", ())],
        "availability": {"status": status, "unavailable_outputs": limited, "issues": issues},
    }


def _summary(skill):
    return {key: skill[key] for key in ("id", "version", "ref", "content_sha256", "source", "title", "summary",
                                        "availability")} | {
        "entry": {key: skill["entry"][key] for key in ("kind", "preset") if key in skill["entry"]}}


class SkillCatalog:
    """Resolved skills (sorted by id, then version) and the problems of unusable definitions."""

    def __init__(self, skills, problems):
        self.skills = skills
        self.problems = problems

    def page(self, *, offset=0, limit=DEFAULT_LIMIT, query=None):
        """``{skills: [summary], total, offset, next_offset, problems, problem_count}``."""
        if type(offset) is not int or not 0 <= offset <= MAX_OFFSET:
            raise SkillCatalogError("invalid_params", f"offset must be an integer from 0 to {MAX_OFFSET}")
        if type(limit) is not int or not 1 <= limit <= MAX_LIMIT:
            raise SkillCatalogError("invalid_params", f"limit must be an integer from 1 to {MAX_LIMIT}")
        if query is not None and (not isinstance(query, str) or len(query) > MAX_QUERY):
            raise SkillCatalogError("invalid_params", f"query must be a string of at most {MAX_QUERY} characters")
        needle = (query or "").strip().casefold()
        matched = [skill for skill in self.skills if not needle or any(
            needle in text.casefold() for text in [skill["id"], skill["ref"], skill["entry"].get("preset", ""),
                                                   *_text_values(skill["title"]), *_text_values(skill["summary"])])]
        chunk = matched[offset:offset + limit]
        end = offset + len(chunk)
        return {"skills": [_summary(skill) for skill in chunk], "total": len(matched), "offset": offset,
                "next_offset": end if end < len(matched) else None,
                "problems": self.problems[:MAX_PROBLEMS], "problem_count": len(self.problems)}

    def get(self, skill_id, version=None):
        """The full skill document (latest version unless ``version``)."""
        if not isinstance(skill_id, str) or not skill_id or len(skill_id) > 96:
            raise SkillCatalogError("invalid_params", "id must be a skill id of at most 96 characters")
        if version is not None and (type(version) is not int or not 1 <= version <= MAX_VERSION):
            raise SkillCatalogError("invalid_params", f"version must be an integer from 1 to {MAX_VERSION}")
        versions = [skill for skill in self.skills if skill["id"] == skill_id]
        known = [skill["version"] for skill in versions]
        if version is not None:
            versions = [skill for skill in versions if skill["version"] == version]
        if versions:
            return versions[-1]
        broken = [problem for problem in self.problems if problem.get("id") == skill_id]
        if version is not None and known:
            message = f"Skill {skill_id} has no version {version}; known versions: {', '.join(map(str, known))}"
        elif broken:
            message = f"Skill {skill_id} has no usable definition: {broken[0]['message']}"
        else:
            message = f"Unknown skill {skill_id}"
        raise SkillCatalogError("not_found", message, {"id": skill_id, "known_versions": known,
                                                       "problems": broken[:MAX_PROBLEMS]})


def load_catalog(registry=None, *, directories=None):
    """Read and resolve definitions; ``directories`` (``[(source label, directory)]``) replaces the built-ins.

    ``registry`` defaults to the process-wide node registry. Definitions are reread on every call, so
    availability follows the current environment.
    """
    from suan.graph.catalog import default_registry
    from suan.graph.schema import check_value
    from . import list_skills

    registry = registry if registry is not None else default_registry()
    roots = directories if directories is not None else [("builtin", _builtin_root())]
    guides = {item["name"]: item["description"] for item in list_skills()}
    problems = _Problems()
    skills = {}
    for source, root in roots:
        root = Path(root) if isinstance(root, str) else root
        for entry in _definition_files(root):
            file = entry.name
            try:
                data = entry.read_bytes()
                if len(data) > MAX_DEFINITION_BYTES:
                    raise ValueError(f"larger than {MAX_DEFINITION_BYTES} bytes")
            except (OSError, ValueError) as exc:
                problems.add(source, file, "unreadable", f"Cannot read the definition: {exc}")
                continue
            try:
                definition = _strict_load(data)
            except (UnicodeDecodeError, ValueError) as exc:  # JSONDecodeError is a ValueError
                problems.add(source, file, "invalid_json", f"Not a UTF-8 JSON document: {exc}")
                continue
            errors = check_value(definition, DEFINITION_SCHEMA)
            if errors:
                for path, message in errors[:8]:
                    problems.add(source, file, "invalid_definition", message, path, definition)
                continue
            if file != f"{definition['id']}.json":
                problems.add(source, file, "file_name_mismatch",
                             f"The file of skill {definition['id']} must be named {definition['id']}.json", "/id",
                             definition)
                continue
            key = (definition["id"], definition["version"])
            if key in skills:
                problems.add(source, file, "duplicate_skill",
                             f"{definition['id']}@{definition['version']} is already defined by "
                             f"{skills[key]['source']}", "/id", definition)
                continue
            try:
                skill = _resolve(definition, registry, guides, problems, source, file)
            except Exception as exc:  # a broken preset or plugin must not hide the other skills
                problems.add(source, file, "invalid_definition", f"{type(exc).__name__}: {exc}", "", definition)
                continue
            if skill is not None:
                skills[key] = skill
    return SkillCatalog([skills[key] for key in sorted(skills)], problems.items)


def lock_document(catalog):
    """``{"schema": "stk.skill-lock/1", "skills": {ref: content_sha256}}`` of ``catalog``."""
    return {"schema": "stk.skill-lock/1", "skills": {skill["ref"]: skill["content_sha256"] for skill in catalog.skills}}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m suan.skills.catalog", description=__doc__.splitlines()[0])
    parser.add_argument("--lock", action="store_true", help="print the id@version -> content_sha256 lock document")
    parser.add_argument("--output", type=Path, help="write to this file instead of standard output")
    args = parser.parse_args(argv)
    catalog = load_catalog()
    if catalog.problems:
        for problem in catalog.problems:
            print(f"{problem['file']}: {problem['code']}: {problem['message']}", file=sys.stderr)
        return 1
    document = lock_document(catalog) if args.lock else {"skills": catalog.skills}
    text = json.dumps(document, ensure_ascii=False, indent=1) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
