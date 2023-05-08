
# -*- coding: utf-8 -*-
"""
Created on Tue Aug 23 22:43:40 2016

@author: cxx
"""

# =======================

import vtk


# The Wavelet Source is nice for generating a test vtkImageData set
rt = vtk.vtkRTAnalyticSource()
rt.SetWholeExtent(-5,5,-5,5,-5,5)
rt.SetXFreq(0)
rt.SetYFreq(0)
rt.SetZFreq(0)
rt.SetXMag(10)
rt.SetYMag(10)
rt.SetZMag(10)
rt.Update()
# Take the gradient of the only scalar 'RTData' to get a vector attribute

contour = vtk.vtkContourFilter()
contour.SetInputConnection(rt.GetOutputPort())
contour.SetValue(0,200)
contour.Update()
mapper = vtk.vtkPolyDataMapper()
ren = vtk.vtkRenderer()

rgb=vtk.vtkFloatArray()
rgb.SetNumberOfComponents(3)
rgb.SetName("RGB")

for i in range(0,270):
    R=contour.GetOutput().GetPointData().GetNormals().GetTuple(i)[0]
    G=contour.GetOutput().GetPointData().GetNormals().GetTuple(i)[1]
    B=contour.GetOutput().GetPointData().GetNormals().GetTuple(i)[2]
    rgb.InsertNextTuple3(R,G,B)

contour.GetOutput().GetPointData().AddArray(rgb)
contourAssign = vtk.vtkAssignAttribute()
contourAssign.SetInputConnection(contour.GetOutputPort())
contourAssign.Assign('RGB', \
               vtk.vtkDataSetAttributes.VECTORS, \
               vtk.vtkAssignAttribute.POINT_DATA)
contourAssign.Update()
# Generate a lookup table for coloring by vector components or magnitude
lut = vtk.vtkLookupTable()
# When using a vector component for coloring
lut.SetVectorModeToRGBColors()
#lut.SetVectorComponent(2)
# When using vector magnitude for coloring
# lut.SetVectorModeToMagnitude()
lut.Build()
  
mapper.SetInputConnection(contourAssign.GetOutputPort())
mapper.SetLookupTable(lut)
mapper.ScalarVisibilityOn()
mapper.SetScalarModeToUsePointFieldData()
mapper.SetColorModeToDirectScalars()
mapper.SelectColorArray('RGB')
# When using a vector component for coloring
mapper.SetScalarRange([0,1])
# When using vector magnitude for coloring
# mapper.SetScalarRange(assign.GetOutput().GetPointData().GetVectors().GetRange(-1))

actor = vtk.vtkActor()
actor.SetMapper(mapper)

# outline
outline = vtk.vtkOutlineFilter()
outline.SetInputConnection(contour.GetOutputPort())
mapper2 = vtk.vtkPolyDataMapper()
mapper2.SetInputConnection(outline.GetOutputPort())
actor2 = vtk.vtkActor()
actor2.SetMapper(mapper2)

ren.AddActor(actor)
ren.AddActor(actor2)
renWin = vtk.vtkRenderWindow()
renWin.AddRenderer(ren)
iren = vtk.vtkRenderWindowInteractor()
istyle = vtk.vtkInteractorStyleTrackballCamera()
iren.SetInteractorStyle(istyle)
iren.SetRenderWindow(renWin)
ren.ResetCamera()
renWin.Render()

iren.Start()