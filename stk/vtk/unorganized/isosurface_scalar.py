
from vtk import *

file_name = "stress.vtk"

# Read the source file.
reader = vtk.vtkDataSetReader()
reader.SetFileName(file_name)
reader.Update() # Needed because of GetScalarRange
id = reader.GetOutput()
scalar_range = id.GetPointData().GetArray(0).GetRange()

print(scalar_range)

contour = vtkContourFilter()
contour.SetInput(id)

#-------------------------------------------------------------------------------
diff=scalar_range[1]-scalar_range[0]
#-------------------------------------------------------------------------------
color=vtkColorTransferFunction()
color.SetColorSpaceToLab()
RGBPoint=3
RGBValue=[scalar_range[0],diff/2+scalar_range[0],scalar_range[1]]
RGB = [[0.0,0.0,1.0],[0.0,1.0,0.0],[1.0,0.0,0.0]]
for a in range(0,RGBPoint):
    color.AddRGBPoint(RGBValue[a],RGB[a][0],RGB[a][1],RGB[a][2])

#-------------------------------------------------------------------------------
#isoValue1 should be set by user, the following gis default value
isoValue1=diff*1/8+scalar_range[0]
contour.SetValue(0,isoValue1)
#-------------------------------------------------------------------------------
contour.ComputeScalarsOn()


contour1 = vtkContourFilter()
contour1.SetInput(id)
contour1.ComputeScalarsOn()
#-------------------------------------------------------------------------------
#isoValue2 should be set by user, the following gis default value
isoValue2=diff*6/8+scalar_range[0]
contour1.SetValue(0,isoValue2)
#-------------------------------------------------------------------------------
# Create the mapper that corresponds the objects of the vtk file
# into graphics elements
mapper = vtkDataSetMapper()
mapper.SetInputConnection(reader.GetOutputPort())
mapper.SetLookupTable(color)

mapper1 = vtkDataSetMapper()
mapper1.SetInputConnection(contour.GetOutputPort())
mapper1.SetLookupTable(color)

mapper2 = vtkDataSetMapper()
mapper2.SetInputConnection(contour1.GetOutputPort())
mapper2.SetLookupTable(color)
# Create the Actor
actor = vtkActor()
actor.SetMapper(mapper)
actor.GetProperty().SetOpacity(0.1)
#actor.GetProperty().SetRepresentationToSurface()

actor1 = vtkActor()
actor1.SetMapper(mapper1)
actor1.GetProperty().SetOpacity(0.5)

actor2 = vtkActor()
actor2.SetMapper(mapper2)
actor2.GetProperty().SetOpacity(0.7)
#actor.GetProperty().SetOrigin(1.0,1.0,1.0)
# Create the Renderer
renderer = vtkRenderer()
renderer.AddActor(actor)
renderer.AddActor(actor1)
renderer.AddActor(actor2)
#-------------------------------------------------------------------------------
#20140820
scaleBar=vtkScalarBarActor()
scaleBar.SetLookupTable(color)
scaleBar.SetTitle("Scale Bar")
scaleBar.SetNumberOfLabels(RGBPoint)
scaleBar.GetTitleTextProperty().SetColor(0,0,0)
scaleBar.GetLabelTextProperty().SetColor(0,0,0)
renderer.AddActor2D(scaleBar)
#-------------------------------------------------------------------------------
renderer.SetBackground(1, 1, 1) # Set background to white

# Create the RendererWindow
renderer_window = vtkRenderWindow()
renderer_window.AddRenderer(renderer)
 
# Create the RendererWindowInteractor and display the vtk_file
interactor = vtkRenderWindowInteractor()
interactor.SetRenderWindow(renderer_window)
interactor.Initialize()
interactor.Start()