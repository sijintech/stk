  
from vtk import *

file_name = "tensor.vtk"

# Read the source file.
reader = vtk.vtkDataSetReader()
reader.SetFileName(file_name)
reader.Update()
id = reader.GetOutput()
scalar_range=id.GetPointData().GetArray(0).GetRange(-1)
print(scalar_range)

#Reduce the amount of points to be plotted, using maskPoints
mask = vtkMaskPoints()
mask.SetInputConnection(reader.GetOutputPort())
mask.SetOnRatio(2)
mask.SetMaximumNumberOfPoints(10000000)
mask.RandomModeOn()
mask.Update()

#Making tensor glyph with superquadratic glyph

tensor11=vtkExtractTensorComponents()
tensor11.SetInputConnection(reader.GetOutputPort())
tensor11.ExtractScalarsOn()
tensor11.PassTensorsToOutputOff()
tensor11.SetScalarComponents(0,0)
tensor11.Update()

tensor12=vtkExtractTensorComponents()
tensor12.SetInputConnection(reader.GetOutputPort())
tensor12.ExtractScalarsOn()
tensor12.SetScalarComponents(0,1)

tensor13=vtkExtractTensorComponents()
tensor13.SetInputConnection(reader.GetOutputPort())
tensor13.ExtractScalarsOn()
tensor13.SetScalarComponents(0,2)

tensor22=vtkExtractTensorComponents()
tensor22.SetInputConnection(reader.GetOutputPort())
tensor22.ExtractScalarsOn()
tensor22.SetScalarComponents(1,1)

tensor23=vtkExtractTensorComponents()
tensor23.SetInputConnection(reader.GetOutputPort())
tensor23.ExtractScalarsOn()
tensor23.SetScalarComponents(1,2)

tensor33=vtkExtractTensorComponents()
tensor33.SetInputConnection(reader.GetOutputPort())
tensor33.ExtractScalarsOn()
tensor33.SetScalarComponents(2,2)
#tensor glyph mapper
mapper11 = vtkSmartVolumeMapper()
mapper11.SetInputConnection(tensor11.GetOutputPort())

mapper12 = vtkSmartVolumeMapper()
mapper12.SetInputConnection(tensor12.GetOutputPort())
mapper13 = vtkSmartVolumeMapper()
mapper13.SetInputConnection(tensor13.GetOutputPort())
mapper22 = vtkSmartVolumeMapper()
mapper22.SetInputConnection(tensor22.GetOutputPort())
mapper23 = vtkSmartVolumeMapper()
mapper23.SetInputConnection(tensor23.GetOutputPort())
mapper33 = vtkSmartVolumeMapper()
mapper33.SetInputConnection(tensor33.GetOutputPort())



actor11 = vtkVolume()
actor11.SetMapper(mapper11)
actor12 = vtkVolume()
actor12.SetMapper(mapper12)
actor13 = vtkVolume()
actor13.SetMapper(mapper13)
actor21 = vtkVolume()
actor21.SetMapper(mapper12)
actor22 = vtkVolume()
actor22.SetMapper(mapper22)
actor23 = vtkVolume()
actor23.SetMapper(mapper23)
actor31 = vtkVolume()
actor31.SetMapper(mapper13)
actor32 = vtkVolume()
actor32.SetMapper(mapper23)
actor33 = vtkVolume()
actor33.SetMapper(mapper33)



volumeProperty=vtkVolumeProperty()
color=vtkColorTransferFunction()
color.SetColorSpaceToLab()

opacity=vtkPiecewiseFunction()
diff=scalar_range[1]-scalar_range[0]
opacityPoint=6
opValue=[scalar_range[0],scalar_range[0]+diff/8,diff/8+scalar_range[0],6*diff/8+scalar_range[0],6*diff/8+scalar_range[0],scalar_range[1]]
alpha=[0.1,0.1,0.0,0.0,0.1,0.1]
for a in range(0,opacityPoint):
    opacity.AddPoint(opValue[a],alpha[a])

RGBPoint=3
RGBValue=[scalar_range[0],diff/20+scalar_range[0],scalar_range[1]]
RGB = [[0.0,0.0,1.0],[0.0,1.0,0.0],[1.0,0.0,0.0]]
for a in range(0,RGBPoint):
    color.AddRGBPoint(RGBValue[a],RGB[a][0],RGB[a][1],RGB[a][2])
volumeProperty.SetScalarOpacity(opacity)
#------------------------------------------------------------------------------
volumeProperty.SetColor(color)

volumeProperty.SetInterpolationTypeToNearest()

actor11.SetProperty(volumeProperty)
actor12.SetProperty(volumeProperty)
actor13.SetProperty(volumeProperty)
actor21.SetProperty(volumeProperty)
actor22.SetProperty(volumeProperty)
actor23.SetProperty(volumeProperty)
actor31.SetProperty(volumeProperty)
actor32.SetProperty(volumeProperty)
actor33.SetProperty(volumeProperty)

#create the outer boundary of the data
outline=vtkOutlineFilter()
outline.SetInput(reader.GetOutput())
outlineMapper=vtkDataSetMapper()
outlineMapper.SetInputConnection(outline.GetOutputPort())
outlineActor=vtkActor()
outlineActor.SetMapper(outlineMapper)
outlineActor.GetProperty().SetColor(0,0,0)



xmins=[0,0.333333,0.666667]
xmaxs=[0.333333,0.666667,1]
ymins=[0,0.333333,0.666667]
ymaxs=[0.333333,0.666667,1]

camera=vtkCamera()
camera.SetPosition(0,0,400)
camera.SetFocalPoint(0,0,0)
renderer11 = vtkRenderer()
renderer12 = vtkRenderer()
renderer13 = vtkRenderer()
renderer21 = vtkRenderer()
renderer22 = vtkRenderer()
renderer23 = vtkRenderer()
renderer31 = vtkRenderer()
renderer32 = vtkRenderer()
renderer33 = vtkRenderer()

renderer11.SetActiveCamera(camera)
renderer12.SetActiveCamera(camera)
renderer13.SetActiveCamera(camera)
renderer21.SetActiveCamera(camera)
renderer22.SetActiveCamera(camera)
renderer23.SetActiveCamera(camera)
renderer31.SetActiveCamera(camera)
renderer32.SetActiveCamera(camera)
renderer33.SetActiveCamera(camera)

renderer11.SetViewport(xmins[0],ymins[2],xmaxs[0],ymaxs[2])
renderer12.SetViewport(xmins[1],ymins[2],xmaxs[1],ymaxs[2])
renderer13.SetViewport(xmins[2],ymins[2],xmaxs[2],ymaxs[2])
renderer21.SetViewport(xmins[0],ymins[1],xmaxs[0],ymaxs[1])
renderer22.SetViewport(xmins[1],ymins[1],xmaxs[1],ymaxs[1])
renderer23.SetViewport(xmins[2],ymins[1],xmaxs[2],ymaxs[1])
renderer31.SetViewport(xmins[0],ymins[0],xmaxs[0],ymaxs[0])
renderer32.SetViewport(xmins[1],ymins[0],xmaxs[1],ymaxs[0])
renderer33.SetViewport(xmins[2],ymins[0],xmaxs[2],ymaxs[0])

renderer11.AddActor(actor11)
renderer11.AddActor(outlineActor)
renderer11.SetBackground(1, 1, 1) # Set background to white

renderer12.AddActor(actor12)
renderer12.AddActor(outlineActor)
renderer12.SetBackground(1, 1, 1) # Set background to white

renderer13.AddActor(actor13)
renderer13.AddActor(outlineActor)
renderer13.SetBackground(1, 1, 1) # Set background to white

renderer21.AddActor(actor21)
renderer21.AddActor(outlineActor)
renderer21.SetBackground(1, 1, 1) # Set background to white

renderer22.AddActor(actor22)
renderer22.AddActor(outlineActor)
renderer22.SetBackground(1, 1, 1) # Set background to white

renderer23.AddActor(actor23)
renderer23.AddActor(outlineActor)
renderer23.SetBackground(1, 1, 1) # Set background to white

renderer31.AddActor(actor31)
renderer31.AddActor(outlineActor)
renderer31.SetBackground(1, 1, 1) # Set background to white

renderer32.AddActor(actor32)
renderer32.AddActor(outlineActor)
renderer32.SetBackground(1, 1, 1) # Set background to white

renderer33.AddActor(actor33)
renderer33.AddActor(outlineActor)
renderer33.SetBackground(1, 1, 1) # Set background to white

renderer=vtkRenderer()
renderer.SetViewport(0.9,0,xmaxs[2],ymaxs[2])
#-------------------------------------------------------------------------------
#20140820
scaleBar=vtkScalarBarActor()
scaleBar.SetLookupTable(color)
scaleBar.SetTitle("Scale Bar")
scaleBar.SetNumberOfLabels(RGBPoint)
scaleBar.GetTitleTextProperty().SetColor(0,0,0)
scaleBar.GetLabelTextProperty().SetColor(0,0,0)
renderer12.AddActor2D(scaleBar)
#-------------------------------------------------------------------------------
renWin = vtkRenderWindow()

renWin.AddRenderer(renderer11)
renWin.AddRenderer(renderer12)
renWin.AddRenderer(renderer13)
renWin.AddRenderer(renderer21)
renWin.AddRenderer(renderer22)
renWin.AddRenderer(renderer23)
renWin.AddRenderer(renderer31)
renWin.AddRenderer(renderer32)
renWin.AddRenderer(renderer33)
interactor = vtkRenderWindowInteractor()
interactor.SetRenderWindow(renWin)

interactor.Initialize()

renWin.Render()

interactor.Start()