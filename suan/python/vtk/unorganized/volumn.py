
from vtk import *

file_name = "strain.vtk"

# Read the source file.
reader = vtk.vtkDataSetReader()
reader.SetFileName(file_name)
reader.Update() # Needed because of GetScalarRange
id = reader.GetOutput()
scalar_range = id.GetPointData().GetArray(0).GetRange()
print(scalar_range)


# Create the mapper that corresponds the objects of the vtk file
# into graphics elements
mapper = vtkSmartVolumeMapper()
mapper.SetInputConnection(reader.GetOutputPort())

# Create the Actor


actor = vtkVolume()
actor.SetMapper(mapper)
volumeProperty=vtkVolumeProperty()
opacity=vtkPiecewiseFunction()
# opacity.AddPoint(scalar_range[0],0.3)
# opacity.AddPoint(sum(scalar_range)/8,0.3)
# opacity.AddPoint(sum(scalar_range)/8,0.05)
# opacity.AddPoint(6*sum(scalar_range)/8,0.05)
# opacity.AddPoint(6*sum(scalar_range)/8,0.3)
# opacity.AddPoint(scalar_range[1],0.3)

color=vtkColorTransferFunction()
color.SetColorSpaceToLab()
# color.AddRGBPoint(scalar_range[0],0.0,0.0,1.0)
# color.AddRGBPoint(sum(scalar_range)/2,0,1,0)
# color.AddRGBPoint(scalar_range[1],1.0,0.0,0.0)


opacityPoint=6
opValue=[scalar_range[0],sum(scalar_range)/8,sum(scalar_range)/8,6*sum(scalar_range)/8,6*sum(scalar_range)/8,scalar_range[1]]
alpha=[0.3,0.3,0.0,0.0,0.3,0.3]
for a in range(0,opacityPoint):
    opacity.AddPoint(opValue[a],alpha[a])

RGBPoint=3
RGBValue=[scalar_range[0],sum(scalar_range)/2,scalar_range[1]]
RGB = [[0.0,0.0,1.0],[0.0,1.0,0.0],[1.0,0.0,0.0]]
for a in range(0,RGBPoint):
    color.AddRGBPoint(RGBValue[a],RGB[a][0],RGB[a][1],RGB[a][2])



volumeProperty.SetScalarOpacity(opacity)
volumeProperty.SetColor(color)
volumeProperty.SetInterpolationTypeToNearest()

actor.SetProperty(volumeProperty)


# Create the Renderer
renderer = vtkRenderer()
renderer.AddActor(actor)
scaleBar=vtkScalarBarActor()
scaleBar.SetLookupTable(color)
scaleBar.SetTitle("Scale Bar")
scaleBar.SetNumberOfLabels(RGBPoint)
scaleBar.GetTitleTextProperty().SetColor(0,0,0)
scaleBar.GetLabelTextProperty().SetColor(0,0,0)
renderer.AddActor2D(scaleBar)
renderer.SetBackground(1, 1, 1) # Set background to white

# Create the RendererWindow
renderer_window = vtkRenderWindow()
renderer_window.AddRenderer(renderer)
print(scalar_range[0],scalar_range[1])
# Create the RendererWindowInteractor and display the vtk_file
interactor = vtkRenderWindowInteractor()
interactor.SetRenderWindow(renderer_window)


interactor.Initialize()
interactor.Start()
