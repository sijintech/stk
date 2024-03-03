# from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTabWidget
# from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
# import vtk
# import re

# class CenterWidget(QWidget):
#     def __init__(self, parent):
#         super().__init__(parent)
#         self.runCode = None
#         self.initUI()

#     def initUI(self):
#         layout = QVBoxLayout()
#         self.tabWidget = QTabWidget()
#         layout.addWidget(self.tabWidget)
#         self.setLayout(layout)

#         self.addMainOperationTabs()

#     def addMainOperationTabs(self):
#         # 执行第一个脚本并传递 renderer 变量
#         if self.runCode:
#             print("renderer")
#             local_vars = {}
#             global_vars = {'vtk': vtk}
#             exec(self.runCode, global_vars, local_vars)
#             renderer = local_vars.get('renderer')
#             if renderer:
#                 print("aaaaaaaa")
#                 # 创建VTK渲染器
#                 self.vtkWidget = QVTKRenderWindowInteractor()  # 创建VTK渲染窗口交互器
#                 self.vtkWidget.Initialize()
#                 self.vtkWidget.GetRenderWindow().AddRenderer(renderer)  # 将渲染器添加到渲染窗口

#                 self.vtkWidget.GetRenderWindow().Render()  # 渲染一次

#                 # 创建VTK可视化Tab并将 vtk_widget 添加到其中
#                 vtk_visualization_tab = QWidget()
#                 vtk_layout = QVBoxLayout()
#                 vtk_layout.addWidget(self.vtkWidget)
#                 vtk_visualization_tab.setLayout(vtk_layout)
#                 self.tabWidget.addTab(vtk_visualization_tab, "VTK Visualization")


#     def analyzeCode(self, curShowCode):
#     # 使用正则表达式判断当前显示代码是否涉及到 vtk 或 matplotlib
#         vtk_import = re.search(r'\bimport\s+vtk\b', curShowCode)
#         matplotlib_import = re.search(r'\bimport\s+matplotlib\b', curShowCode)

#         # 如果涉及到 vtk 的代码
#         if vtk_import:
#             self.curShowCodeType = 'vtk'
#             # 查找涉及到 vtk 渲染窗口和交互器的变量名
#             vtk_vars = set()
#             var_assignments = re.finditer(r'(\w+)\s*=\s*(vtk\.vtkRenderWindow|vtk\.vtkRenderWindowInteractor)\(\)', curShowCode)
#             for match in var_assignments:
#                 vtk_vars.add(match.group(1))
#             vtk_vars.add('vtkRenderWindow()')
#             vtk_vars.add('vtkRenderWindowInteractor()')
#             print("vtk_vars:",vtk_vars)
#             # 删除涉及到 vtk 渲染窗口和交互器的变量赋值语句以及相关的代码行
#             curShowCode_lines = curShowCode.split('\n')  # 将代码按行拆分为列表
#             updated_lines = []  # 用于存储更新后的代码行
#             for line in curShowCode_lines:
#                 if any(var in line for var in vtk_vars):
#                     continue  # 如果当前行涉及到 vtk 渲染窗口和交互器的变量，则跳过该行
#                 updated_lines.append(line)  # 否则添加到更新后的代码行列表中
#             curShowCode = '\n'.join(updated_lines)  # 将更新后的代码行列表重新组合成字符串
#         # 如果涉及到 matplotlib 的代码
#         elif matplotlib_import:
#             self.curShowCodeType = 'matplotlib'

#         return curShowCode  # 返回处理后的代码字符串
# # 运行主窗口
# if __name__ == '__main__':
#     import sys
#     from PyQt5.QtWidgets import QApplication

#     app = QApplication(sys.argv)
#     mainWindow = CenterWidget(None)
#     runCode = """
# import vtk

# # 创建一个圆锥源
# cone_source = vtk.vtkConeSource()
# cone_source.SetCenter(0, 0, 0)
# cone_source.SetRadius(1.0)
# cone_source.SetHeight(2.0)

# # 创建一个mapper
# mapper = vtk.vtkPolyDataMapper()
# mapper.SetInputConnection(cone_source.GetOutputPort())

# # 创建一个actor
# actor = vtk.vtkActor()
# actor.SetMapper(mapper)

# # 创建一个渲染器
# renderer = vtk.vtkRenderer()
# renderer.AddActor(actor)

# # 创建一个交互器
# interactor = vtk.vtkRenderWindowInteractor()
# interactor.SetInteractorStyle(vtk.vtkInteractorStyleTrackballCamera())

# # 创建一个渲染窗口
# render_window = vtk.vtkRenderWindow()
# render_window.AddRenderer(renderer)

# # 将渲染窗口设置给交互器
# interactor.SetRenderWindow(render_window)

# # 初始化交互器
# interactor.Initialize()

# # 启动交互
# interactor.Start()
# """
#     code=mainWindow.analyzeCode(runCode)
#     print(code)
#     mainWindow.runCode=code
#     mainWindow.addMainOperationTabs()
#     mainWindow.show()
#     sys.exit(app.exec_())


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