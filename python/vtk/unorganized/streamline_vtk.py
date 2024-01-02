
from vtk import *
from math import sqrt

file_name = "vector.vtk"

# Read the source file.
reader = vtk.vtkDataSetReader()
reader.SetFileName(file_name)
reader.Update() # Needed because of GetScalarRange
scalar_range = reader.GetStructuredPointsOutput().GetPointData().GetVectors().GetRange(-1)
id=reader.GetOutput()
print(reader.GetStructuredPointsOutput().GetPointData().GetVectors())
#---------------------------------------------------------------------------------
length=reader.GetOutput().GetBounds()
#---------------------------------------------------------------------------------

#Reduce the number of points to be plotted
mask = vtkMaskPoints()
mask.SetOnRatio(10)
mask.SetInput(id)
mask.Update()

#Set the source for stream lines
#x,y,z,nPoints,radius should be set by user, the following is default value
x=10
y=10
z=10
nPoints=10
radius=5

seeds=vtkPointSource()
seeds.SetCenter(x,y,z)
seeds.SetNumberOfPoints(nPoints)
seeds.SetRadius(radius)
#create stream lines
stream=vtkStreamLine()
stream.SetInputConnection(reader.GetOutputPort())
#---------------------------------------------------------------------------------
stream.SetStepLength(0.1/sqrt(scalar_range[0]*scalar_range[1]))
#---------------------------------------------------------------------------------
stream.SetIntegrationStepLength(0.1)
stream.SetNumberOfThreads(10)
stream.SetSource(seeds.GetOutput())
#---------------------------------------------------------------------------------
stream.SetMaximumPropagationTime(length[1]/sqrt(scalar_range[0]*scalar_range[1]))
#---------------------------------------------------------------------------------
stream.SpeedScalarsOn()
stream.SetIntegrationDirectionToForward()

#create the outer boundary of data
outline=vtkOutlineFilter()
outline.SetInput(reader.GetOutput())

#set the colormap based on vector's magnitude
# colormap=vtkColorTransferFunction()
# colormap.SetColorSpaceToLab()
# colormap.AddRGBPoint(scalar_range[0],0,0,1)
# colormap.AddRGBPoint(sum(scalar_range)/4,0,1,0)
# colormap.AddRGBPoint(sum(scalar_range)/2,1,0,0)
# colormap.Build()


color=vtkColorTransferFunction()
color.SetColorSpaceToLab()
diff=scalar_range[1]-scalar_range[0]
RGBPoint=3
RGBValue=[scalar_range[0],diff/2+scalar_range[0],scalar_range[1]]
RGB = [[0.0,0.0,1.0],[0.0,1.0,0.0],[1.0,0.0,0.0]]
for a in range(0,RGBPoint):
    color.AddRGBPoint(RGBValue[a],RGB[a][0],RGB[a][1],RGB[a][2])

print(color)
#Streamline mapper and outline mapper
streamMapper=vtkPolyDataMapper()
streamMapper.SetInputConnection(stream.GetOutputPort())
streamMapper.SetLookupTable(color)

outlineMapper=vtkDataSetMapper()
outlineMapper.SetInputConnection(outline.GetOutputPort())


# Create the Actor
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

streamActor=vtkActor()
streamActor.SetMapper(streamMapper)
streamActor.VisibilityOn()

# Create the Renderer
renderer = vtkRenderer()

renderer.AddActor(outlineActor)
renderer.AddActor(axes)
renderer.AddActor(streamActor)

scaleBar=vtkScalarBarActor()
scaleBar.SetLookupTable(color)
scaleBar.SetTitle("Scale Bar")
scaleBar.SetNumberOfLabels(RGBPoint)
scaleBar.GetTitleTextProperty().SetColor(0,0,0)
scaleBar.GetLabelTextProperty().SetColor(0,0,0)
renderer.AddActor2D(scaleBar)

renderer.SetBackground(0.6, 0.6, 0.6) # Set background to white

# Create the RendererWindow
renderer_window = vtkRenderWindow()
renderer_window.AddRenderer(renderer)
 
# Create the RendererWindowInteractor and display the vtk_file
interactor = vtkRenderWindowInteractor()
interactor.SetRenderWindow(renderer_window)
interactor.Initialize()
interactor.Start()