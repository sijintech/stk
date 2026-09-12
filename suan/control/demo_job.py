"""Manufactured fields for transport and visualization acceptance; no solver."""
from pathlib import Path
import numpy as np
import vtk
from vtk.util.numpy_support import numpy_to_vtk


def main():
    shape = (32, 28, 24)
    origin, spacing = (-2., 3., 10.), (.2, .3, .4)
    x, y, z = np.meshgrid(*(origin[i] + np.arange(shape[i])*spacing[i] for i in range(3)), indexing="ij")
    values = [x + 2*y - .5*z, x + 2*y - .5*z + 2, np.stack((x, y, z), axis=3)]
    for name, value, step in zip(["scalar-0.vti", "scalar-1.vti", "vector.vti"], values, [0, 1, 0]):
        image = vtk.vtkImageData()
        image.SetDimensions(*shape)
        image.SetOrigin(*origin)
        image.SetSpacing(*spacing)
        array = value.ravel(order="F") if value.ndim == 3 else value.transpose(2, 1, 0, 3).reshape(-1, 3)
        field = numpy_to_vtk(np.ascontiguousarray(array), deep=True)
        field.SetName("manufactured")
        image.GetPointData().SetScalars(field)
        for key, text in (("STK_units", "Pa" if value.ndim == 3 else "m"), ("STK_coordinate_units", "m")):
            annotation = vtk.vtkStringArray()
            annotation.SetName(key)
            annotation.InsertNextValue(text)
            image.GetFieldData().AddArray(annotation)
        time_step = vtk.vtkIntArray()
        time_step.SetName("STK_timestep")
        time_step.InsertNextValue(step)
        image.GetFieldData().AddArray(time_step)
        writer = vtk.vtkXMLImageDataWriter()
        writer.SetFileName(str(Path(name)))
        writer.SetInputData(image)
        if not writer.Write():
            raise RuntimeError("VTK file write failed")
        print(f"Published {name}", flush=True)


if __name__ == "__main__":
    main()
