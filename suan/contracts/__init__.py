"""STK contracts: JSON Schemas (draft 2020-12) and the quantity vocabulary.

The schema files under ``schemas/`` are the published contract shared by Python,
the web client, Blender and LLM tools. This module only loads them; it uses the
standard library alone so the hub, the Windows client and MCP servers can import
it without NumPy. Python-side validation is hand-written where it matters
(``suan.graph.schema.validate_graph``); ``jsonschema`` is not a dependency.

Schema ids are the file stems (``"graph-1"``); document tags (``"stk.graph/1"``)
and URNs (``"urn:stk:schema:graph-1"``, the schemas' ``$id``) are accepted too.
Cross-file references use those URNs.
"""
from copy import deepcopy
from functools import lru_cache
from importlib.resources import files
import json

__all__ = [
    "DOCUMENT_SCHEMAS", "SCHEMA_IDS", "UNIT_TOKENS", "URN_PREFIX",
    "list_schemas", "load_all_schemas", "load_quantities", "load_schema", "quantity_info", "schema_id",
]

URN_PREFIX = "urn:stk:schema:"
SCHEMA_IDS = ("case-1", "dataset-1", "desktop-bridge-1", "event-1", "field-1", "graph-1", "node-type-1",
              "payload-2", "plot-1", "ref-1", "result-1", "view-1")
# Document "schema" tags and the schema file that describes them.
DOCUMENT_SCHEMAS = {
    "stk.case/1": "case-1", "stk.catalog/1": "node-type-1", "stk.dataset/1": "dataset-1", "stk.graph/1": "graph-1",
    "stk.payload/2": "payload-2", "stk.plot/1": "plot-1", "stk.result/1": "result-1", "stk.view/1": "view-1",
}
# Reserved unit tokens; every other unit string is a UCUM case-sensitive code.
UNIT_TOKENS = ("unspecified", "1", "normalized", "grid_index")


def _strict_json(text, origin):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"{origin}: duplicate JSON key {key!r}")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=pairs)


def _resource(*parts):
    return files(__name__).joinpath(*parts)


def schema_id(name):
    """Normalize ``graph-1``, ``graph-1.schema.json``, ``stk.graph/1`` or a URN to ``graph-1``."""
    if not isinstance(name, str):
        raise TypeError("Schema id must be a string")
    key = DOCUMENT_SCHEMAS.get(name, name)
    if key.startswith(URN_PREFIX):
        key = key[len(URN_PREFIX):]
    if key.endswith(".schema.json"):
        key = key[:-len(".schema.json")]
    if key not in list_schemas():
        raise KeyError(f"Unknown STK schema {name!r}; known: {', '.join(list_schemas())}")
    return key


@lru_cache(maxsize=None)
def list_schemas():
    """Schema ids shipped in this package, sorted (a tuple)."""
    return tuple(sorted(entry.name[:-len(".schema.json")] for entry in _resource("schemas").iterdir()
                        if entry.name.endswith(".schema.json")))


@lru_cache(maxsize=None)
def _schema(key):
    schema = _strict_json(_resource("schemas", key + ".schema.json").read_text(encoding="utf-8"), key)
    if schema.get("$id") != URN_PREFIX + key:
        raise ValueError(f"Schema {key} must declare $id {URN_PREFIX + key}")
    return schema


def load_schema(name):
    """Return a fresh copy of one schema (see :func:`schema_id` for accepted names)."""
    return deepcopy(_schema(schema_id(name)))


def load_all_schemas():
    """Return ``{$id: schema}`` for every shipped schema (for a jsonschema referencing registry)."""
    return {URN_PREFIX + key: deepcopy(_schema(key)) for key in list_schemas()}


@lru_cache(maxsize=None)
def _quantities():
    return _strict_json(_resource("quantities.json").read_text(encoding="utf-8"), "quantities.json")


def load_quantities():
    """Return a fresh copy of the whole quantity vocabulary document."""
    return deepcopy(_quantities())


def quantity_info(name, tensor=None):
    """Display defaults for a quantity id, with every key filled in.

    Plain ids must be in the vocabulary (``KeyError`` otherwise). Namespaced
    extensions (``"mupro:landau_force"``) and ``None`` fall back to the
    vocabulary defaults, resolved for ``tensor`` when given.
    """
    document = _quantities()
    defaults = document["defaults"]
    if name is not None and ":" not in name:
        entry = document["quantities"][name]
        return {"id": name, "known": True, "component_names": None, **deepcopy(entry)}
    tensor = tensor or "scalar"
    return {
        "id": name, "known": False, "label": dict(defaults["label"]), "dimension": None, "si_unit": None,
        "tensor": None, "components": None, "component_names": None,
        "representation": defaults["representation"].get(tensor, "slice"), "colormap": defaults["colormap"],
        "range": defaults["range"], "categorical": tensor == "label",
        "default_graph": defaults["default_graph"].get(tensor, "slice"),
    }
