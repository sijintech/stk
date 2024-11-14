  
from vtk import *
from math import sqrt

file_name = "tensor.vtk"

# Read the source file.
reader = vtk.vtkDataSetReader()
reader.SetFileName(file_name)
reader.Update()
id = reader.GetOutput()
scalar_range = reader.GetStructuredPointsOutput().GetPointData().GetTensors().GetRange(-1)
print(scalar_range)
#Reduce the amount of points to be plotted, using maskPoints
mask = vtkMaskPoints()
mask.SetInputConnection(reader.GetOutputPort())
mask.SetOnRatio(100)
mask.SetMaximumNumberOfPoints(1000000)
mask.RandomModeOn()

#Making tensor glyph with superquadratic glyph
super=vtkSuperquadricSource()
tensorglyph=vtkTensorGlyph()
tensorglyph.SetInputConnection(mask.GetOutputPort())
tensorglyph.SetSourceConnection(super.GetOutputPort())
#----------------------------------------------------------------------------
tensorglyph.SetScaleFactor(0.6/sqrt(scalar_range[0]*scalar_range[1]))
#----------------------------------------------------------------------------
tensorglyph.ColorGlyphsOn()
tensorglyph.SetColorModeToEigenvalues()

#tensor glyph mapper
mapper = vtkPolyDataMapper()
mapper.SetInputConnection(tensorglyph.GetOutputPort())

actor = vtkActor()
actor.SetMapper(mapper)

#create the outer boundary of the data
outline=vtkOutlineFilter()
outline.SetInput(reader.GetOutput())
outlineMapper=vtkDataSetMapper()
outlineMapper.SetInputConnection(outline.GetOutputPort())
outlineActor=vtkActor()
outlineActor.SetMapper(outlineMapper)
outlineActor.GetProperty().SetColor(0,0,0)


renderer = vtkRenderer()
renderer.AddActor(actor)
renderer.AddActor(outlineActor)
renderer.SetBackground(1, 1, 1) # Set background to white

renWin = vtkRenderWindow()
renWin.AddRenderer(renderer)


interactor = vtkRenderWindowInteractor()
interactor.SetRenderWindow(renWin)

interactor.Initialize()

renWin.Render()

interactor.Start()