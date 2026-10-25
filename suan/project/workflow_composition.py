"""Bounded, read-only composition of versioned workflow interfaces.

Compilation resolves project UUIDs, not executable Python. The resulting ordinary steps can be
frozen by WorkflowRuns; their identities derive from instance paths, so repeated calls are distinct.
"""
from copy import deepcopy
import hashlib

from suan.graph.schema import canonical_json, check_value, parameter_schema, validate_graph

from .store import ProjectError, RevisionConflict

MAX_DEPTH = 8
MAX_EXPANDED_STEPS = 1000
MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_EXPANDED_BYTES = 4 * 1024 * 1024


class CompositionError(ProjectError):
    def __init__(self, code, path, message):
        super().__init__(message)
        self.code, self.path = code, path


def check_interface(interface):
    from .workflows import _ident, _PORT_REF, _INPUT_REF
    from .analyses import _graph_schema
    if type(interface) is not dict or set(interface) != {"inputs", "outputs", "parameters"}:
        raise ProjectError("Workflow interface requires exactly inputs, outputs and parameters")
    for direction in ("inputs", "outputs"):
        ports = interface[direction]
        if type(ports) is not dict or len(ports) > 32:
            raise ProjectError("Workflow interface allows at most 32 inputs and 32 outputs")
        for name, port in ports.items():
            _ident(name, "interface port")
            keys = {"type"} if direction == "inputs" else {"type", "from"}
            types = ("rows", "files") if direction == "inputs" else ("rows", "files", "result")
            if type(port) is not dict or set(port) != keys or port.get("type") not in types:
                raise ProjectError("Invalid workflow interface port declaration")
            if direction == "outputs" and (type(port["from"]) is not str or
                    not (_PORT_REF.fullmatch(port["from"]) or _INPUT_REF.fullmatch(port["from"]))):
                raise ProjectError("Workflow interface outputs name a step.port or $input.port")
    if check_value(interface["parameters"], _graph_schema()["properties"]["parameters"]):
        raise ProjectError("Workflow interface parameters must match the structural graph parameter contract")
    graph = {"schema": "stk.graph/1", "nodes": [], "outputs": {}, "parameters": interface["parameters"]}
    # Reuse the parameter vocabulary without loading a node registry or any implementation.
    problems = [issue for issue in validate_graph(graph, None) if issue.path.startswith("/parameters")]
    if problems:
        raise ProjectError("Workflow interface: " + problems[0].message)


def _field(value):
    return type(value) is dict and set(value) == {"$field"}


def _parameter(value):
    return type(value) is dict and set(value) == {"$param"}


def check_bound_values(composition, values):
    """Enforce every declared interface, including constraints narrower than its consumers."""
    for item in composition["parameter_checks"]:
        value = item["value"]
        if item["field_binding"]:
            value = values.get(value["$field"])
        problems = check_value(value, parameter_schema(item["declaration"]))
        if problems:
            raise ProjectError(f"Workflow parameter {item['path']}: {problems[0][1]}")


def _compile(workflows, document, revision):
    from .workflows import COMPOSITE_FORMAT, MAX_WORKFLOWS, _PORT_REF, _INPUT_REF, _cycles
    flat, sources, paths, instances = [], {}, {}, {}
    aliases, completion, ports, parameters, forwards = {}, {}, [], [], []
    field_parameters = {}
    visits, source_bytes, expanded_bytes = 0, 0, 0

    def identity(path):
        return path[0] if len(path) == 1 else "w_" + hashlib.sha256(canonical_json(path)).hexdigest()[:62]

    def fail(code, path, message):
        raise CompositionError(code, "/".join(path), message)

    def visit(doc, path, supplied, overrides, stack, gates=(), override_fields=()):
        nonlocal visits, source_bytes, expanded_bytes
        if len(path) > MAX_DEPTH:
            fail("workflow_depth", path, f"Workflow nesting exceeds {MAX_DEPTH} levels")
        ids = [step["id"] for step in doc["steps"]]
        if len(ids) != len(set(ids)):
            fail("duplicate_step", path, "Step id is used more than once")
        edges = {}
        for step in doc["steps"]:
            before = list(step.get("after", []))
            before += [link["from"].split(".", 1)[0] for link in step.get("inputs", {}).values()
                       if not _INPUT_REF.fullmatch(link["from"])]
            for source in before:
                if source not in ids:
                    fail("missing_step", (*path, step["id"]), f"No step {source!r}")
                edges.setdefault(source, set()).add(step["id"])
        cyclic = _cycles(ids, edges)
        if cyclic:
            fail("cycle", (*path, cyclic[0]), "Step is on a dependency cycle")
        interface = doc["interface"]
        declarations = {p["name"]: p for p in interface["parameters"]}
        if set(overrides) - set(declarations):
            fail("unknown_parameter", path, "Subworkflow parameter is not declared by its interface")
        values = {name: overrides.get(name, p["default"]) for name, p in declarations.items()}
        for name, value in values.items():
            parameters.append({"path": "/".join((*path, name)), "declaration": declarations[name],
                               "value": value, "field_binding": name in override_fields})
        if set(supplied) != set(interface["inputs"]):
            fail("workflow_inputs", path, "Subworkflow links must match all declared interface inputs")
        for name, source in supplied.items():
            ports.append((path, source, interface["inputs"][name]["type"]))

        def reference(value):
            external = _INPUT_REF.fullmatch(value)
            if external:
                if external[1] not in supplied:
                    fail("unknown_input", path, f"No interface input {external[1]!r}")
                return supplied[external[1]]
            match = _PORT_REF.fullmatch(value)
            return identity((*path, match[1])) + "." + match[2]

        seen, members = set(), []
        for step in doc["steps"]:
            visits += 1
            if visits > MAX_EXPANDED_STEPS:
                fail("workflow_size", path, f"Workflow expansion exceeds {MAX_EXPANDED_STEPS} steps")
            local = step["id"]
            if local in seen:
                fail("duplicate_step", (*path, local), "Step id is used more than once")
            seen.add(local)
            step_path = (*path, local)
            here = identity(step_path)
            if here in paths:
                fail("step_identity_collision", step_path, "Expanded step identities collide")
            paths[here] = list(step_path)
            inputs = {name: {"from": reference(link["from"])} for name, link in step.get("inputs", {}).items()}
            after = list(gates) + [identity((*path, item)) for item in step.get("after", [])]
            bound, bound_fields = {}, set()
            for name, value in step.get("parameters", {}).items():
                if type(value) is dict and set(value) == {"$literal"}:
                    bound[name] = value["$literal"]
                elif _parameter(value):
                    key = value["$param"]
                    if type(key) is not str or key not in declarations:
                        fail("unknown_parameter", step_path, "The $param reference is not declared")
                    bound[name] = values[key]
                    if key in override_fields:
                        bound_fields.add(name)
                    forwards.append((here, name, declarations[key]))
                else:
                    bound[name] = value
                    if _field(value):
                        bound_fields.add(name)
            if step["kind"] != "workflow":
                if step["kind"] == "workflow_input":
                    fail("unknown_kind", step_path, "workflow_input is a reserved compiler step")
                item = deepcopy(step)
                item.update(id=here, inputs=inputs, parameters=bound, after=after)
                expanded_bytes += len(canonical_json(item))
                if expanded_bytes > MAX_EXPANDED_BYTES:
                    fail("workflow_size", step_path, "Expanded workflow steps exceed 4 MiB")
                flat.append(item)
                # Defaults are literals, even if their JSON has the shape of a binding.
                # Carry provenance through nested calls instead of inspecting substituted values.
                field_parameters[here] = sorted(bound_fields)
                members.append(here)
                continue
            if set(step["ref"]) != {"workflow"}:
                fail("invalid_reference", step_path, "A workflow step references exactly {workflow: UUID}")
            target = step["ref"]["workflow"]
            if target in stack:
                fail("workflow_cycle", step_path, "Workflow references form a cycle")
            if target not in sources:
                if len(sources) >= MAX_WORKFLOWS:
                    fail("workflow_size", step_path, "Too many referenced workflow documents")
                try:
                    result = workflows.get(target)
                except ProjectError as exc:
                    fail("missing_reference", step_path, str(exc))
                if result["revision"] != revision:
                    raise RevisionConflict("Project changed while resolving subworkflows")
                record = result["workflow"]
                if record["state"] != "readable" or record["format"] != COMPOSITE_FORMAT:
                    fail("workflow_interface", step_path, "A subworkflow needs a readable version 2 interface")
                raw = canonical_json(record["document"])
                source_bytes += len(raw)
                if source_bytes > MAX_SOURCE_BYTES:
                    fail("workflow_size", step_path, "Referenced workflow documents exceed 4 MiB")
                sources[target] = {"name": record["name"], "document": record["document"],
                                   "sha256": hashlib.sha256(raw).hexdigest()}
            child = sources[target]["document"]
            instances[here] = {"workflow_id": target, "path": list(step_path)}
            # A call's prerequisites guard every child task, including tasks unrelated to an output.
            child_gates = after + [link["from"].split(".", 1)[0] for link in inputs.values()]
            outputs, children = visit(child, step_path, {k: v["from"] for k, v in inputs.items()},
                                      bound, (*stack, target), child_gates, bound_fields)
            completion[here] = children + child_gates
            members.extend(children)
            for name, source in outputs.items():
                aliases[here + "." + name] = source
        exports = {name: reference(port["from"]) for name, port in interface["outputs"].items()}
        ports.extend((path, exports[name], port["type"]) for name, port in interface["outputs"].items())
        return exports, members

    supplied = {}
    for name, port in document["interface"]["inputs"].items():
        here = "i_" + hashlib.sha256(name.encode()).hexdigest()[:62]
        supplied[name] = here + ".value"
        flat.append({"id": here, "kind": "workflow_input", "ref": {"type": port["type"]}})
        paths[here] = ["$input", name]
    exports, _ = visit(document, (), supplied, {}, ())

    def resolve(source):
        seen = set()
        while source in aliases:
            if source in seen:
                fail("workflow_cycle", (), "Workflow output aliases form a cycle")
            seen.add(source)
            source = aliases[source]
        return source

    if _cycles(list(completion), {key: set(value) & set(completion) for key, value in completion.items()}):
        fail("workflow_cycle", (), "Workflow call dependencies form a cycle")

    def dependencies(values):
        pending, seen, result = list(values), set(), set()
        while pending:
            item = pending.pop()
            if item in seen:
                continue
            seen.add(item)
            if item in completion:
                pending.extend(completion[item])
            else:
                result.add(item)
        return sorted(result)

    for step in flat:
        after = list(step.get("after", []))
        for link in step.get("inputs", {}).values():
            before = link["from"].split(".", 1)[0]
            if before in completion:
                after.extend(completion[before])
            link["from"] = resolve(link["from"])
        step["after"] = dependencies(after)
    if len(canonical_json(flat)) > MAX_EXPANDED_BYTES:
        fail("workflow_size", (), "Expanded workflow dependencies exceed 4 MiB")
    return {"document": {"format": "stk.workflow-expanded/1", "steps": flat, "ui": {}}, "sources": sources,
            "step_paths": paths, "instances": instances, "parameter_checks": parameters, "forwards": forwards,
            "field_parameters": field_parameters,
            "ports": [(path, resolve(source), kind) for path, source, kind in ports],
            "outputs": {name: resolve(source) for name, source in exports.items()}}


def unchanged_steps(workflows, plan, current):
    """Compare frozen source paths independently, so a broken sibling does not stale every task."""
    def semantic(doc):
        return {key: ([{k: v for k, v in step.items() if k != "label"} for step in value]
                      if key == "steps" else value) for key, value in doc.items() if key != "ui"}

    original = plan["workflow_document"]
    if current.get("format") != original["format"] or current.get("interface") != original["interface"]:
        return {}
    old = {s["id"]: s for s in original["steps"]}
    new = {s["id"]: s for s in current["steps"]}
    duplicate = len(new) != len(current["steps"])
    changed_roots = {key for key in old if duplicate or key not in new or
                     semantic({"steps": [old[key]]}) != semantic({"steps": [new[key]]})}
    changed_sources = set()
    for identity, source in plan["composition"]["sources"].items():
        try:
            record = workflows.get(identity)["workflow"]
            same = record["state"] == "readable" and semantic(record["document"]) == semantic(source["document"])
        except ProjectError:
            same = False
        if not same:
            changed_sources.add(identity)
    affected = [item["path"] for item in plan["composition"]["instances"].values()
                if item["workflow_id"] in changed_sources]
    result = {}
    for step in plan["document"]["steps"]:
        path = plan["composition"]["step_paths"][step["id"]]
        if path[0] not in changed_roots and not any(path[:len(prefix)] == prefix for prefix in affected):
            result[step["id"]] = step
    return result


def validate_composition(workflows, document):
    from .workflows import _Issues, _parameter_summary, FIELD_PARAMETER_TYPES
    from suan.workflows.templates import workflow_templates
    revision = workflows.store.info()["revision"]
    try:
        compiled = _compile(workflows, document, revision)
    except CompositionError as exc:
        return {"revision": revision, "ok": False, "issues": [
            {"code": exc.code, "step": exc.path.split("/")[0], "path": exc.path, "message": str(exc)}],
                "omitted_issues": 0, "steps": [{"id": step["id"], "kind": step["kind"], "name": None,
                    "content_sha256": None, "file_count": None, "inputs": [], "outputs": [], "parameters": []}
                    for step in document["steps"]]}, None
    checked = workflows._validate_flat(compiled["document"], interface_inputs=True,
                                       field_parameters=compiled["field_parameters"])
    if checked["revision"] != revision:
        raise RevisionConflict("Project changed while validating subworkflows")
    issues = _Issues()
    for issue in checked["issues"]:
        path = compiled["step_paths"].get(issue["step"], [issue["step"]])
        issues.add(issue["code"], path[0], "/".join(path) + "/" + issue["path"], issue["message"])
    issues.omitted += checked["omitted_issues"]
    summaries = {item["id"]: item for item in checked["steps"]}
    for path, source, kind in compiled["ports"]:
        step, port = source.split(".", 1)
        declared = next((p for p in summaries.get(step, {}).get("outputs", []) if p["name"] == port), None)
        if declared is None or declared["type"] != kind:
            issues.add("interface_port", path[0] if path else "", "/".join(path),
                       f"Interface expects {kind} at {source}, but that output is absent or has a different type")
    for here, instance in compiled["instances"].items():
        source = compiled["sources"][instance["workflow_id"]]
        interface = source["document"]["interface"]
        summaries[here] = {"id": here, "kind": "workflow", "name": source["name"],
            "content_sha256": source["sha256"], "file_count": None,
            "inputs": [{"name": name, "type": p["type"], "required": True} for name, p in interface["inputs"].items()],
            "outputs": [{"name": name, "type": p["type"]} for name, p in interface["outputs"].items()],
            "parameters": [_parameter_summary(p) for p in interface["parameters"]]}
    for here, name, origin in compiled["forwards"]:
        target = next((p for p in summaries.get(here, {}).get("parameters", []) if p["name"] == name), None)
        if target and (target["type"] not in FIELD_PARAMETER_TYPES.get(origin["type"], {origin["type"]}) or
                       target.get("unit") and origin.get("unit") != target["unit"]):
            path = compiled["step_paths"][here]
            issues.add("parameter_interface", path[0], "/".join(path), "Forwarded parameter type or unit is incompatible")
    table_ids = {s["ref"]["table"] for s in compiled["document"]["steps"] if s["kind"] == "table" and set(s["ref"]) == {"table"}}
    with workflows.store._connect() as db:
        fields = {r["id"]: dict(r) for r in db.execute("SELECT id,table_id,type,unit FROM fields") if r["table_id"] in table_ids}
        if db.execute("SELECT revision FROM project").fetchone()[0] != revision:
            raise RevisionConflict("Project changed while validating workflow parameters")
    for item in compiled["parameter_checks"]:
        value, declaration = item["value"], item["declaration"]
        if item["field_binding"]:
            field = fields.get(value["$field"]) if type(value["$field"]) is str else None
            if (field is None or declaration["type"] not in FIELD_PARAMETER_TYPES.get(field["type"], ()) or
                    declaration.get("unit") and field["unit"] != declaration["unit"]):
                issues.add("parameter_interface", "", item["path"], "Interface field binding has an incompatible type, unit or table")
        else:
            for _, message in check_value(value, parameter_schema(declaration)):
                issues.add("parameter_interface", "", item["path"], message)
    tables = [s["ref"].get("table") for s in compiled["document"]["steps"] if s["kind"] == "table"]
    templates = workflow_templates()
    remote = any(s["kind"] == "simulation" and getattr(templates.get(s["ref"].get("template")), "remote", False)
                 for s in compiled["document"]["steps"])
    return {"revision": revision, "ok": not issues.items and not issues.omitted, "issues": issues.items,
            "omitted_issues": issues.omitted, "steps": [summaries[s["id"]] for s in document["steps"]],
            "execution": {"requires_runtime": remote, "table_id": tables[0] if len(tables) == 1 else None}}, compiled
