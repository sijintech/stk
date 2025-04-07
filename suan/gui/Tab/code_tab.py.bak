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

from custom_logger import CustomLogger


class CodeTab(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.logger = CustomLogger()
        self.curShowCode = None
        self.curShowCodeType = None
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        self.curShowCode = None

    def showContent(self, content):
        """显示代码内容"""
        self.curShowCode = content
        self.setText(content)
        codeIndex = self.parent.tabWidget.indexOf(self.parent.codeTab)
        self.parent.tabWidget.setCurrentIndex(codeIndex)

    def show_context_menu(self, pos):
        """显示右键菜单"""
        menu = QMenu(self)

        analyzeRunAction = QAction("Analyze and Run the current code", self)
        analyzeRunAction.triggered.connect(self.runCodeWithAnalysis)
        menu.addAction(analyzeRunAction)

        directRunAction = QAction("Run the current code directly (without analysis)", self)
        directRunAction.triggered.connect(self.runCodeWithoutAnalysis)
        menu.addAction(directRunAction)

        menu.exec_(self.mapToGlobal(pos))

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
        if self.getContentfromPath(self.parent.parent.curWorkFile) is None or self.getContentfromPath(
                self.parent.parent.curWorkFile) == self.toPlainText():
            return True
        else:
            return False

    def analyzeCode(self, curShowCode):

        variable_info = self.extract_variable_info(curShowCode)
        self.parent.parent.right_sidebar.updateData(variable_info)

        # 使用正则表达式判断当前显示代码是否涉及到 vtk 或 matplotlib
        vtk_import = re.search(r"(?<!#)\s*\bimport\s+vtk\b", curShowCode)
        if vtk_import is None:
            vtk_import = re.search(r"(?<!#)\s*\bfrom\s+vtk\b", curShowCode)

        matplotlib_import = re.search(r"(?<!#)\s*\bimport\s+matplotlib\b", curShowCode)
        need_variable = None  # 用于存储提取的渲染器变量名
        # 如果涉及到 vtk 的代码
        if vtk_import:
            # print("vtk")
            self.curShowCodeType = "vtk"
            # 使用正则表达式查找赋值为 vtkRenderer() 的语句，并提取变量名
            need_variables = re.finditer(
                r"(?<!#)\s*(\w+)\s*=\s*vtk\.vtkRenderer\(\w*\)", curShowCode
            )
            if need_variable is None:
                need_variables = re.finditer(
                    r"(?<!#)\s*(\w+)\s*=\s*vtkRenderer\(\w*\)", curShowCode
                )

            for match in need_variables:
                need_variable = match.group(1)
            # 查找涉及到 vtk 渲染窗口和交互器的变量名
            vtk_vars = set()
            var_assignments = re.finditer(
                r"(?<!#)\s*(\w+)\s*=\s*(vtk\.vtkRenderWindow|vtk\.vtkRenderWindowInteractor)\(\w*\)",
                curShowCode,
            )
            for match in var_assignments:
                vtk_vars.add(match.group(1))
            vtk_vars.add("vtkRenderWindow()")
            vtk_vars.add("vtkRenderWindowInteractor()")
            # print("vtk_vars:",vtk_vars)
            # 删除涉及到 vtk 渲染窗口和交互器的变量赋值语句以及相关的代码行
            curShowCode_lines = curShowCode.split("\n")  # 将代码按行拆分为列表
            # line_nums=len(curShowCode_lines)
            updated_lines = []  # 用于存储更新后的代码行
            for line in curShowCode_lines:
                if any(var in line for var in vtk_vars):
                    local_assignments = re.finditer(r"(?<!#)\s*(\w+)\s*=\s*\w*", line)
                    # if len(local_assignments)!=0:
                    for match in local_assignments:
                        vtk_vars.add(match.group(1))
                    continue  # 如果当前行涉及到 vtk 渲染窗口和交互器的变量，则跳过该行
                updated_lines.append(line)  # 否则添加到更新后的代码行列表中
            self.logger.debug("vtk_vars: %s", vtk_vars)
            curShowCode = "\n".join(
                updated_lines
            )  # 将更新后的代码行列表重新组合成字符串
        # 如果涉及到 matplotlib 的代码
        elif matplotlib_import:
            # print("mat")
            self.curShowCodeType = "matplotlib"
            # 使用正则表达式查找赋值为 figure() 的语句，并提取变量名
            need_variables = re.finditer(
                r"(?<!#)\s+(\w+)\s*=\s*\w*\.figure\(\)", curShowCode
            )
            for match in need_variables:
                need_variable = match.group(1)
            # 查找涉及到画布控件的变量名
            mat_vars = set()
            var_assignments = re.finditer(
                r"(?<!#)\s+(\w+)\s*=\s*\w*FigureCanvas\(\w*\)", curShowCode
            )
            for match in var_assignments:
                mat_vars.add(match.group(1))
            mat_vars.add("FigureCanvas()")
            self.logger.debug("mat_vars:", mat_vars)
            # 删除涉及到画布控件的变量赋值语句以及相关的代码行
            curShowCode_lines = curShowCode.split("\n")  # 将代码按行拆分为列表
            updated_lines = []  # 用于存储更新后的代码行
            for line in curShowCode_lines:
                if any(var in line for var in mat_vars):
                    continue  # 如果当前行涉及到画布控件的变量，则跳过该行
                updated_lines.append(line)  # 否则添加到更新后的代码行列表中
            curShowCode = "\n".join(
                updated_lines
            )  # 将更新后的代码行列表重新组合成字符串
        # print(need_variable)
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
        # 将当前代码段按行拆分成列表
        lines = self.curShowCode.split("\n")

        # 遍历变量信息字典
        for variable_name, info in variable_info.items():
            # 获取变量的初始值和位置信息
            initial_value = info["initial_value"]
            initial_value_position = info["initial_value_position"]

            # 更新代码段中对应变量的初始赋值为对应的 initial_value
            lines[initial_value_position - 1] = f"{variable_name} = {initial_value}"

        # 更新 self.curShowCode 为修改后的代码段
        self.curShowCode = "\n".join(lines)
        self.setText(self.curShowCode)

    def extract_variable_info(self, curShowCode):
        # 初始化变量信息字典
        variable_info = {}

        # 从代码中提取注释段
        match = re.search(r'"""(.+?)"""', curShowCode, re.DOTALL)
        if match:
            comment_block = match.group(1)

            # 匹配注释块中的变量声明信息
            pattern = r"@var\s+(\w+)\s+(\w+)"
            matches = re.findall(pattern, comment_block)

            # 遍历匹配结果
            for match in matches:
                variable_type = match[0]
                variable_name = match[1]
                variable_info[variable_name] = {
                    "type": variable_type,
                    "initial_value_position": None,
                    "initial_value": None,
                }

        # 按行分割代码
        lines = curShowCode.split("\n")

        # 初始化行号
        line_number = 0

        # 遍历代码行
        for line in lines:
            line_number += 1

            # 匹配变量赋值语句
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
