import vtk

# 创建一个圆锥源
cone_source = vtk.vtkConeSource()
cone_source.SetCenter(0, 0, 0)
cone_source.SetRadius(1.0)
cone_source.SetHeight(2.0)

# 创建一个mapper
mapper = vtk.vtkPolyDataMapper()
mapper.SetInputConnection(cone_source.GetOutputPort())

# 创建一个actor
actor = vtk.vtkActor()
actor.SetMapper(mapper)

# 创建一个渲染器
renderer = vtk.vtkRenderer()
renderer.AddActor(actor)

# 创建一个交互器
interactor = vtk.vtkRenderWindowInteractor()
interactor.SetInteractorStyle(vtk.vtkInteractorStyleTrackballCamera())

# 创建一个渲染窗口
render_window = vtk.vtkRenderWindow()
render_window.AddRenderer(renderer)

# 将渲染窗口设置给交互器
interactor.SetRenderWindow(render_window)

# 初始化交互器
interactor.Initialize()

# 启动交互
interactor.Start()