"""View nodes ``stk.view.camera@1`` and ``stk.view.scene@1`` (docs/specs/stk-graph-v1.md §7, §14).

A camera is the ``camera`` object of ``stk.view/1`` (physical float64
coordinates). The scene orders its layers in link order, resolves a camera
preset against the layer bounds (focal point = centre, distance =
r / sin(θ/2) / zoom) and chooses the render origin. Declarations are copied
from docs/specs/catalog/m1_nodes.py (frozen).
"""
from suan.graph.registry import (
    NodeExecutionError, Port, color, enum, integer, json_param, node, number, string, vector3,
)


def _nullable_string(**kw):
    return string(None, nullable=True, **kw)


@node("stk.view.camera", title={"en": "Camera", "zh": "相机"},
      description={"en": "A preset (fit to the scene bounds) or a numeric camera in physical coordinates."},
      outputs=[Port("camera", "camera")],
      params={
          "preset": enum(["iso", "+x", "-x", "+y", "-y", "+z", "-z", None], "iso"),
          "position": vector3(None, nullable=True),
          "focal_point": vector3(None, nullable=True),
          "view_up": vector3(None, nullable=True),
          "projection": enum(["perspective", "parallel"], "perspective"),
          "view_angle_deg": number(30.0, exclusive_minimum=0, exclusive_maximum=180),
          "zoom": number(1.0, exclusive_minimum=0),
          "parallel_scale": number(None, nullable=True, exclusive_minimum=0),
      })
def camera(ctx, inputs, params):
    if params.get("focal_point") is not None and params.get("position") is None:
        raise NodeExecutionError("A numeric camera needs 'position' (the focal point alone is not enough)",
                                 code="invalid_param", hint="set 'position' or use a preset")
    result = {"projection": params["projection"], "preset": params["preset"],
              "view_angle_deg": float(params["view_angle_deg"]), "zoom": float(params["zoom"])}
    for key in ("position", "focal_point", "view_up", "parallel_scale"):
        if params.get(key) is not None:
            result[key] = params[key]
    if result.get("position") is not None:
        result["preset"] = None
    return result


def _unique_ids(layers):
    seen, result = {}, []
    for layer in layers:
        layer_id = layer.id
        if layer_id in seen:
            seen[layer_id] += 1
            layer = layer.copy(id=f"{layer_id}_{seen[layer_id]}")
        else:
            seen[layer_id] = 0
        result.append(layer)
    return result


def resolve_camera(spec, bounds):
    """Numeric ``stk.view/1`` camera from a camera value (presets fit ``bounds``)."""
    from suan.render.layers import default_view_up, fit_camera
    spec = dict(spec or {"preset": "iso"})
    angle = float(spec.get("view_angle_deg", 30.0))
    zoom = float(spec.get("zoom", 1.0))
    projection = spec.get("projection", "perspective")
    if spec.get("position") is not None:
        position = [float(v) for v in spec["position"]]
        if spec.get("focal_point") is not None:
            focal = [float(v) for v in spec["focal_point"]]
        else:
            lo, hi = bounds if bounds else ([0.0] * 3, [0.0] * 3)
            focal = [(a + b) / 2 for a, b in zip(lo, hi)]
        if position == focal:
            raise NodeExecutionError("Camera position equals the focal point", code="invalid_param")
        camera = {"projection": projection, "position": position, "focal_point": focal,
                  "view_up": [float(v) for v in spec.get("view_up") or default_view_up(position, focal)],
                  "view_angle_deg": angle}
        if zoom != 1.0:
            camera["zoom"] = zoom
        if spec.get("parallel_scale") is not None:
            camera["parallel_scale"] = float(spec["parallel_scale"])
        elif projection == "parallel" and bounds:
            import math
            camera["parallel_scale"] = math.dist(bounds[0], bounds[1]) / 2 / zoom or 1.0
        return camera
    camera = fit_camera(bounds, spec.get("preset") or "iso", view_angle_deg=angle, zoom=zoom,
                        projection=projection)
    if spec.get("view_up") is not None:
        camera["view_up"] = [float(v) for v in spec["view_up"]]
    if spec.get("parallel_scale") is not None:
        camera["parallel_scale"] = float(spec["parallel_scale"])
    return camera


@node("stk.view.scene", title={"en": "Scene", "zh": "场景"},
      description={"en": "Ordered layers plus the view (camera, viewport, background, lighting)."},
      inputs=[Port("layers", "layer", multi=True), Port("camera", "camera", required=False)],
      outputs=[Port("scene", "scene")],
      params={
          "background": color([1.0, 1.0, 1.0]),
          "lighting": enum(["three_point", "headlight", "none"], "three_point"),
          "width": integer(1600, minimum=16, maximum=16384),
          "height": integer(1200, minimum=16, maximum=16384),
          "render_origin": json_param({"anyOf": [{"const": "auto"},
                                                 {"type": "array", "items": {"type": "number"}, "minItems": 3,
                                                  "maxItems": 3}]}, "auto"),
          "title": _nullable_string(),
      })
def scene(ctx, inputs, params):
    from suan.render.layers import Layer, Scene, union_bounds
    layers = inputs.get("layers") or []
    if not isinstance(layers, (list, tuple)):
        layers = [layers]
    for layer in layers:
        if not isinstance(layer, Layer):
            raise NodeExecutionError(f"Scene inputs must be render layers, got {type(layer).__name__}",
                                     code="kind_mismatch")
    layers = _unique_ids(layers)
    bounds = union_bounds([layer.bounds() for layer in layers if layer.is_3d])
    grid = next((layer.grid for layer in layers if layer.grid is not None), None)
    if params["render_origin"] == "auto":
        box = grid["bounds"] if grid is not None else bounds
        render_origin = [(a + b) / 2 for a, b in zip(*box)] if box else [0.0, 0.0, 0.0]
    else:
        render_origin = [float(v) for v in params["render_origin"]]
    units = {layer.props.get("length_unit") for layer in layers if layer.is_3d and layer.props.get("length_unit")}
    if len(units) > 1:
        ctx.warn(f"Layers use different length units ({', '.join(sorted(units))}); coordinates are not converted",
                 code="mixed_length_units")
    length_unit = next((layer.props["length_unit"] for layer in layers
                        if layer.is_3d and layer.props.get("length_unit")), "unspecified")
    camera = resolve_camera(inputs.get("camera"), bounds)
    if grid is not None and grid.get("frame"):
        camera["frame"] = grid["frame"]
    title = params.get("title")
    if title:
        layers.append(Layer("overlay", id=f"{getattr(ctx, 'node_id', 'scene')}_title",
                            props={"kind": "text", "text": title, "anchor": "top", "offset_px": [0, 12],
                                   "font_size_px": 18}))
    view = {"schema": "stk.view/1", "camera": camera,
            "viewport": {"width": params["width"], "height": params["height"], "magnification": 1,
                         "lock_aspect": True},
            "background": {"type": "solid", "color": [float(c) for c in params["background"]]},
            "lighting": {"preset": params["lighting"], "intensity": 1.0},
            "visibility": {layer.id: bool(layer.visible) for layer in layers}}
    time = next((layer.props["time"] for layer in layers if layer.props.get("time")), None)
    if time is not None:
        view["time"] = {"step": time.get("step"), "time": time.get("time")}
    return Scene(layers=layers, view=view, render_origin=tuple(render_origin), length_unit=length_unit,
                 time=time, grid=grid, title=title)
