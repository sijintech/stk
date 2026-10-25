"""Project-owned skill versions, independent of the installed catalog on read/recovery.

Each binding keeps bounded, hash-checked definition/template snapshots and an explicit active
digest. Writes use the ordinary project transaction and undo journal. These are method definitions,
not executable environments: creating an analysis copies a draft and never starts a run.
"""
import hashlib
import re
from uuid import NAMESPACE_URL, uuid5

from suan.graph.schema import check_value
from suan.skills.catalog import DEFINITION_SCHEMA, _canonical

from . import analyses
from .managed import ManagedTable, clone, name
from .store import ProjectError, RevisionConflict, UnsupportedProjectFormat, _expected_revision, _id


DOCUMENT_FORMAT = "stk.project-skill/1"
TABLE_ID = str(uuid5(NAMESPACE_URL, "urn:stk:project:skills:1"))
FIELDS = {"name": ("Name", "text"), "format": ("Format", "text"),
          "active": ("Active content", "text"), "versions": ("Saved versions", "json")}
FIELD_IDS = {key: str(uuid5(NAMESPACE_URL, "urn:stk:project:skills:1:" + key)) for key in FIELDS}
MAX_VERSIONS = 16
MAX_DOCUMENT_BYTES = 384 * 1024
MAX_SKILLS = 128
MAX_COLLECTION_BYTES = 4 * 1024 * 1024


class ProjectSkillNotFound(ProjectError):
    """No project skill with this UUID exists in the managed table."""


_TABLE = ManagedTable(table_id=TABLE_ID, table_name="Project skills", fields=FIELDS, field_ids=FIELD_IDS,
                      subject="Project skill", not_found=ProjectSkillNotFound,
                      limits=lambda: (MAX_SKILLS, MAX_COLLECTION_BYTES, 12 * 1024 * 1024),
                      limit_text="128 records or 4 MiB", max_cell_bytes=2 * MAX_DOCUMENT_BYTES)


def _hash(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ProjectError("Skill content digest must be a lowercase SHA-256")
    return value


def _snapshot(value):
    if type(value) is not dict or set(value) != {"definition", "template", "content_sha256"}:
        raise ProjectError("Saved skill requires definition, template and content_sha256")
    definition, template = value["definition"], value["template"]
    if check_value(definition, DEFINITION_SCHEMA):
        raise ProjectError("Saved skill definition is invalid")
    if (definition["entry"].get("kind") != "graph.preset" or type(template) is not dict or
            set(template) != {"id", "name", "description", "bindings", "graph"} or
            template["id"] != definition["entry"].get("preset")):
        raise ProjectError("Saved skill must contain its complete graph preset")
    if (any(type(template[key]) is not str or len(template[key]) > 4096 for key in ("name", "description")) or
            type(template["bindings"]) is not list or len(template["bindings"]) > 32):
        raise ProjectError("Saved skill preset metadata is invalid")
    bindings = set()
    for binding in template["bindings"]:
        if (type(binding) is not dict or set(binding) != {"name", "description"} or
                type(binding["name"]) is not str or not 0 < len(binding["name"]) <= 64 or
                type(binding["description"]) is not str or len(binding["description"]) > 4096 or
                binding["name"] in bindings):
            raise ProjectError("Saved skill binding declarations are invalid")
        bindings.add(binding["name"])
    # Only the shipped structural schema: no registry, optional dependency or original preset read.
    analyses._document({"format": analyses.DOCUMENT_FORMAT, "graph": template["graph"],
                        "parameters": {}, "outputs": []})
    content = {"definition": definition, "template": template}
    if hashlib.sha256(_canonical(content).encode("utf-8")).hexdigest() != _hash(value["content_sha256"]):
        raise ProjectError("Saved skill content digest does not match its definition and template")
    return value


def _document(value):
    value = clone(value, "Project skill")
    if type(value) is not dict or set(value) != {"format", "active", "versions"}:
        raise ProjectError("Project skill requires exactly format, active and versions")
    if value["format"] != DOCUMENT_FORMAT:
        raise UnsupportedProjectFormat("Unsupported project skill format")
    versions = value["versions"]
    if type(versions) is not list or not 1 <= len(versions) <= MAX_VERSIONS:
        raise ProjectError("Project skill must keep between 1 and 16 versions")
    skill_id, numbers, digests = None, set(), set()
    for item in versions:
        _snapshot(item)
        definition = item["definition"]
        if skill_id is not None and definition["id"] != skill_id:
            raise ProjectError("Saved versions must belong to the same skill")
        skill_id = definition["id"]
        if definition["version"] in numbers or item["content_sha256"] in digests:
            raise ProjectError("Saved skill versions must have unique versions and digests")
        numbers.add(definition["version"])
        digests.add(item["content_sha256"])
    if _hash(value["active"]) not in digests:
        raise ProjectError("Active skill version is not saved in this project")
    if len(_canonical(value).encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise ProjectError("Project skill document exceeds 384 KiB")
    return value


def _summary(item):
    definition = item["definition"]
    return {"skill_id": definition["id"], "version": definition["version"],
            "ref": f"{definition['id']}@{definition['version']}", "title": definition["title"],
            "content_sha256": item["content_sha256"]}


def _record(db, identity, compatible, error):
    result = {"id": identity, "name": None, "format": None, "state": "invalid", "error": "",
              "active": None, "versions": [], "document": None}
    try:
        result["name"] = name(_TABLE.literal(db, identity, "name"), "Project skill")
        format_value = _TABLE.literal(db, identity, "format")
        result["format"] = format_value if type(format_value) is str and len(format_value) <= 128 else None
        if not compatible:
            raise ProjectError(error)
        if _TABLE.indirect(db, identity):
            raise ProjectError("Project skill cells must be literals; undo or repair the edit")
        if result["format"] != DOCUMENT_FORMAT:
            result["format"] = result["format"] if type(result["format"]) is str else None
            result["state"] = "unsupported"
            raise ProjectError("Unsupported project skill format")
        document = _document({"format": result["format"],
                              **{key: _TABLE.literal(db, identity, key) for key in ("active", "versions")}})
        result["document"] = document
        result["versions"] = [_summary(item) for item in document["versions"]]
        result["active"] = next(item for item in result["versions"] if item["content_sha256"] == document["active"])
        result["state"] = "readable"
    except ProjectError as exc:
        result["error"] = str(exc)
    return result


class ProjectSkills:
    def __init__(self, store):
        self.store = store

    def _read(self, db, identity):
        _TABLE.require(db, "project skills")
        if db.execute("SELECT 1 FROM records WHERE table_id=? AND id=?", (TABLE_ID, identity)).fetchone() is None:
            raise ProjectSkillNotFound("Project skill not found")
        _, compatible, error = _TABLE.schema(db)
        return _record(db, identity, compatible, error)

    def list(self, *, offset=0, limit=50):
        if type(offset) is not int or not 0 <= offset < 2**63 or type(limit) is not int or not 1 <= limit <= 100:
            raise ProjectError("Project skill pagination requires offset >= 0 and limit between 1 and 100")
        with self.store._connect() as db:
            _TABLE.require(db, "project skills")
            _, compatible, error = _TABLE.schema(db)
            items = []
            for row in db.execute("SELECT id FROM records WHERE table_id=? ORDER BY rowid LIMIT ? OFFSET ?",
                                  (TABLE_ID, limit, offset)):
                item = _record(db, row[0], compatible, error)
                del item["document"]
                items.append(item)
            return {"revision": db.execute("SELECT revision FROM project").fetchone()[0], "table_id": TABLE_ID,
                    "compatible": compatible, "error": error, "offset": offset,
                    "total": db.execute("SELECT count(*) FROM records WHERE table_id=?", (TABLE_ID,)).fetchone()[0],
                    "skills": items}

    def get(self, project_skill_id):
        _id(project_skill_id)
        with self.store._connect() as db:
            return {"revision": db.execute("SELECT revision FROM project").fetchone()[0],
                    "table_id": TABLE_ID, "skill": self._read(db, project_skill_id)}

    @staticmethod
    def _capture(skill_id, version, content_sha256):
        from suan.skills.catalog import SkillCatalogError, load_catalog
        _hash(content_sha256)
        if type(version) is not int or version < 1:
            raise ProjectError("Pinning a skill requires an explicit positive version")
        try:
            content = load_catalog().freeze(skill_id, version, content_sha256)
        except SkillCatalogError as exc:
            if exc.code == "conflict":
                raise RevisionConflict(str(exc)) from None
            raise ProjectError(str(exc)) from None
        return {**content, "content_sha256": content_sha256}

    def pin(self, skill_id, version, content_sha256, *, project_skill_id, expected_revision):
        _id(project_skill_id)
        _expected_revision(expected_revision)
        item = self._capture(skill_id, version, content_sha256)
        document = _document({"format": DOCUMENT_FORMAT, "active": content_sha256, "versions": [item]})
        with self.store._connect(write=True) as db:
            _TABLE.require(db, "project skills")
            return _TABLE.write(self.store, db, project_skill_id,
                                {"name": item["definition"]["title"]["en"], **document}, expected_revision,
                                create=True, document_format=DOCUMENT_FORMAT)

    def _current(self, db, identity, revision):
        if db.execute("SELECT revision FROM project").fetchone()[0] != revision:
            raise RevisionConflict("Project changed; refresh the saved skill before editing")
        item = self._read(db, identity)
        if item["state"] != "readable":
            raise ProjectError(item["error"])
        return item

    def upgrade(self, project_skill_id, version, content_sha256, *, expected_revision):
        _id(project_skill_id)
        _expected_revision(expected_revision)
        # Resolve outside the write lock, then check the same revision again inside the transaction.
        before = self.get(project_skill_id)
        if before["revision"] != expected_revision:
            raise RevisionConflict("Project changed; refresh the saved skill before upgrading")
        if before["skill"]["state"] != "readable":
            raise ProjectError(before["skill"]["error"])
        item = self._capture(before["skill"]["active"]["skill_id"], version, content_sha256)
        with self.store._connect(write=True) as db:
            current = self._current(db, project_skill_id, expected_revision)
            document = current["document"]
            if version <= max(entry["definition"]["version"] for entry in document["versions"]):
                raise ProjectError("Upgrade requires a newer version; restore an already saved version explicitly")
            document["versions"].append(item)
            document["active"] = content_sha256
            document = _document(document)
            return _TABLE.write(self.store, db, project_skill_id, {"name": current["name"], **document},
                                expected_revision, create=False, document_format=DOCUMENT_FORMAT)

    def restore(self, project_skill_id, content_sha256, *, expected_revision):
        _id(project_skill_id)
        _expected_revision(expected_revision)
        _hash(content_sha256)
        with self.store._connect(write=True) as db:
            current = self._current(db, project_skill_id, expected_revision)
            document = current["document"]
            document["active"] = content_sha256
            document = _document(document)
            return _TABLE.write(self.store, db, project_skill_id, {"name": current["name"], **document},
                                expected_revision, create=False, document_format=DOCUMENT_FORMAT)

    def create_analysis(self, project_skill_id, content_sha256, *, analysis_id, name, expected_revision):
        """Copy the reviewed active version to a saved analysis, with durable provenance in graph UI."""
        _id(project_skill_id)
        _id(analysis_id)
        _expected_revision(expected_revision)
        _hash(content_sha256)
        title = analyses._name(name)
        with self.store._connect(write=True) as db:
            current = self._current(db, project_skill_id, expected_revision)
            if current["active"]["content_sha256"] != content_sha256:
                raise RevisionConflict("The active skill version changed; review it before creating an analysis")
            saved = next(item for item in current["document"]["versions"] if item["content_sha256"] == content_sha256)
            graph = saved["template"]["graph"]
            graph.setdefault("ui", {})["project_skill"] = {"id": project_skill_id, "ref": current["active"]["ref"],
                                                           "content_sha256": content_sha256}
            document = analyses._document({"format": analyses.DOCUMENT_FORMAT, "graph": graph,
                                           "parameters": {}, "outputs": list(graph["outputs"])})
            return analyses._TABLE.write(self.store, db, analysis_id, {"name": title, **document}, expected_revision,
                                         create=True, document_format=analyses.DOCUMENT_FORMAT)
