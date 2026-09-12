"""The fixed STK demonstration method, including its independent result checks."""

import hashlib
import json
import math
from importlib.resources import files

from synorder_interaction.contracts import Conflict, canonical

NAME = "stk.analytic-field.v1"


def script():
    return files("synorder_stk").joinpath("examples", "simulate.py").read_bytes()


def prepare(detail):
    source = script()
    if hashlib.sha256(source).hexdigest() != detail["script_sha256"]:
        raise Conflict("方法文件已变化，不能启动旧配置")
    return {
        "simulate.py": source,
        "input.json": canonical({"amplitude": detail["amplitude"]}).encode(),
    }


def verify(detail, contents):
    summary = json.loads(contents["summary.json"])
    canonical(summary)
    amplitude = detail["amplitude"]
    expected = {
        "amplitude": amplitude,
        "mean": amplitude * 13,
        "minimum": min(0, amplitude * 26),
        "maximum": max(0, amplitude * 26),
    }
    passed = all(
        type(summary.get(k)) in (int, float)
        and math.isclose(summary[k], value, rel_tol=0, abs_tol=1e-9)
        for k, value in expected.items()
    )
    dat = contents["field.dat"].decode().splitlines()
    if dat[0].split() != ["8", "6", "4"] or len(dat) != 193:
        raise ValueError("DAT dimensions differ from the fixed example")
    seen = set()
    for line in dat[1:]:
        i, j, k, value = line.split()
        point = (int(i), int(j), int(k))
        if (
            not (1 <= point[0] <= 8 and 1 <= point[1] <= 6 and 1 <= point[2] <= 4)
            or point in seen
        ):
            raise ValueError("DAT coordinates differ from the fixed example")
        seen.add(point)
        expected_value = amplitude * (
            point[0] - 1 + 2 * (point[1] - 1) + 3 * (point[2] - 1)
        )
        passed &= math.isclose(float(value), expected_value, rel_tol=0, abs_tol=1e-12)
    vtk = contents["field.vtk"].decode().splitlines()
    if vtk[2:8] != [
        "ASCII",
        "DATASET STRUCTURED_POINTS",
        "DIMENSIONS 8 6 4",
        "ORIGIN 0 0 0",
        "SPACING 1 1 1",
        "POINT_DATA 192",
    ]:
        raise ValueError("VTK geometry differs from the fixed example")
    if vtk[8:10] != ["SCALARS field double 1", "LOOKUP_TABLE default"]:
        raise ValueError("VTK scalar declaration differs from the fixed example")
    numbers = [float(v) for v in " ".join(vtk[10:]).split()]
    expected_values = [
        amplitude * (i + 2 * j + 3 * k)
        for k in range(4)
        for j in range(6)
        for i in range(8)
    ]
    passed &= len(numbers) == len(expected_values) and all(
        math.isclose(a, b, rel_tol=0, abs_tol=1e-12)
        for a, b in zip(numbers, expected_values)
    )
    passed &= contents["preview.png"].startswith(b"\x89PNG\r\n\x1a\n")
    environment = json.loads(contents["environment.json"])
    canonical(environment)
    passed &= all(
        isinstance(environment.get(k), str)
        for k in ("python", "numpy", "matplotlib", "platform")
    )
    # This validates the deterministic I/O example, never a scientific solver's validity.
    return {
        "summary": summary,
        "verification": "passed" if passed else "failed",
        "verification_kind": "deterministic-io-example",
        "scientific_validation": "not_applicable",
        "field_absolute_tolerance": 1e-12,
        "field_points": len(seen),
        "environment": environment,
        "acceptance": "pending",
    }
