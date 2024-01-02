
from vtk import *

file_name = "strain.vtk"

# Read the source file.
reader = vtk.vtkDataSetReader()
reader.SetFileName(file_name)
reader.Update() # Needed because of GetScalarRange
id = reader.GetOutput()
scalar_range = id.GetPointData().GetArray(0).GetRange()

print(scalar_range)

colormap=vtkLookupTable()
colormap.SetHueRange(0,0)
colormap.SetSaturationRange(0,0)
colormap.SetAlphaRange(0.5,0.5)
colormap.SetValueRange(0,0)

contour = vtkContourFilter()
contour.SetInput(id)
contour.SetValue(0,1)
contour.ComputeScalarsOn()
contour1 = vtkContourFilter()
contour1.SetInput(id)
contour1.ComputeScalarsOn()
contour1.SetValue(0,2)
# Create the mapper that corresponds the objects of the vtk file
# into graphics elements
mapper = vtkDataSetMapper()
mapper.SetInputConnection(reader.GetOutputPort())
mapper.SetScalarRange(0,0)
mapper.SetLookupTable(colormap)

mapper1 = vtkDataSetMapper()
mapper1.SetInputConnection(contour.GetOutputPort())
mapper1.SetScalarRange(scalar_range)

mapper2 = vtkDataSetMapper()
mapper2.SetInputConnection(contour1.GetOutputPort())
mapper2.SetScalarRange(scalar_range)
# Create the Actor
actor = vtkActor()
actor.SetMapper(mapper)
actor.GetProperty().SetColor(0,0,0)
actor.GetProperty().SetOpacity(0.5)
#actor.GetProperty().SetRepresentationToSurface()

actor1 = vtkActor()
actor1.SetMapper(mapper1)

actor2 = vtkActor()
actor2.SetMapper(mapper2)

#actor.GetProperty().SetOrigin(1.0,1.0,1.0)
# Create the Renderer
renderer = vtkRenderer()
renderer.AddActor(actor)
renderer.AddActor(actor1)
renderer.AddActor(actor2)
renderer.SetBackground(1, 1, 1) # Set background to white
 
# Create the RendererWindow
renderer_window = vtkRenderWindow()
renderer_window.AddRenderer(renderer)
 
# Create the RendererWindowInteractor and display the vtk_file
interactor = vtkRenderWindowInteractor()
interactor.SetRenderWindow(renderer_window)
interactor.Initialize()
interactor.Start()