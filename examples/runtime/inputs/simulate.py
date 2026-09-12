"""Deterministic I/O acceptance case; this is not a physical solver."""

import json
from pathlib import Path
import platform
import time

import matplotlib
import numpy as np
from toolkits.sviz.field import write_field, plot_field

config = json.loads(Path("input.json").read_text())
amplitude = config["amplitude"]
x, y, z = np.indices((8, 6, 4))
field = amplitude * (x + 2 * y + 3 * z).astype(float)
print(f"Computing amplitude={amplitude}", flush=True)
time.sleep(config.get("delay_seconds", 0))
write_field("field.dat", field)
write_field("field.vtk", field)
plot_field("field.dat", "preview.png", axis="z", index=2)
Path("summary.json").write_text(
    json.dumps(
        {
            "amplitude": amplitude,
            "mean": float(field.mean()),
            "minimum": float(field.min()),
            "maximum": float(field.max()),
        }
    )
)
Path("environment.json").write_text(
    json.dumps(
        {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "numpy": np.__version__,
            "matplotlib": matplotlib.__version__,
        }
    )
)
print("Results ready", flush=True)
