"""Sphere points and genuine bond/box segments using the existing payload/2 primitives."""
from suan.graph.registry import NodeExecutionError, Port, json_param, node, number, string
from suan.graph.nodes.render import COLOR_SPEC


def _base(ctx, dataset):
    from suan.render.layers import Attribute
    props = {"length_unit": dataset.length_unit}
    if dataset.time and dataset.time.step is not None:
        props["time"] = {"step": dataset.time.step, "time": None}
    # No grid or pick.probe descriptor: the volume interpolation API cannot sample molecules.
    return {"id": ctx.node_id, "node": ctx.node_id, "name": dataset.label or dataset.id,
            "props": props, "attributes": {name: Attribute.from_field(field, field.values)
                                           for name, field in dataset.fields.items()}}


@node("stk.render.molecule_atoms", title={"en": "Molecular atoms", "zh": "分子原子"},
      description={"en": "Sphere points retaining atom ID, molecule ID, type, charge and original position attributes; no field probe."},
      inputs=[Port("in", "dataset", accepts=["points"])], outputs=[Port("layer", "layer")],
      params={"radius": number(0.3, exclusive_minimum=0, maximum=10, stage="client"),
              "color": json_param(COLOR_SPEC, {"by": "field", "field": "atom_type"}, stage="client"),
              "opacity": number(1.0, minimum=0, maximum=1, stage="client"),
              "name": string(None, nullable=True, stage="client")}, stage="representation")
def atoms_layer(ctx, inputs, params):
    from suan.render.layers import Layer
    data = inputs["in"]
    if "atom_id" not in data.fields or "atom_type" not in data.fields:
        raise NodeExecutionError("Molecular atoms require original atom_id and atom_type fields", code="invalid_input")
    base = _base(ctx, data)
    base["props"]["default_color"] = {"by": "field", "field": "atom_type"}
    return Layer("points", geometry={"positions": data.points}, appearance={"render_as": "spheres"}, **base)


@node("stk.render.molecule_lines", title={"en": "Molecular lines", "zh": "分子线段"},
      description={"en": "Render explicit two-point topology bonds or cell edges as lines, without inferring connectivity."},
      inputs=[Port("in", "dataset", accepts=["polydata"])], outputs=[Port("layer", "layer")],
      params={"width_px": number(1.5, minimum=0, maximum=32, stage="client"),
              "color": json_param(COLOR_SPEC, {"by": "solid", "solid": [0.35, 0.35, 0.35]}, stage="client"),
              "opacity": number(1.0, minimum=0, maximum=1, stage="client"),
              "name": string(None, nullable=True, stage="client")}, stage="representation")
def lines_layer(ctx, inputs, params):
    import numpy as np
    from suan.render.layers import Layer
    data = inputs["in"]
    if data.polys.n_cells or data.verts.n_cells or np.any(np.diff(data.lines.offsets) != 2):
        raise NodeExecutionError("Molecular lines require explicit two-point segments", code="invalid_input")
    return Layer("lines", geometry={"positions": data.points,
                 "indices": data.lines.connectivity.reshape(-1, 2)}, **_base(ctx, data))


__all__ = ["atoms_layer", "lines_layer"]
