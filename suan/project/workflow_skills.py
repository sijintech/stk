"""Project workflow method snapshots and atomic, explicitly rebound instances.

Only saved JSON and database metadata are read. A skill never captures table rows, file bytes,
Runtime connections or engine implementations, and these operations never load engine plugins.
"""
from copy import deepcopy
import hashlib
import re
from uuid import uuid4

from suan.graph.schema import canonical_json

from . import analyses, files, workflows
from .field_types import FIELD_TYPES
from .managed import clone, name as checked_name, snapshot_limit
from .store import ProjectError, RevisionConflict, _expected_revision, _id, _json
from .workflow_composition import MAX_DEPTH, MAX_EXPANDED_STEPS, _compile


MAX_TEMPLATE_BYTES = 8 * 1024 * 1024
MAX_DEPENDENCIES = 1000


def _digest(value):
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _sha(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ProjectError("Workflow skill requires lowercase SHA-256 digests")
    return value


def _object(value, keys, what):
    if type(value) is not dict or set(value) != set(keys):
        raise ProjectError(f"Workflow skill {what} has invalid fields")


def _reference_inventory(root, documents):
    """Check the closed workflow DAG, counting repeated calls against the expansion budget."""
    seen, analysis_ids, table_ids, field_ids, snapshot_ids, template_ids = set(), set(), set(), set(), set(), set()
    visits = 0

    def visit(identity, stack):
        nonlocal visits
        if identity in stack:
            raise ProjectError("Workflow skill references form a cycle")
        if len(stack) > MAX_DEPTH:
            raise ProjectError("Workflow skill nesting exceeds 8 levels")
        if identity not in documents:
            raise ProjectError("Workflow skill is missing a referenced workflow")
        doc = documents[identity]["document"]
        seen.add(identity)
        step_ids = [step["id"] for step in doc["steps"]]
        if len(step_ids) != len(set(step_ids)):
            raise ProjectError("Workflow skill has duplicate step IDs")
        edges = {}
        for step in doc["steps"]:
            visits += 1
            if visits > MAX_EXPANDED_STEPS:
                raise ProjectError("Workflow skill expansion exceeds 1000 steps")
            kind = step["kind"]
            key = "workflow" if kind == "workflow" else workflows.REF_KEYS.get(kind)
            if key is None or set(step["ref"]) != {key}:
                raise ProjectError("Workflow skill has an unsupported step or invalid reference")
            target = step["ref"][key]
            if kind != "simulation":
                _id(target)
            predecessors = list(step.get("after", []))
            predecessors.extend(link["from"].split(".", 1)[0] for link in step.get("inputs", {}).values()
                                if not link["from"].startswith("$input."))
            for before in predecessors:
                if before not in step_ids:
                    raise ProjectError("Workflow skill references a missing step")
                edges.setdefault(before, set()).add(step["id"])
            for value in step.get("parameters", {}).values():
                # Deliberately never descend into defaults, $literal, graph JSON, UI or extensions.
                if type(value) is dict and set(value) == {"$field"}:
                    _id(value["$field"])
                    field_ids.add(value["$field"])
            if kind == "workflow":
                if doc["format"] != workflows.COMPOSITE_FORMAT:
                    raise ProjectError("Nested workflow calls require workflow version 2")
                if target in documents and documents[target]["document"]["format"] != workflows.COMPOSITE_FORMAT:
                    raise ProjectError("A nested workflow requires a version 2 interface")
                visit(target, (*stack, identity))
            elif kind == "analysis":
                analysis_ids.add(target)
            elif kind == "table":
                table_ids.add(target)
            elif kind == "files":
                snapshot_ids.add(target)
            else:
                template_ids.add(target)
        if workflows._cycles(step_ids, edges):
            raise ProjectError("Workflow skill step dependencies form a cycle")

    visit(root, ())
    if seen != set(documents):
        raise ProjectError("Workflow skill contains workflows outside its reference closure")
    return analysis_ids, table_ids, field_ids, snapshot_ids, template_ids


def _compiled(template):
    """The structural compiler uses only this frozen resolver, never the current project."""
    root = template["workflows"][template["root"]]["document"]
    if root["format"] != workflows.COMPOSITE_FORMAT:
        return

    class Frozen:
        def get(self, identity):
            entry = template["workflows"].get(identity)
            if entry is None:
                raise ProjectError("Workflow skill is missing a referenced workflow")
            return {"revision": 0, "workflow": {**entry, "state": "readable", "format": entry["document"]["format"]}}

    result = _compile(Frozen(), root, 0)
    ports = {}
    for step in result["document"]["steps"]:
        kind, ref = step["kind"], step["ref"]
        if kind == "analysis":
            graph = template["analyses"][ref["analysis"]]["document"]["graph"]
            outputs = {output: "result" for output in graph["outputs"]}
        elif kind == "workflow_input":
            outputs = {"value": ref["type"]}
        else:
            outputs = {"rows": "rows"} if kind == "table" else {"files": "files"}
        ports.update({step["id"] + "." + output: kind for output, kind in outputs.items()})
    for _, source, kind in result["ports"]:
        if ports.get(source) != kind:
            raise ProjectError("Workflow skill interface refers to a missing or incompatible output")


def check_template(template, definition):
    """Validate a complete stored closure without looking up its sources or execution environment."""
    _object(template, ("id", "name", "description", "source", "root", "workflows", "analyses", "dependencies", "templates"), "template")
    if (definition["entry"] != {"kind": "workflow.document"} or type(template["id"]) is not str or
            re.fullmatch(r"[0-9a-f]{32}", template["id"]) is None or definition["id"] != "user.s" + template["id"]):
        raise ProjectError("Workflow skill identity is invalid")
    checked_name(template["name"], "Workflow skill")
    if len(template["name"]) > 120:
        raise ProjectError("Workflow skill title must be at most 120 characters")
    if type(template["description"]) is not str or not 0 < len(template["description"]) <= 1000 or "\0" in template["description"]:
        raise ProjectError("Workflow skill description is invalid")
    _object(template["source"], ("project_id", "workflow_id", "revision", "content_sha256"), "source")
    source = template["source"]
    _id(source["project_id"])
    _id(source["workflow_id"])
    _expected_revision(source["revision"])
    if template["root"] != source["workflow_id"]:
        raise ProjectError("Workflow skill root and source do not match")
    for key, module, limit in (("workflows", workflows, workflows.MAX_WORKFLOWS),
                               ("analyses", analyses, analyses.MAX_ANALYSES)):
        entries = template[key]
        if type(entries) is not dict or len(entries) > limit:
            raise ProjectError(f"Workflow skill {key} collection exceeds its object limit")
        size = 0
        for identity, item in entries.items():
            _id(identity)
            _object(item, ("name", "document", "content_sha256"), key + " entry")
            checked_name(item["name"], "Workflow skill source")
            module._document(item["document"])
            if _digest(item["document"]) != _sha(item["content_sha256"]):
                raise ProjectError("Workflow skill source document digest does not match")
            size += len(canonical_json(item["document"]))
        if size > module.MAX_COLLECTION_BYTES:
            raise ProjectError(f"Workflow skill {key} exceed 4 MiB")
    if set(template["workflows"]) & set(template["analyses"]):
        raise ProjectError("Workflow skill source UUIDs must have one object kind")
    minimum_commands = sum(2 + len(item["document"]) for category in ("workflows", "analyses")
                           for item in template[category].values())
    if minimum_commands > 1000:
        raise ProjectError("Workflow skill instances would exceed the 1000-command project edit limit")
    if template["root"] not in template["workflows"] or \
            template["workflows"][template["root"]]["content_sha256"] != _sha(source["content_sha256"]):
        raise ProjectError("Workflow skill root digest does not match its source")
    analysis_ids, table_ids, field_ids, snapshot_ids, template_ids = _reference_inventory(template["root"], template["workflows"])
    if analysis_ids != set(template["analyses"]):
        raise ProjectError("Workflow skill analyses do not match its reference closure")
    dependencies = template["dependencies"]
    _object(dependencies, ("tables", "fields", "snapshots"), "dependencies")
    for category in dependencies.values():
        if type(category) is not dict or len(category) > MAX_DEPENDENCIES:
            raise ProjectError("Workflow skill dependency collection exceeds its limit")
        for identity in category:
            _id(identity)
    if set(dependencies["fields"]) != field_ids or set(dependencies["snapshots"]) != snapshot_ids:
        raise ProjectError("Workflow skill dependencies do not match its references")
    for field in dependencies["fields"].values():
        _object(field, ("table_id", "name", "type", "unit"), "field dependency")
        _id(field["table_id"])
        checked_name(field["name"], "Field dependency")
        if type(field["type"]) is not str or field["type"] not in FIELD_TYPES or (field["unit"] is not None and
                (type(field["unit"]) is not str or len(field["unit"]) > 256 or "\0" in field["unit"])):
            raise ProjectError("Workflow skill field type or unit is invalid")
        table_ids.add(field["table_id"])
    if set(dependencies["tables"]) != table_ids:
        raise ProjectError("Workflow skill table dependencies do not match its references")
    for table in dependencies["tables"].values():
        _object(table, ("name",), "table dependency")
        checked_name(table["name"], "Table dependency")
    for snapshot in dependencies["snapshots"].values():
        _object(snapshot, ("sha256", "files"), "snapshot dependency")
        _sha(snapshot["sha256"])
        if type(snapshot["files"]) is not list or not 1 <= len(snapshot["files"]) <= 100:
            raise ProjectError("Workflow skill snapshot file list is invalid")
        for item in snapshot["files"]:
            _object(item, ("name", "size", "sha256"), "snapshot file")
            if type(item["name"]) is not str or len(item["name"]) > 4096 or "\0" in item["name"] or \
                    type(item["size"]) is not int or not 0 <= item["size"] <= 1024**4:
                raise ProjectError("Workflow skill snapshot file metadata is invalid")
            _sha(item["sha256"])
    if (type(template["templates"]) is not list or any(type(item) is not str for item in template["templates"]) or
            len(template["templates"]) != len(set(template["templates"])) or set(template["templates"]) != template_ids):
        raise ProjectError("Workflow skill template dependencies do not match its references")
    _compiled(template)
    if len(canonical_json(template)) > MAX_TEMPLATE_BYTES:
        raise ProjectError("Workflow skill template exceeds 8 MiB")


def _read_record(db, module, identity):
    module._TABLE.require(db, "workflow skill sources")
    if db.execute("SELECT 1 FROM records WHERE id=? AND table_id=?", (identity, module.TABLE_ID)).fetchone() is None:
        raise ProjectError("Workflow skill source object is missing")
    _, compatible, error = module._TABLE.schema(db)
    record = module._record(db, identity, compatible, error)
    if record["state"] != "readable":
        raise ProjectError("Workflow skill source is unreadable: " + record["error"])
    return {"name": record["name"], "document": record["document"], "content_sha256": _digest(record["document"])}


def _snapshot(store, db, identity):
    service = store.snapshots
    service._require(db)
    size = db.execute("SELECT length(CAST(manifest AS BLOB)) FROM project_snapshots WHERE id=?", (identity,)).fetchone()
    if size is None or size[0] > 1024 * 1024:
        raise ProjectError("Workflow skill input snapshot is missing or its metadata exceeds 1 MiB")
    value = service._decode(db.execute("SELECT * FROM project_snapshots WHERE id=?", (identity,)).fetchone())
    return {"sha256": value["sha256"], "files": [{key: item[key] for key in ("name", "size", "sha256")}
                                                for item in value["manifest"]["files"]]}


def _capture(store, db, workflow_id):
    documents, pending = {}, [workflow_id]
    while pending:
        identity = pending.pop()
        if identity in documents:
            continue
        if len(documents) >= workflows.MAX_WORKFLOWS:
            raise ProjectError("Workflow skill contains too many workflows")
        documents[identity] = _read_record(db, workflows, identity)
        pending.extend(step["ref"].get("workflow") for step in documents[identity]["document"]["steps"]
                       if step["kind"] == "workflow" and set(step["ref"]) == {"workflow"})
    analysis_ids, table_ids, field_ids, snapshot_ids, template_ids = _reference_inventory(workflow_id, documents)
    if len(analysis_ids) > analyses.MAX_ANALYSES or max(len(table_ids), len(field_ids), len(snapshot_ids)) > MAX_DEPENDENCIES:
        raise ProjectError("Workflow skill source collection exceeds its object limit")
    dependencies = {"tables": {}, "fields": {}, "snapshots": {}}
    for identity in sorted(field_ids):
        row = db.execute("SELECT table_id,name,type,unit FROM fields WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise ProjectError("Workflow skill references a missing field")
        dependencies["fields"][identity] = dict(row)
        table_ids.add(row["table_id"])
    from . import skills
    for identity in sorted(table_ids):
        row = db.execute("SELECT name FROM tables WHERE id=?", (identity,)).fetchone()
        if row is None or identity in (workflows.TABLE_ID, analyses.TABLE_ID, files.TABLE_ID, skills.TABLE_ID):
            raise ProjectError("Workflow skill requires an ordinary parameter table")
        dependencies["tables"][identity] = dict(row)
    for identity in sorted(snapshot_ids):
        dependencies["snapshots"][identity] = _snapshot(store, db, identity)
    return {"root": workflow_id, "workflows": documents,
            "analyses": {identity: _read_record(db, analyses, identity) for identity in sorted(analysis_ids)},
            "dependencies": dependencies, "templates": sorted(template_ids)}


def publish_workflow(service, workflow_id, *, project_skill_id, create, name, description, expected_revision):
    from . import skills
    _id(workflow_id)
    _id(project_skill_id)
    _expected_revision(expected_revision)
    title = checked_name(name, "Workflow skill")
    if type(create) is not bool or len(title) > 120 or type(description) is not str or \
            not description.strip() or len(description) > 1000 or "\0" in description:
        raise ProjectError("Publishing requires an explicit create choice, a title up to 120 characters and a description up to 1000")
    with service.store._connect(write=True) as db:
        if db.execute("SELECT revision FROM project").fetchone()[0] != expected_revision:
            raise RevisionConflict("Project changed; review the workflow before publishing a skill")
        skills._TABLE.require(db, "project skills")
        versions = [] if create else service._current(db, project_skill_id, expected_revision)["document"]["versions"]
        if any(item["definition"]["entry"]["kind"] != "workflow.document" for item in versions):
            raise ProjectError("Publish a new workflow skill instead of replacing another skill kind")
        template_id = versions[0]["template"]["id"] if versions else project_skill_id.replace("-", "")
        skill_id = versions[0]["definition"]["id"] if versions else "user.s" + template_id
        captured = _capture(service.store, db, workflow_id)
        template = {"id": template_id, "name": title, "description": description, **captured,
                    "source": {"project_id": service.store._project_id, "workflow_id": workflow_id,
                               "revision": expected_revision,
                               "content_sha256": captured["workflows"][workflow_id]["content_sha256"]}}
        definition = {"schema": "stk.skill/1", "id": skill_id,
                      "version": 1 + max((item["definition"]["version"] for item in versions), default=0),
                      "title": {"en": title}, "summary": {"en": description}, "entry": {"kind": "workflow.document"}}
        content = {"definition": definition, "template": template}
        digest = _digest(content)
        versions.append({**content, "content_sha256": digest})
        document = skills._document({"format": skills.DOCUMENT_FORMAT, "active": digest, "versions": versions})
        return skills._TABLE.write(service.store, db, project_skill_id, {"name": title, **document}, expected_revision,
                                   create=create, document_format=skills.DOCUMENT_FORMAT)


def _bindings(store, db, dependencies, bindings):
    bindings = clone(bindings, "Workflow skill bindings")
    _object(bindings, ("tables", "fields", "snapshots"), "bindings")
    for category, values in bindings.items():
        if type(values) is not dict or set(values) != set(dependencies[category]):
            raise ProjectError("Workflow skill bindings must map every declared dependency exactly once")
        for target in values.values():
            _id(target)
    from . import skills
    for target in bindings["tables"].values():
        if target in (workflows.TABLE_ID, analyses.TABLE_ID, files.TABLE_ID, skills.TABLE_ID) or \
                db.execute("SELECT 1 FROM tables WHERE id=?", (target,)).fetchone() is None:
            raise ProjectError("Workflow skill table binding must name an existing ordinary table")
    for identity, target in bindings["fields"].items():
        source = dependencies["fields"][identity]
        field = db.execute("SELECT table_id,type,unit FROM fields WHERE id=?", (target,)).fetchone()
        if field is None or field["table_id"] != bindings["tables"][source["table_id"]] or \
                field["type"] != source["type"] or field["unit"] != source["unit"]:
            raise ProjectError("Workflow skill field binding has an incompatible table, type or unit")
    for identity, target in bindings["snapshots"].items():
        actual = _snapshot(store, db, target)
        required = [item["name"] for item in dependencies["snapshots"][identity]["files"]]
        available = [item["name"] for item in actual["files"]]
        if any(available.count(name) != required.count(name) for name in set(required)):
            raise ProjectError("Workflow skill snapshot binding must provide the declared file names without ambiguity")
    return bindings


def _create_commands(db, module, documents):
    """Preflight a managed collection and return its commands; the caller applies all collections once."""
    if not documents:
        return []
    table = module._TABLE
    table.require(db, "workflow skill instances")
    exists, compatible, error = table.schema(db)
    if not compatible:
        raise ProjectError(error)
    count = db.execute("SELECT count(*) FROM records WHERE table_id=?", (table.table_id,)).fetchone()[0]
    placeholders = ",".join("?" for _ in table.field_ids)
    total = db.execute(f"SELECT coalesce(sum(length(CAST(value AS BLOB))),0) FROM cells "
                       f"WHERE table_id=? AND field_id IN ({placeholders})", (table.table_id, *table.field_ids.values())).fetchone()[0]
    total += sum(len(_json(value).encode("utf-8")) for values in documents.values() for value in values.values())
    max_records, max_bytes, _ = table.limits()
    if count + len(documents) > max_records or total > max_bytes:
        raise ProjectError(f"{table.subject} collection exceeds {table.limit_text} of stored managed JSON")
    commands = []
    if not exists:
        commands.append({"op": "create_table", "id": table.table_id, "name": table.table_name})
    for key, (title, kind) in table.fields.items():
        row = db.execute("SELECT table_id FROM fields WHERE id=?", (table.field_ids[key],)).fetchone()
        if row is not None and row["table_id"] != table.table_id:
            raise ProjectError("Reserved managed field IDs belong to another table")
        if row is None and (not exists or any(key in values for values in documents.values())):
            commands.append({"op": "add_field", "table_id": table.table_id, "id": table.field_ids[key], "name": title, "type": kind})
    for identity, values in documents.items():
        if db.execute("SELECT 1 FROM records WHERE id=?", (identity,)).fetchone() is not None:
            raise RevisionConflict("Workflow skill instance UUID already exists")
        commands.append({"op": "add_record", "table_id": table.table_id, "id": identity})
        commands.extend({"op": "set_cell", "table_id": table.table_id, "record_id": identity,
                         "field_id": table.field_ids[key], "value": value} for key, value in values.items())
    return commands


def create_workflow(service, project_skill_id, content_sha256, *, workflow_id, name, bindings, expected_revision):
    from . import skills
    _id(project_skill_id)
    _id(workflow_id)
    _expected_revision(expected_revision)
    skills._hash(content_sha256)
    title = checked_name(name, "Workflow")
    with service.store._connect(write=True) as db:
        current = service._current(db, project_skill_id, expected_revision)
        if current["active"]["content_sha256"] != content_sha256:
            raise RevisionConflict("The active skill version changed; review it before creating a workflow")
        saved = next(item for item in current["document"]["versions"] if item["content_sha256"] == content_sha256)
        if saved["definition"]["entry"]["kind"] != "workflow.document":
            raise ProjectError("An analysis skill creates an analysis, not a workflow")
        template = saved["template"]
        bound = _bindings(service.store, db, template["dependencies"], bindings)
        mapping = {"workflows": {identity: workflow_id if identity == template["root"] else str(uuid4())
                                 for identity in template["workflows"]},
                   "analyses": {identity: str(uuid4()) for identity in template["analyses"]}}
        provenance = {"id": project_skill_id, "ref": current["active"]["ref"], "content_sha256": content_sha256}
        instances = {"workflows": {}, "analyses": {}}
        for identity, source in template["analyses"].items():
            doc = deepcopy(source["document"])
            doc["graph"].setdefault("ui", {})["project_skill"] = provenance
            instances["analyses"][mapping["analyses"][identity]] = {"name": source["name"], **analyses._document(doc)}
        for identity, source in template["workflows"].items():
            doc = deepcopy(source["document"])
            for step in doc["steps"]:
                kind, ref = step["kind"], step["ref"]
                if kind == "workflow":
                    ref["workflow"] = mapping["workflows"][ref["workflow"]]
                elif kind == "analysis":
                    ref["analysis"] = mapping["analyses"][ref["analysis"]]
                elif kind == "table":
                    ref["table"] = bound["tables"][ref["table"]]
                elif kind == "files":
                    ref["snapshot"] = bound["snapshots"][ref["snapshot"]]
                for value in step.get("parameters", {}).values():
                    if type(value) is dict and set(value) == {"$field"}:
                        value["$field"] = bound["fields"][value["$field"]]
            doc["ui"]["project_skill"] = provenance
            instances["workflows"][mapping["workflows"][identity]] = {
                "name": title if identity == template["root"] else source["name"], **workflows._document(doc)}
        commands = _create_commands(db, analyses, instances["analyses"])
        commands += _create_commands(db, workflows, instances["workflows"])
        result = service.store._apply(db, service.store._prepare_commands(commands, expected_revision), expected_revision)
        snapshot_limit(service.store, db, "Workflow skill instance")
        return {**result, "table_id": workflows.TABLE_ID, "record_id": workflow_id}
