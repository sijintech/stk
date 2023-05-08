
from vtk import *
from math import sqrt

file_name = "v123.vtk"

# Read the source file.
reader = vtk.vtkDataSetReader()
reader.SetFileName(file_name)
reader.Update() # Needed because of GetScalarRange
id = reader.GetOutput()
#scalar_range = id.GetPointData().GetArray(0).GetRange(-1)
scalar_range=[0.001,1]
print(reader)

# Create the mapper that corresponds the objects of the vtk file
# into graphics elements



arrow = vtkArrowSource()
arrow.Update()
mask = vtkMaskPoints()
mask.SetOnRatio(10)
mask.SetInputConnection(reader.GetOutputPort())
mask.Update()
glyph = vtkGlyph3D()
glyph.SetSourceConnection(arrow.GetOutputPort())
glyph.SetInputConnection(mask.GetOutputPort())
glyph.OrientOn()
glyph.SetVectorModeToUseVector()
glyph.SetColorModeToColorByVector()
glyph.SetScaleModeToScaleByVector()

#-------------------------------------------------------------------------------
glyph.SetScaleFactor(1/sqrt(scalar_range[0]*scalar_range[1]))
#-------------------------------------------------------------------------------
outline=vtkOutlineFilter()
outline.SetInputConnection(reader.GetOutputPort())

mapper = vtkDataSetMapper()
mapper.SetInputConnection(glyph.GetOutputPort())

#-------------------------------------------------------------------------------
mapper.SetScalarRange(scalar_range[0],scalar_range[1])
#-------------------------------------------------------------------------------
color=vtkColorTransferFunction()
color.SetColorSpaceToLab()
diff=scalar_range[1]-scalar_range[0]
RGBPoint=3
RGBValue=[scalar_range[0],diff/2+scalar_range[0],scalar_range[1]]
RGB = [[0.0,0.0,1.0],[0.0,1.0,0.0],[1.0,0.0,0.0]]
for a in range(0,RGBPoint):
    color.AddRGBPoint(RGBValue[a],RGB[a][0],RGB[a][1],RGB[a][2])

mapper.SetLookupTable(color)



outlineMapper=vtkPolyDataMapper()
outlineMapper.SetInputConnection(outline.GetOutputPort())
# Create the Actor
actor = vtkActor()
actor.SetMapper(mapper)
actor.GetProperty().SetOpacity(0.5)
actor.GetProperty().SetRepresentationToSurface()


transform=vtkTransform()
transform.Translate(-5,0.0,0.0)
axes=vtkAxesActor()
axes.SetUserTransform(transform)
axes.SetScale(10)
axes.SetTotalLength(10,10,10)
axes.GetXAxisCaptionActor2D().GetProperty().SetColor(0,0,0)
axes.GetYAxisCaptionActor2D().GetProperty().SetColor(0,0,0)
axes.GetZAxisCaptionActor2D().GetProperty().SetColor(0,0,0)
outlineActor=vtkActor()
outlineActor.SetMapper(outlineMapper)
outlineActor.GetProperty().SetColor(0,0,0)



# Create the Renderer
renderer = vtkRenderer()
renderer.AddActor(actor)
renderer.AddActor(outlineActor)
renderer.AddActor(axes)


scaleBar=vtkScalarBarActor()
scaleBar.SetLookupTable(color)
scaleBar.SetTitle("Scale Bar")
scaleBar.SetNumberOfLabels(RGBPoint)
scaleBar.GetTitleTextProperty().SetColor(0,0,0)
scaleBar.GetLabelTextProperty().SetColor(0,0,0)
renderer.AddActor2D(scaleBar)

renderer.SetBackground(0.9, 0.9, 0.9) # Set background to white
print(scalar_range)
# Create the RendererWindow
renderer_window = vtkRenderWindow()
renderer_window.AddRenderer(renderer)
 
# Create the RendererWindowInteractor and display the vtk_file
interactor = vtkRenderWindowInteractor()
interactor.SetRenderWindow(renderer_window)
interactor.Initialize()
interactor.Start()