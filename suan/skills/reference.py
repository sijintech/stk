"""Generate ``stk-visualize/reference/nodes.md`` from an ``stk.catalog/1`` document (standard library only).

``python -m suan.skills.reference`` prints the reference of the installed
catalog; ``--spec`` uses the frozen Milestone-1 spec catalog of a source
checkout (the version committed in the package), ``--output PATH`` writes it.
"""
import argparse
import json
from pathlib import Path
import sys

__all__ = ["nodes_markdown"]

FAMILIES = ("source", "filter", "analysis", "render", "view", "output", "plot")
FAMILY_TEXT = {
    "source": "read data through connectors; a `binding` names the run, `path` is relative inside it",
    "filter": "transform datasets (data-stage params re-run them)",
    "analysis": "derive labels, fractions and statistics",
    "render": "turn data into draw layers; appearance params are client-stage",
    "view": "camera and scene assembly",
    "output": "deliverables: payload, image, dataset export",
    "plot": "stk.plot/1 figures (matplotlib), delivered as SVG/PNG plus the plotted data",
}


def _short(value, limit=48):
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _type_text(schema):
    if not isinstance(schema, dict):
        return "any"
    if "const" in schema:
        return _short(schema["const"])
    if "enum" in schema:
        return " \\| ".join(_short(v, 24) for v in schema["enum"])
    for key in ("anyOf", "oneOf"):
        if key in schema:
            return " \\| ".join(dict.fromkeys(_type_text(branch) for branch in schema[key]))
    kind = schema.get("type")
    if isinstance(kind, list):
        return " \\| ".join(kind)
    if kind == "array":
        if "prefixItems" in schema:
            return "[" + ", ".join(_type_text(item) for item in schema["prefixItems"]) + "]"
        items = schema.get("items")
        size = ""
        if schema.get("minItems") is not None and schema.get("minItems") == schema.get("maxItems"):
            size = f"[{schema['minItems']}]"
        return f"array{size} of {_type_text(items)}" if items else "array"
    if kind == "object":
        properties = schema.get("properties")
        return "object {" + ", ".join(properties) + "}" if properties else "object"
    if kind in ("number", "integer"):
        bounds = []
        if "minimum" in schema:
            bounds.append(f"≥{schema['minimum']}")
        if "exclusiveMinimum" in schema:
            bounds.append(f">{schema['exclusiveMinimum']}")
        if "maximum" in schema:
            bounds.append(f"≤{schema['maximum']}")
        return kind + (f" ({', '.join(bounds)})" if bounds else "")
    return kind or "any"


def _port(port):
    kinds = port.get("accepts") or port.get("kinds")
    kind = port["type"] if isinstance(port["type"], str) else " | ".join(port["type"])
    extra = []
    if kinds:
        extra.append("kinds " + ", ".join(kinds))
    if port.get("multi"):
        extra.append("multi")
    if port.get("required") is False:
        extra.append("optional")
    return f"`{port['name']}` ({kind}{'; ' + '; '.join(extra) if extra else ''})"


def _text(value):
    if isinstance(value, dict):
        value = value.get("en") or next(iter(value.values()), "")
    return " ".join(str(value or "").split())


def nodes_markdown(catalog):
    """Markdown reference of every node type in ``catalog`` (deterministic)."""
    nodes = sorted(catalog.get("nodes") or (), key=lambda n: (FAMILIES.index(n["id"].split(".")[1])
                                                               if n["id"].split(".")[1] in FAMILIES else 99, n["id"]))
    lines = ["# STK graph node reference", "",
             "Generated from the node catalog (`stk.catalog/1`) by `python -m suan.skills.reference`; "
             "`suan skills export` regenerates it from the installed catalog. Do not edit by hand.", "",
             "Conventions: links are written on the input side as `{\"from\": \"<node>.<port>\"}` (a list for multi "
             "ports); a param may be `{\"$param\": \"<graph parameter>\"}`. Stage `data` params re-run the node and "
             "everything downstream; stage `client` params only change appearance. Units are never guessed: "
             "`unspecified` means unknown, `1` means dimensionless. Label values: -1 = unclassified / no data, "
             "0 = substrate.", ""]
    families = []
    for node in nodes:
        family = node["id"].split(".")[1]
        if family not in families:
            families.append(family)
    lines += ["## Families", ""]
    for family in families:
        members = [n["id"] for n in nodes if n["id"].split(".")[1] == family]
        lines.append(f"- **{family}** — {FAMILY_TEXT.get(family, 'nodes')}: " + ", ".join(f"`{m}`" for m in members))
    lines.append("")
    for node in nodes:
        title = _text(node.get("title"))
        lines += [f"## `{node['id']}`" + (f" — {title}" if title else ""), ""]
        description = _text(node.get("description"))
        if description:
            lines += [description, ""]
        if node.get("stretch"):
            lines += ["*Stretch goal: may be absent from an install.*", ""]
        inputs = node.get("inputs") or []
        outputs = node.get("outputs") or []
        lines.append("- Inputs: " + (", ".join(_port(p) for p in inputs) if inputs else "none"))
        lines.append("- Outputs: " + (", ".join(_port(p) for p in outputs) if outputs else "none"))
        params = (node.get("params") or {}).get("properties") or {}
        required = set((node.get("params") or {}).get("required") or ())
        if params:
            lines += ["", "| param | type | default | stage | notes |", "|---|---|---|---|---|"]
            for name, schema in params.items():
                default = "**required**" if name in required else (_short(schema["default"]) if "default" in schema
                                                                    else "")
                notes = [_text(schema.get("title"))] if schema.get("title") else []
                if schema.get("x-stk-widget") in ("binding", "path", "field", "step"):
                    notes.append(f"{schema['x-stk-widget']}")
                cell = lambda text: str(text).replace("|", "\\|")  # noqa: E731
                lines.append(f"| `{name}` | {_type_text(schema)} | {cell(default)} | "
                             f"{schema.get('x-stk-stage', 'data')} | {cell('; '.join(notes))} |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _spec_catalog():
    path = Path(__file__).resolve().parents[2] / "docs" / "specs" / "catalog" / "stk-catalog-m1.json"
    if not path.is_file():
        raise SystemExit("The spec catalog is only available in a source checkout (docs/specs/catalog)")
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m suan.skills.reference", description=__doc__.splitlines()[0])
    parser.add_argument("--spec", action="store_true", help="use docs/specs/catalog/stk-catalog-m1.json")
    parser.add_argument("--output", type=Path, help="write to this file instead of standard output")
    args = parser.parse_args(argv)
    if args.spec:
        catalog = _spec_catalog()
    else:
        from suan.graph.catalog import catalog_document
        catalog = catalog_document()
    text = nodes_markdown(catalog)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.buffer.write(text.encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
