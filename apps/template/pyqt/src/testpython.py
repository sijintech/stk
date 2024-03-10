# from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTabWidget
# from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
# import re
# import vtk
# import matplotlib.pyplot as plt
# from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg

# class CustomFigureCanvas(FigureCanvasQTAgg):
#     def __init__(self, figure=None):
#         super().__init__(figure)
#         self._figure = None  # 用于保存 Figure 对象的成员变量

#     def setFigure(self, fig):
#         # 清除当前画布上的所有内容
#         self.figure.clf()
#         # 关联新的 Figure 对象
#         self._figure = fig
#         # 重新构造 FigureCanvasQTAgg 对象并关联新的 Figure 对象
#         self.__init__(fig)

#     def getFigure(self):
#         return self._figure
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
#             local_vars = {}
#             global_vars = {'plt': plt}
#             exec(self.runCode, global_vars, local_vars)
#             fig = local_vars.get('fig')
#             self.matplotlibWidget = CustomFigureCanvas()  # 创建画布控件
#             self.matplotlibWidget.setFigure(fig)
#             # 创建matplotlib可视化Tab并将 matplotlib_widget 添加到其中
#             matplotlibDisplayTab = QWidget()
#             matplotlibLayout = QVBoxLayout()
#             matplotlibLayout.addWidget(self.matplotlibWidget)
#             matplotlibDisplayTab.setLayout(matplotlibLayout)

#             self.tabWidget.addTab(matplotlibDisplayTab, "Matplotlib Display")


#     def analyzeCode(self, curShowCode):
#         # 使用正则表达式判断当前显示代码是否涉及到 vtk 或 matplotlib
#         vtk_import = re.search(r'\bimport\s+vtk\b', curShowCode)
#         matplotlib_import = re.search(r'\bimport\s+matplotlib\b', curShowCode)
#         need_variable = None  # 用于存储提取的渲染器变量名
#         # 如果涉及到 vtk 的代码
#         if vtk_import:
#             self.curShowCodeType = 'vtk'
#             # 使用正则表达式查找赋值为 vtkRenderer() 的语句，并提取变量名
#             need_variables = re.finditer(r'(\w+)\s*=\s*vtk\.vtkRenderer\(\)', curShowCode)
#             for match in need_variables:
#                 need_variable=match.group(1)
#             # 查找涉及到 vtk 渲染窗口和交互器的变量名
#             vtk_vars = set()
#             var_assignments = re.finditer(r'(\w+)\s*=\s*(vtk\.vtkRenderWindow|vtk\.vtkRenderWindowInteractor)\(\)', curShowCode)
#             for match in var_assignments:
#                 vtk_vars.add(match.group(1))
#             vtk_vars.add('vtkRenderWindow()')
#             vtk_vars.add('vtkRenderWindowInteractor()')
#             # print("vtk_vars:",vtk_vars)
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
#             # 使用正则表达式查找赋值为 figure() 的语句，并提取变量名
#             need_variables = re.finditer(r'(\w+)\s*=\s*\w*\.figure\(\)', curShowCode)
#             for match in need_variables:
#                 need_variable=match.group(1)
#             # 查找涉及到画布控件的变量名
#             vtk_vars = set()
#             var_assignments = re.finditer(r'(\w+)\s*=\s*\w*FigureCanvas\(\w*\)', curShowCode)
#             for match in var_assignments:
#                 vtk_vars.add(match.group(1))
#             vtk_vars.add('FigureCanvas()')
#             print("vtk_vars:",vtk_vars)
#             # 删除涉及到 vtk 渲染窗口和交互器的变量赋值语句以及相关的代码行
#             curShowCode_lines = curShowCode.split('\n')  # 将代码按行拆分为列表
#             updated_lines = []  # 用于存储更新后的代码行
#             for line in curShowCode_lines:
#                 if any(var in line for var in vtk_vars):
#                     continue  # 如果当前行涉及到 vtk 渲染窗口和交互器的变量，则跳过该行
#                 updated_lines.append(line)  # 否则添加到更新后的代码行列表中
#             curShowCode = '\n'.join(updated_lines)  # 将更新后的代码行列表重新组合成字符串

#         print(need_variable)
#         return curShowCode,need_variable  # 返回处理后的代码字符串

# # 运行主窗口
# if __name__ == '__main__':
#     import sys
#     from PyQt5.QtWidgets import QApplication

#     app = QApplication(sys.argv)
#     mainWindow = CenterWidget(None)
#     runCode = """
# import sys
# import numpy as np
# from qtpy.QtWidgets import QApplication  # qtpy会以PyQt5,PyQt6,PySide2,PySide6的顺序依次尝试import。
# from matplotlib.backends.backend_qtagg import FigureCanvas
# import matplotlib.pyplot as plt
# fig = plt.figure()  # 创建figure
# ax = fig.subplots()
# t = np.linspace(0, np.pi, 50)
# ax.plot(t, np.sin(t))  # 画曲线（在窗口显示之后画也可以）
# win = FigureCanvas(fig)  # 创建画布控件
# win.show()  # 画布控件作为窗口显示
# """
#     code,_=mainWindow.analyzeCode(runCode)
#     print(code)
#     mainWindow.runCode=code
#     mainWindow.addMainOperationTabs()
#     mainWindow.show()
#     sys.exit(app.exec_())

import sys
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt
fig = plt.figure()  # 创建figure
ax = fig.subplots()
t = np.linspace(0, np.pi, 50)
ax.plot(t, np.sin(t))  # 画曲线（在窗口显示之后画也可以）
win = FigureCanvas(fig)  # 创建画布控件
win.show()  # 画布控件作为窗口显示