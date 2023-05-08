# -*- coding: utf-8 -*-
"""
Created on Wed Feb  4 10:30:11 2015

@author: cxx
"""
from vtk import *

fileName = "vector.vtk"
reader = vtk.vtkDataSetReader()
reader.SetFileName(fileName)
reader.Update()

id = reader.GetOutput()


arrow = vtkArrowSource()
arrow.Update()
glyph = vtkGlyph3D()
glyph.SetSourceConnection(arrow.GetOutputPort())
glyph.SetInput(id)
glyph.OrientOn
glyph.SetVectorModeToUseVector()
glyph.SetColorModeToColorByVector()
glyph.SetScaleModeToScaleByVector()
glyph.SetScaleFactor(4)

mapper=vtkDataSetMapper()
mapper.SetInputConnection(glyph.GetOutputPort())

actor = vtkActor()
actor.SetMapper(mapper)
actor.GetProperty().SetOpacity(0.5)
actor.GetProperty().SetRepresentationToSurface()

renderer = vtkRenderer()
renderer.AddActor(actor)
renderer.SetBackground(1,1,1)

renWin = vtkRenderWindow()
renWin.AddRenderer(renderer)


interactor = vtkRenderWindowInteractor()
istyle = vtk.vtkInteractorStyleSwitch()
interactor.SetInteractorStyle(istyle)
istyle.SetCurrentStyleToTrackballCamera()
interactor.SetRenderWindow(renWin)
interactor.Initialize()
interactor.Start()