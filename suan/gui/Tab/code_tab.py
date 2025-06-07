from PySide6.QtWidgets import (
    QMessageBox,
    QMenu,
    QTextEdit,
    QWidget,
    QVBoxLayout,
    QTabWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
import os
import re

os.environ['QT_API'] = 'pyside6'
os.environ['FORCE_QT_API'] = 'PySide6'
from pyqode.core.api import CodeEdit
from pyqode.core.panels import LineNumberPanel
from pyqode.core import modes, api, panels
from custom_logger import CustomLogger
from pyqode.qt import QtWidgets


class CodeTab(QWidget):
    def __init__(self, parent=None):
        super().__init__()
        self.parent = parent
        self.logger = CustomLogger()
        self.curShowCode = None
        self.curShowCodeType = "python"
        self.encoding = 'utf-8'
        self.current_file = None

        self.editor = CodeEdit()

        self.editor.modes.append(modes.PygmentsSyntaxHighlighter(self.editor.document()))
        self.editor.modes.append(modes.CodeCompletionMode())
        self.editor.modes.append(modes.CaretLineHighlighterMode())

        self.editor.panels.append(LineNumberPanel())
        self.editor.panels.append(panels.SearchAndReplacePanel(),
                                  api.Panel.Position.BOTTOM)

        self.editor.setTabStopWidth(4)
        self.editor.setLineWrapMode(CodeEdit.NoWrap)
        self.show_context_menu()

        layout = QVBoxLayout(self)
        layout.addWidget(self.editor)

        self.setLayout(layout)

    def showContent(self, content):
        """显示代码内容"""
        self.curShowCode = content
        self.editor.setPlainText(content, "text/plain", self.encoding)
        codeIndex = self.parent.tabWidget.indexOf(self.parent.codeTab)
        self.parent.tabWidget.setCurrentIndex(codeIndex)

    def toPlainText(self):
        return self.editor.toPlainText()

    def setTest(self, content):
        self.editor.setPlainText(content, "text/plain", self.encoding)

    def show_context_menu(self):
        """显示右键菜单"""

        analyzeRunAction = QAction("Analyze and Run the current code", self)
        analyzeRunAction.triggered.connect(self.runCodeWithAnalysis)

        self.editor.add_action(analyzeRunAction, 'RUN')

        directRunAction = QAction("Run the current code directly (without analysis)", self)
        directRunAction.triggered.connect(self.runCodeWithoutAnalysis)

        self.editor.add_action(directRunAction, 'RUN')

    def runCodeWithoutAnalysis(self):
        """直接运行当前代码"""
        if self.curShowCode:
            self.execute_code_with_file_path(
                self.curShowCode, self.parent.parent.curWorkFile, globals(), locals()
            )

    def runCodeWithAnalysis(self):
        """分析代码后运行"""
        if self.curShowCode:
            runCode, need_variable = self.analyzeCode(self.curShowCode)
            self.parent.parent.center_widget.runCodeWithAnalysis(
                runCode, self.curShowCodeType, need_variable
            )

    def getContentfromPath(self, path):
        self.logger.debug(path)
        if path == '':
            return None
        try:
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
                return content
        except Exception as e:
            self.logger.error("Error reading file: %s", e)
            return None

    def curFileIsSave(self):
        self.logger.debug(f"当前文件：{self.parent.parent.curWorkFile}")
        comment = self.editor.toPlainText()
        if self.getContentfromPath(self.parent.parent.curWorkFile) is None or self.getContentfromPath(
                self.parent.parent.curWorkFile) == comment:
            return True
        else:
            return False

    def analyzeCode(self, curShowCode):

        variable_info = self.extract_variable_info(curShowCode)
        self.parent.parent.right_sidebar.updateData(variable_info)

        vtk_import = re.search(r"(?<!#)\s*\bimport\s+vtk\b", curShowCode)
        if vtk_import is None:
            vtk_import = re.search(r"(?<!#)\s*\bfrom\s+vtk\b", curShowCode)

        matplotlib_import = re.search(r"(?<!#)\s*\bimport\s+matplotlib\b", curShowCode)
        need_variable = None  # 用于存储提取的渲染器变量名

        if vtk_import:

            self.curShowCodeType = "vtk"

            need_variables = re.finditer(
                r"(?<!#)\s*(\w+)\s*=\s*vtk\.vtkRenderer\(\w*\)", curShowCode
            )
            if need_variable is None:
                need_variables = re.finditer(
                    r"(?<!#)\s*(\w+)\s*=\s*vtkRenderer\(\w*\)", curShowCode
                )

            for match in need_variables:
                need_variable = match.group(1)

            vtk_vars = set()
            var_assignments = re.finditer(
                r"(?<!#)\s*(\w+)\s*=\s*(vtk\.vtkRenderWindow|vtk\.vtkRenderWindowInteractor)\(\w*\)",
                curShowCode,
            )
            for match in var_assignments:
                vtk_vars.add(match.group(1))
            vtk_vars.add("vtkRenderWindow()")
            vtk_vars.add("vtkRenderWindowInteractor()")

            curShowCode_lines = curShowCode.split("\n")  # 将代码按行拆分为列表

            updated_lines = []  # 用于存储更新后的代码行
            for line in curShowCode_lines:
                if any(var in line for var in vtk_vars):
                    local_assignments = re.finditer(r"(?<!#)\s*(\w+)\s*=\s*\w*", line)

                    for match in local_assignments:
                        vtk_vars.add(match.group(1))
                    continue  # 如果当前行涉及到 vtk 渲染窗口和交互器的变量，则跳过该行
                updated_lines.append(line)  # 否则添加到更新后的代码行列表中
            self.logger.debug("vtk_vars: %s", vtk_vars)
            curShowCode = "\n".join(
                updated_lines
            )  # 将更新后的代码行列表重新组合成字符串

        elif matplotlib_import:

            self.curShowCodeType = "matplotlib"

            need_variables = re.finditer(
                r"(?<!#)\s+(\w+)\s*=\s*\w*\.figure\(\)", curShowCode
            )
            for match in need_variables:
                need_variable = match.group(1)

            mat_vars = set()
            var_assignments = re.finditer(
                r"(?<!#)\s+(\w+)\s*=\s*\w*FigureCanvas\(\w*\)", curShowCode
            )
            for match in var_assignments:
                mat_vars.add(match.group(1))
            mat_vars.add("FigureCanvas()")
            self.logger.debug("mat_vars:", mat_vars)

            curShowCode_lines = curShowCode.split("\n")  # 将代码按行拆分为列表
            updated_lines = []  # 用于存储更新后的代码行
            for line in curShowCode_lines:
                if any(var in line for var in mat_vars):
                    continue  # 如果当前行涉及到画布控件的变量，则跳过该行
                updated_lines.append(line)  # 否则添加到更新后的代码行列表中
            curShowCode = "\n".join(
                updated_lines
            )  # 将更新后的代码行列表重新组合成字符串

        return curShowCode, need_variable  # 返回处理后的代码字符串

    def execute_code_with_file_path(self, code_string, file_path, global_vals, local_vals):
        """执行代码"""
        script_directory = os.path.dirname(os.path.abspath(file_path))
        original_directory = os.getcwd()
        os.chdir(script_directory)

        modified_code = code_string.replace("__file__", f'"{file_path}"')
        try:
            exec(modified_code, global_vals, local_vals)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to execute script: {str(e)}")
        finally:
            os.chdir(original_directory)

    def update_initial_value(self, variable_info):

        lines = self.curShowCode.split("\n")

        for variable_name, info in variable_info.items():
            initial_value = info["initial_value"]
            initial_value_position = info["initial_value_position"]

            lines[initial_value_position - 1] = f"{variable_name} = {initial_value}"

        self.curShowCode = "\n".join(lines)
        self.setText(self.curShowCode)

    def extract_variable_info(self, curShowCode):

        variable_info = {}

        match = re.search(r'"""(.+?)"""', curShowCode, re.DOTALL)
        if match:
            comment_block = match.group(1)

            pattern = r"@var\s+(\w+)\s+(\w+)"
            matches = re.findall(pattern, comment_block)

            for match in matches:
                variable_type = match[0]
                variable_name = match[1]
                variable_info[variable_name] = {
                    "type": variable_type,
                    "initial_value_position": None,
                    "initial_value": None,
                }

        lines = curShowCode.split("\n")

        line_number = 0

        for line in lines:
            line_number += 1

            assignment_match = re.search(r"\b(\w+)\s*=\s*(.+)", line)
            if assignment_match:
                assigned_variable = assignment_match.group(1)
                if (
                        assigned_variable in variable_info
                        and variable_info[assigned_variable]["initial_value_position"]
                        is None
                ):
                    variable_info[assigned_variable][
                        "initial_value_position"
                    ] = line_number
                    variable_info[assigned_variable]["initial_value"] = (
                        assignment_match.group(2).strip()
                    )

        return variable_info

    def save_if_auto(self):
        """如果开启了自动保存且当前文件已被修改，则保存文件"""
        if not self.parent or not hasattr(self.parent, 'parent'):
            return False
            
        parent_window = self.parent.parent

        if not hasattr(parent_window, 'preferences') or parent_window.preferences is None:
            return False

        auto_save = parent_window.preferences.get("Auto_Save", True)

        if not hasattr(self, 'current_file'):

            if hasattr(parent_window, 'curWorkFile'):
                current_file = parent_window.curWorkFile
            else:
                return False
        else:
            current_file = self.current_file

        if auto_save and not self.curFileIsSave() and current_file:
            parent_window.logger.debug(f"自动保存文件: {current_file}")
            self.save_file()
            return True
        return False

    def save_file(self):
        """保存当前文件"""
        try:

            if hasattr(self, 'current_file') and self.current_file:
                file_path = self.current_file
            elif hasattr(self.parent, 'parent') and hasattr(self.parent.parent, 'curWorkFile'):
                file_path = self.parent.parent.curWorkFile
            else:
                self.logger.error("没有可保存的文件路径")
                return False

            content = self.editor.toPlainText()

            with open(file_path, "w", encoding=self.encoding) as file:
                file.write(content)
                
            self.logger.debug(f"文件已保存: {file_path}")
            return True
        except Exception as e:
            self.logger.error(f"保存文件失败: {e}")
            return False
