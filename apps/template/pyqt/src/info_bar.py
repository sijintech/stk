from PyQt5.QtWidgets import QMessageBox, QAction, QMenu, QFileDialog, QTextEdit,QWidget,QVBoxLayout,QTabWidget
from PyQt5.QtCore import Qt
import re

from center_widget import CenterWidget


class InfoBar(QWidget):

    def __init__(self,parent):

        super().__init__()
        self.parent=parent
        # self.center_widget=center_widget
        self.curShowCode=None
        self.curShowCodeType=None
        self.initUI()


    def initUI(self):

        layout = QVBoxLayout()

        self.tabWidget = QTabWidget()

        layout.addWidget(self.tabWidget)

        self.setLayout(layout)


        self.addInfoTabs()


    def addInfoTabs(self):
        self.codeTab = QTextEdit()
        self.tabWidget.addTab(self.codeTab, "Code")
        self.codeTab.setContextMenuPolicy(Qt.CustomContextMenu)
        self.codeTab.customContextMenuRequested.connect(self.showContextMenu)

        logTab = QTextEdit()
        self.tabWidget.addTab(logTab, "Log")


        consoleTab = QTextEdit()
        self.tabWidget.addTab(consoleTab, "Console")


        statusTab = QTextEdit()
        self.tabWidget.addTab(statusTab, "Status Information")


    def showContent(self, content):
        # 将文件内容显示在Code标签页中
        self.codeTab.setText(content)
        self.curShowCode=content
    def showContextMenu(self, pos):
        # 显示右键菜单
        menu = QMenu(self)
        
        runAction = QAction("Analyze and Run the current code", self)
        runAction.triggered.connect(self.runCodeWithAnalysis)
        menu.addAction(runAction)
 
        runAction = QAction("Run the current code directly (without analysis)", self)
        runAction.triggered.connect(self.runCodeWithoutAnalysis)
        menu.addAction(runAction)

        menu.exec_(self.codeTab.mapToGlobal(pos))
        
    def runCodeWithoutAnalysis(self):
        # 执行当前显示的原代码（独立运行，一般会打开新窗口显示）
        try:
            exec(self.curShowCode, globals(), locals())
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to execute script: {str(e)}")
            return
    def analyzeCode(self, curShowCode):
        # 使用正则表达式判断当前显示代码是否涉及到 vtk 或 matplotlib
        vtk_import = re.search(r'\bimport\s+vtk\b', curShowCode)
        matplotlib_import = re.search(r'\bimport\s+matplotlib\b', curShowCode)
        need_variable = None  # 用于存储提取的渲染器变量名
        # 如果涉及到 vtk 的代码
        if vtk_import:
            self.curShowCodeType = 'vtk'
            # 使用正则表达式查找赋值为 vtkRenderer() 的语句，并提取变量名
            need_variables = re.finditer(r'(\w+)\s*=\s*vtk\.vtkRenderer\(\)', curShowCode)
            for match in need_variables:
                need_variable=match.group(1)
            # 查找涉及到 vtk 渲染窗口和交互器的变量名
            vtk_vars = set()
            var_assignments = re.finditer(r'(\w+)\s*=\s*(vtk\.vtkRenderWindow|vtk\.vtkRenderWindowInteractor)\(\)', curShowCode)
            for match in var_assignments:
                vtk_vars.add(match.group(1))
            vtk_vars.add('vtkRenderWindow()')
            vtk_vars.add('vtkRenderWindowInteractor()')
            # print("vtk_vars:",vtk_vars)
            # 删除涉及到 vtk 渲染窗口和交互器的变量赋值语句以及相关的代码行
            curShowCode_lines = curShowCode.split('\n')  # 将代码按行拆分为列表
            updated_lines = []  # 用于存储更新后的代码行
            for line in curShowCode_lines:
                if any(var in line for var in vtk_vars):
                    continue  # 如果当前行涉及到 vtk 渲染窗口和交互器的变量，则跳过该行
                updated_lines.append(line)  # 否则添加到更新后的代码行列表中
            curShowCode = '\n'.join(updated_lines)  # 将更新后的代码行列表重新组合成字符串
        # 如果涉及到 matplotlib 的代码
        elif matplotlib_import:
            self.curShowCodeType = 'matplotlib'
        print(need_variable)
        return curShowCode,need_variable  # 返回处理后的代码字符串
    def runCodeWithAnalysis(self):
        # 分析当前显示的原代码提取出渲染器后再运行
        runCode,need_variable=self.analyzeCode(self.curShowCode)
        # self.parent.CenterWidget.runCode(runCode,self.curShowCodeType)
        self.parent.center_widget.runCodeWithAnalysis(runCode,self.curShowCodeType,need_variable)

