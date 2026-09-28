"""Deterministic synthetic 3D field, for testing the STK workflow (not a physical solver)."""
import json
import math
from pathlib import Path
import platform
import struct
import sys
import zlib


def simulate(config, directory):
    temperature, size = float(config["temperature_K"]), int(config.get("size", 17))
    if not math.isfinite(temperature) or not 0 < temperature <= 10000 or not 3 <= size <= 65 or size % 2 != 1:
        raise ValueError("Use a positive finite temperature and an odd grid size from 3 to 65")
    axis = [i / (size - 1) for i in range(size)]
    values = [temperature * math.exp(-12 * ((x - .5) ** 2 + (y - .5) ** 2 + (z - .5) ** 2))
              for z in axis for y in axis for x in axis]
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    header = ("# vtk DataFile Version 3.0\nSTK synthetic field\nASCII\nDATASET STRUCTURED_POINTS\n"
              f"DIMENSIONS {size} {size} {size}\nORIGIN 0 0 0\nSPACING " + " ".join([str(1 / (size - 1))] * 3) +
              f"\nPOINT_DATA {len(values)}\nSCALARS response double 1\nLOOKUP_TABLE default\n")
    (directory / "field.vtk").write_text(header + "\n".join(format(value, ".17g") for value in values) + "\n", encoding="ascii")
    metrics = {"format": 1, "synthetic": True, "temperature_K": temperature, "shape": [size] * 3,
               "mean_K": math.fsum(values) / len(values), "max_K": max(values),
               "python": sys.version, "platform": platform.platform()}
    (directory / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    plane = values[(size // 2) * size * size:(size // 2 + 1) * size * size]
    def color(value):
        fraction = max(0., min(1., value / 400.))
        return bytes((round(255 * fraction), round(180 * (1 - abs(2 * fraction - 1))), round(255 * (1 - fraction))))
    raw = b"".join(b"\x00" + b"".join(color(value) for value in plane[y * size:(y + 1) * size]) for y in range(size))
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    (directory / "slice.png").write_bytes(png)
    return metrics


if __name__ == "__main__":
    config = json.loads(Path("input.json").read_text(encoding="utf-8"))
    metrics = simulate(config, Path.cwd())
    print(f"Synthetic field: T={metrics['temperature_K']} K, mean={metrics['mean_K']:.6f} K, max={metrics['max_K']:.6f} K", flush=True)
