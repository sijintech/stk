"""Qt-free regular-grid I/O and previews.

Array axes are (x, y, z, component). DAT indices are one-based; legacy
STRUCTURED_POINTS VTK stores x fastest. No physics or solver is implemented.
"""

from pathlib import Path
import numpy as np


def read_field(filename):
    path = Path(filename)
    if path.suffix.lower() == ".npy":
        data = np.load(path, allow_pickle=False)
        if data.ndim == 3:
            data = data[..., None]
    elif path.suffix.lower() == ".vtk":
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(lines) < 10 or lines[2].strip() != "ASCII" or lines[3].strip() != "DATASET STRUCTURED_POINTS":
            raise ValueError("Preview supports ASCII STRUCTURED_POINTS VTK; convert other VTK types first")
        tokens = " ".join(lines[4:]).split()
        index = tokens.index("DIMENSIONS")
        shape = tuple(map(int, tokens[index + 1:index + 4]))
        for key, expected in [("ORIGIN", (0., 0., 0.)), ("SPACING", (1., 1., 1.))]:
            index = tokens.index(key)
            if tuple(map(float, tokens[index + 1:index + 4])) != expected:
                raise ValueError("This conversion supports unit grid spacing and zero origin only")
        if "VECTORS" in tokens:
            index = tokens.index("VECTORS") + 3
            components = 3
        else:
            index = tokens.index("SCALARS")
            components = int(tokens[index + 3]) if tokens[index + 3] != "LOOKUP_TABLE" else 1
            index = tokens.index("LOOKUP_TABLE") + 2
        values = np.array(tokens[index:], dtype=float)
        data = values.reshape((shape[2], shape[1], shape[0], components)).transpose(2, 1, 0, 3)
    else:
        # Header 'nx ny nz [n4 [n5]] [! comment]', then one-based index rows (suan/data/dat.py: a
        # fixed-width fast path plus the general parser, same checks and messages as before).
        from suan.data.dat import read_dat
        data = read_dat(path, layout="xyzc")
    if data.ndim != 4 or any(n < 1 for n in data.shape) or not np.issubdtype(data.dtype, np.number) or not np.isfinite(data).all():
        raise ValueError("Expected a finite numeric (x,y,z[,component]) field")
    return data


def write_field(filename, data):
    path = Path(filename)
    data = np.asarray(data)
    if data.ndim == 3:
        data = data[..., None]
    if data.ndim != 4 or not np.isfinite(data).all():
        raise ValueError("Expected a finite (x,y,z,component) field")
    path.parent.mkdir(parents=True, exist_ok=True)
    nx, ny, nz, components = data.shape
    if path.suffix.lower() == ".npy":
        np.save(path, data, allow_pickle=False)
    elif path.suffix.lower() == ".vtk":
        if components not in (1, 3):
            raise ValueError("VTK export supports one scalar or three vector components")
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(f"# vtk DataFile Version 3.0\nSTK field\nASCII\nDATASET STRUCTURED_POINTS\nDIMENSIONS {nx} {ny} {nz}\nORIGIN 0 0 0\nSPACING 1 1 1\nPOINT_DATA {nx*ny*nz}\n")
            stream.write("VECTORS field double\n" if components == 3 else "SCALARS field double 1\nLOOKUP_TABLE default\n")
            np.savetxt(stream, data.transpose(2, 1, 0, 3).reshape(-1, components), fmt="%.17g")
    else:
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(f"{nx} {ny} {nz}\n")
            for i, j, k in np.ndindex(nx, ny, nz):
                stream.write(f"{i+1} {j+1} {k+1} " + " ".join(f"{v:.17g}" for v in data[i, j, k]) + "\n")
    return path


def field_info(filename):
    data = read_field(filename)
    return {"shape": list(data.shape[:3]), "components": data.shape[3], "min": float(data.min()),
            "max": float(data.max()), "mean": float(data.mean())}


def plot_field(filename, output, vector=False, axis="z", index=None, component=0):
    # FigureCanvasAgg avoids global backend changes when called from desktop.
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    data = read_field(filename)
    direction = "xyz".index(axis)
    index = data.shape[direction] // 2 if index is None else index
    if not 0 <= index < data.shape[direction] or not 0 <= component < data.shape[3]:
        raise ValueError("Slice index or component is outside the field")
    plane = np.take(data, index, axis=direction)
    fig = Figure(figsize=(6, 5), tight_layout=True)
    FigureCanvasAgg(fig)
    ax = fig.subplots()
    axes = [n for n in range(3) if n != direction]
    if vector:
        if data.shape[3] != 3:
            raise ValueError("Vector preview requires exactly three components")
        x, y = np.meshgrid(np.arange(plane.shape[0]), np.arange(plane.shape[1]), indexing="ij")
        stride = max(1, max(plane.shape[:2]) // 40)
        ax.quiver(x[::stride, ::stride], y[::stride, ::stride], plane[::stride, ::stride, axes[0]], plane[::stride, ::stride, axes[1]])
    else:
        view = ax.imshow(plane[..., component].T, origin="lower", aspect="equal")
        fig.colorbar(view, ax=ax)
    ax.set(xlabel="xyz"[axes[0]], ylabel="xyz"[axes[1]], title=f"{Path(filename).name}: {axis}={index}")
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    return path
