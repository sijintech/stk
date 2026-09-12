"""Regular point-grid views. Physical coordinates are origin + index * spacing.

NumPy storage is (x,y,z,component); VTK point arrays have x varying fastest.
Filters run in double precision. Render coordinates are relative to an explicit
origin so GPU float32 conversion does not erase small features far from zero.
"""
from dataclasses import dataclass
import hashlib
from pathlib import Path

import numpy as np

from toolkits.sviz.field import read_field


@dataclass
class Grid:
    values: np.ndarray
    origin: tuple = (0., 0., 0.)
    spacing: tuple = (1., 1., 1.)
    units: str = "unspecified"
    field: str = "field"
    coordinate_units: str = "unspecified"
    timestep: int | None = None

    def __post_init__(self):
        self.values = np.asarray(self.values)
        if self.values.ndim == 3:
            self.values = self.values[..., None]
        if (self.values.ndim != 4 or min(self.values.shape) < 1
                or self.values.dtype.kind not in "fiu" or not np.isfinite(self.values).all()):
            raise ValueError("Expected a finite real (x,y,z,component) point field")
        if (len(self.origin) != 3 or len(self.spacing) != 3
                or not np.isfinite(self.origin).all() or not np.isfinite(self.spacing).all()
                or min(self.spacing) <= 0):
            raise ValueError("Origin must be finite and spacing strictly positive")
        if self.timestep is not None and (isinstance(self.timestep, bool) or not isinstance(self.timestep, int) or self.timestep < 0):
            raise ValueError("Time-step metadata must be a nonnegative integer")

    @property
    def dimensions(self):
        return self.values.shape[:3]

    def scalar(self, component=0):
        if component == "magnitude":
            return np.linalg.norm(self.values.astype(np.float64), axis=3)
        if isinstance(component, bool) or not isinstance(component, int) or not 0 <= component < self.values.shape[3]:
            raise ValueError("Component outside field")
        return self.values[..., component].astype(np.float64)

    def image(self, component=0):
        import vtk
        from vtk.util.numpy_support import numpy_to_vtk
        image = vtk.vtkImageData()
        image.SetDimensions(*self.dimensions)
        image.SetOrigin(*self.origin)
        image.SetSpacing(*self.spacing)
        values = numpy_to_vtk(self.scalar(component).ravel(order="F"), deep=True)
        values.SetName(self.field)
        image.GetPointData().SetScalars(values)
        return image


def load_grid(path, *, file_format=None, **metadata):
    path = Path(path)
    suffix = file_format or path.suffix.lower()
    if file_format is not None and file_format not in {".vtk", ".vti"}:
        raise ValueError("Explicit scientific format must be .vtk or .vti")
    if suffix not in {".vtk", ".vti"}:
        return Grid(read_field(path), **metadata)
    import vtk
    from vtk.util.numpy_support import vtk_to_numpy
    reader = vtk.vtkXMLImageDataReader() if suffix == ".vti" else vtk.vtkStructuredPointsReader()
    reader.SetFileName(str(path))
    reader.Update()
    data = reader.GetOutput()
    dimensions = data.GetDimensions()
    array = data.GetPointData().GetScalars()
    if array is None:
        array = data.GetPointData().GetVectors()
    if min(dimensions) < 1 or array is None:
        raise ValueError("Expected VTK image/structured-points data with point scalars or vectors")
    values = vtk_to_numpy(array).reshape((*dimensions[::-1], -1)).transpose(2, 1, 0, 3)
    # A non-zero VTK extent changes the location of the first stored sample.
    extent = data.GetExtent()
    origin = tuple(data.GetOrigin()[i] + extent[2*i]*data.GetSpacing()[i] for i in range(3))
    metadata = dict(metadata)
    for name in ("units", "coordinate_units"):
        annotation = data.GetFieldData().GetAbstractArray("STK_" + name)
        if annotation is not None and annotation.GetNumberOfValues() == 1:
            metadata.setdefault(name, str(annotation.GetVariantValue(0).ToString()))
    annotation = data.GetFieldData().GetArray("STK_timestep")
    if annotation is not None and annotation.GetNumberOfValues() == 1:
        step = float(annotation.GetTuple1(0))
        if not np.isfinite(step) or step < 0 or int(step) != step:
            raise ValueError("Invalid VTK time-step metadata")
        metadata["timestep"] = int(step)
    metadata.update(origin=origin, spacing=data.GetSpacing(), field=array.GetName() or "field")
    return Grid(values, **metadata)


def probe(grid, position):
    """Trilinear interpolation of original point samples (including boundaries)."""
    p = np.asarray(position, dtype=np.float64)
    if p.shape != (3,) or not np.isfinite(p).all():
        raise ValueError("A finite physical xyz position is required")
    index = (p - grid.origin) / grid.spacing
    last = np.asarray(grid.dimensions) - 1
    if (index < -1e-10).any() or (index > last + 1e-10).any():
        raise ValueError("Probe is outside the grid")
    index = np.clip(index, 0, last)
    lo = np.floor(index).astype(int)
    hi = np.minimum(lo + 1, last)
    t = index - lo
    result = np.zeros(grid.values.shape[3], dtype=np.float64)
    for dx, dy, dz in np.ndindex(2, 2, 2):
        bits = np.array([dx, dy, dz])
        weight = np.prod(np.where(bits, t, 1 - t))
        result += weight * grid.values[tuple(np.where(bits, hi, lo))]
    return {"position": p.tolist(), "values": result.tolist(), "units": grid.units,
            "interpolation": "trilinear", "source": "original_point_data"}


def _poly_mesh(poly, render_origin, max_vertices):
    import vtk
    from vtk.util.numpy_support import vtk_to_numpy
    triangles = vtk.vtkTriangleFilter()
    triangles.SetInputData(poly)
    triangles.Update()
    output = triangles.GetOutput()
    reduced = False
    if output.GetNumberOfPoints() > max_vertices:
        decimate = vtk.vtkDecimatePro()
        decimate.SetInputData(output)
        decimate.SetTargetReduction(min(.99, 1 - max_vertices / output.GetNumberOfPoints()))
        decimate.PreserveTopologyOff()
        decimate.Update()
        output = decimate.GetOutput()
        reduced = True
    if output.GetNumberOfPoints() > max_vertices * 2:
        raise ValueError("View exceeds transfer budget; use a coarser slice or smaller region")
    if output.GetNumberOfPoints() == 0:
        return {"positions": [], "indices": [], "values": [], "reduced": reduced}
    positions = vtk_to_numpy(output.GetPoints().GetData()).astype(np.float64) - render_origin
    cells = vtk_to_numpy(output.GetPolys().GetConnectivityArray()).reshape(-1, 3)
    scalars = output.GetPointData().GetScalars()
    values = vtk_to_numpy(scalars) if scalars else np.zeros(len(positions))
    if values.ndim > 1:
        values = np.linalg.norm(values, axis=1)
    return {"positions": positions.tolist(), "indices": cells.ravel().tolist(),
            "values": values.astype(float).tolist(), "reduced": reduced}


def build_scene(grid, *, dataset_id, mode="slice", component=0, axis=2, index=None,
                level=None, timestep=None, max_vertices=20000):
    if timestep is not None and grid.timestep is not None and timestep != grid.timestep:
        raise ValueError("Requested time step differs from the selected data file")
    timestep = grid.timestep if grid.timestep is not None else (timestep if timestep is not None else 0)
    if isinstance(timestep, bool) or not isinstance(timestep, int) or timestep < 0:
        raise ValueError("Time step must be a nonnegative integer")
    import vtk
    from vtk.util.numpy_support import numpy_to_vtk
    if mode not in {"slice", "iso", "vectors"} or axis not in (0, 1, 2):
        raise ValueError("Unknown view mode or axis")
    if not 100 <= max_vertices <= 40000:
        raise ValueError("Vertex budget must be between 100 and 40000")
    scalar = grid.scalar(component)
    value_range = [float(scalar.min()), float(scalar.max())]
    origin = np.array(grid.origin, dtype=np.float64)
    image = grid.image(component)
    # Run geometric filters near zero; VTK filters may choose float32 points.
    # Scientific scalar samples and physical manifest/probe coordinates stay double.
    image.SetOrigin(0., 0., 0.)
    if mode == "slice":
        index = grid.dimensions[axis] // 2 if index is None else index
        if not isinstance(index, int) or not 0 <= index < grid.dimensions[axis]:
            raise ValueError("Slice index outside field")
        # Extract a grid plane rather than cutting: also handles a singleton axis.
        extent = [0, grid.dimensions[0]-1, 0, grid.dimensions[1]-1, 0, grid.dimensions[2]-1]
        extent[axis*2:axis*2+2] = [index, index]
        extract = vtk.vtkImageDataGeometryFilter()
        extract.SetInputData(image)
        extract.SetExtent(*extent)
        extract.Update()
        poly = extract.GetOutput()
    elif mode == "iso":
        level = sum(value_range)/2 if level is None else float(level)
        if not np.isfinite(level):
            raise ValueError("Isovalue must be finite")
        contour = vtk.vtkContourFilter()
        contour.SetInputData(image)
        contour.SetValue(0, level)
        contour.Update()
        poly = contour.GetOutput()
    else:
        if grid.values.shape[3] != 3:
            raise ValueError("Vector arrows require exactly three components")
        stride = max(1, int(np.ceil((np.prod(grid.dimensions)/max(1, max_vertices//60)) ** (1/3))))
        coords = np.array(list(np.ndindex(tuple((n-1)//stride+1 for n in grid.dimensions)))) * stride
        vectors = grid.values[tuple(coords.T)].astype(np.float64)
        points = vtk.vtkPoints()
        points.SetData(numpy_to_vtk(coords*np.array(grid.spacing), deep=True))
        source = vtk.vtkPolyData()
        source.SetPoints(points)
        source.GetPointData().SetVectors(numpy_to_vtk(vectors, deep=True))
        source.GetPointData().SetScalars(numpy_to_vtk(scalar[tuple(coords.T)], deep=True))
        arrow = vtk.vtkArrowSource()
        arrow.SetTipResolution(4)
        arrow.SetShaftResolution(4)
        glyph = vtk.vtkGlyph3D()
        glyph.SetInputData(source)
        glyph.SetSourceConnection(arrow.GetOutputPort())
        glyph.SetVectorModeToUseVector()
        glyph.SetScaleModeToScaleByVector()
        glyph.SetColorModeToColorByScalar()
        magnitude = float(np.linalg.norm(vectors, axis=1).max())
        glyph.SetScaleFactor(min(grid.spacing)*stride*.8/max(magnitude, 1e-30))
        glyph.Update()
        poly = glyph.GetOutput()
    mesh = _poly_mesh(poly, np.zeros(3), max_vertices)
    descriptor = {"version": 1, "dataset_id": dataset_id, "field": grid.field,
                  "association": "point", "dimensions": list(grid.dimensions),
                  "origin": list(grid.origin), "spacing": list(grid.spacing),
                  "units": grid.units, "coordinate_units": grid.coordinate_units,
                  "components": grid.values.shape[3], "component": component,
                  "timestep": timestep, "mode": mode, "axis": axis, "index": index,
                  "level": level, "value_range": value_range, "render_origin": origin.tolist(),
                  "display_reduced": mesh["reduced"], "resources": [{"kind": "triangle_mesh", "key": "mesh"}]}
    return {"manifest": descriptor, "mesh": mesh}


def file_id(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
