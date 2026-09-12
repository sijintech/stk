"""Validate the wire scene before handing untrusted numeric arrays to native code."""
import math


def validate_scene(scene):
    m, mesh = scene["manifest"], scene["mesh"]
    if m["version"] != 1 or m.get("association", "point") != "point":
        raise ValueError("Unsupported scientific scene version or association")
    for key in ("origin", "render_origin", "spacing", "dimensions"):
        if len(m[key]) != 3 or not all(isinstance(v, (float, int)) and math.isfinite(v) for v in m[key]):
            raise ValueError("Invalid spatial metadata")
    if any(n < 1 or int(n) != n for n in m["dimensions"]) or min(m["spacing"]) <= 0:
        raise ValueError("Invalid grid dimensions/spacing")
    if len(m["value_range"]) != 2 or not all(math.isfinite(v) for v in m["value_range"]) or m["value_range"][1] < m["value_range"][0]:
        raise ValueError("Invalid scalar range")
    if len(mesh["positions"]) > 80000 or len(mesh["values"]) != len(mesh["positions"]):
        raise ValueError("Invalid point count")
    if len(mesh["indices"]) % 3 or len(mesh["indices"]) > 480000:
        raise ValueError("Invalid triangle count")
    for p in mesh["positions"]:
        if len(p) != 3 or not all(math.isfinite(v) and abs(v) < 1e30 for v in p):
            raise ValueError("Invalid render coordinates")
    if not all(math.isfinite(v) for v in mesh["values"]):
        raise ValueError("Invalid scalar samples")
    if any(isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < len(mesh["positions"]) for i in mesh["indices"]):
        raise ValueError("Triangle index outside point array")
    return scene


def demo_scene():
    positions, values, indices = [], [], []
    n = 32
    for y in range(n):
        for x in range(n):
            a, b = x/(n-1)*2-1, y/(n-1)*2-1
            z = math.sin(a*3)*math.cos(b*3)*.3
            positions.append([a+1,b+1,z+.3])
            values.append(z)
            if x+1 < n and y+1 < n:
                i = y*n+x
                indices.extend([i,i+1,i+n,i+1,i+n+1,i+n])
    return {"manifest": {"version": 1, "association": "point", "dataset_id": "local-demo",
        "field": "演示曲面（非计算结果）", "dimensions": [n,n,2], "origin": [0,0,0],
        "render_origin": [0,0,0], "spacing": [2/(n-1),2/(n-1),.6], "value_range": [-.3,.3],
        "units": "演示", "coordinate_units": "演示", "timestep": 0, "mode": "demo",
        "resources": [{"kind": "triangle_mesh", "key": "mesh"}]},
        "mesh": {"positions": positions, "values": values, "indices": indices}}
