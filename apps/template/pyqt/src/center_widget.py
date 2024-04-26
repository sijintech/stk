from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QTabWidget,
    QTableWidgetItem,
    QPushButton,
    QTableWidget,
    QMenu,
)
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
import vtk
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
import matplotlib.pyplot as plt
import toml
from PySide6.QtCore import Qt


class CustomFigureCanvas(FigureCanvasQTAgg):
    def __init__(self, figure=None):
        super().__init__(figure)
        self._figure = None  # 用于保存 Figure 对象的成员变量

    def setFigure(self, fig):
        # 清除当前画布上的所有内容
        self.figure.clf()
        # 关联新的 Figure 对象
        self._figure = fig
        # 重新构造 FigureCanvasQTAgg 对象并关联新的 Figure 对象
        self.__init__(fig)

    def getFigure(self):
        return self._figure


ColumnCount = 7


class PreferenceTab(QWidget):
    def __init__(self, data):
        super().__init__()
        self.data = data
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        self.table = QTableWidget()
        self.table.setRowCount(len(self.data))
        self.table.setColumnCount(ColumnCount)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setVisible(False)
        self.table.setShowGrid(False)
        layout.addWidget(self.table)
        layout.setContentsMargins(0, 0, 0, 0)

        # 添加保存按钮
        self.saveButton = QPushButton("保存")
        self.saveButton.clicked.connect(self.saveData)
        layout.addWidget(self.saveButton)

        self.setLayout(layout)
        self.populateTable(self.data, 0, 0)
        self.beautify()

    def beautify(self):
        for row in range(0, self.table.rowCount()):
            single_col = self.check_single_cell(row)
            double_col = self.check_double_cell(row)
            if single_col != -1:
                for col in range(0, self.table.columnCount()):
                    if col == single_col:
                        continue
                    else:
                        no_item = QTableWidgetItem("")
                        no_item.setFlags(
                            no_item.flags() & ~Qt.ItemIsEnabled & ~Qt.ItemIsSelectable
                        )
                        self.table.setItem(row, col, no_item)
            if double_col != -1:
                for col in range(0, self.table.columnCount()):
                    if col == double_col - 1 or col == double_col:
                        continue
                    else:
                        no_item = QTableWidgetItem("")
                        no_item.setFlags(
                            no_item.flags() & ~Qt.ItemIsEnabled & ~Qt.ItemIsSelectable
                        )
                        self.table.setItem(row, col, no_item)

    def populateTable(self, data, row, column):
        for key, value in data.items():
            self.table.setRowCount(row + 1)
            item_key = QTableWidgetItem(str(key))
            self.table.setItem(row, column, item_key)
            # 叶节点
            if not isinstance(value, dict):
                item_value = QTableWidgetItem(str(value))
                self.table.setItem(row, column + 1, item_value)
                row += 1
            # 父节点
            else:
                row = self.populateTable(value, row + 1, column + 1)

        return row

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        addRowAbove = menu.addAction("在上方添加行")
        addRowBelow = menu.addAction("在下方添加行")
        deleteRow = menu.addAction("删除行")
        action = menu.exec_(event.globalPos())

        if action == addRowAbove:
            self.addNewRow(above=True)
        elif action == addRowBelow:
            self.addNewRow(above=False)
        elif action == deleteRow:
            self.deleteRow()

    def addNewRow(self, above=True):
        current_row = self.table.currentRow()
        if current_row == -1:
            current_row = self.table.rowCount()
        else:
            current_row = current_row if above else current_row + 1
        self.table.insertRow(current_row)
        for i in range(self.table.columnCount()):
            self.table.setItem(current_row, i, QTableWidgetItem(""))

    def deleteRow(self):
        current_row = self.table.currentRow()
        if current_row != -1:
            self.table.removeRow(current_row)

    def save_preferences_to_file(self, preferences):
        with open(
            "C:/Users/Lenovo/Desktop/sijin/stk/apps/template/pyqt/preference.toml", "w"
        ) as file:
            toml.dump(preferences, file)

    def saveData(self):
        rows = self.table.rowCount()  # 获取表格的行数
        cols = self.table.columnCount()  # 获取表格的列数

        # 得到子字典
        def get_subdict(row, col):
            data_dict = {}  # 用于存储子字典数据
            nextrow = row
            while nextrow < rows:
                father_index = self.check_single_cell(nextrow)
                key_item = self.table.item(nextrow, col)  # 获取当前单元格的键项
                key = (
                    key_item.text() if key_item else None
                )  # 获取键项的文本内容，如果键项为空则设置为None
                if father_index != -1:  # 是一个父子典
                    print(key + ":{")

                    if father_index < col:  # 不是上一个父子典的子字典
                        return nextrow, data_dict
                    elif father_index == col:
                        nextrow, sub_dict = get_subdict(nextrow + 1, col + 1)
                        if sub_dict is not None:
                            data_dict[key] = sub_dict
                        else:
                            data_dict[key] = {}
                        nextrow += 1
                    print("}")

                else:  # 是叶字典
                    value_item = (
                        self.table.item(nextrow, col + 1) if col + 1 < cols else None
                    )  # 获取当前单元格的值项
                    value = (
                        value_item.text() if value_item else None
                    )  # 获取值项的文本内容，如果值项为空则设置为None
                    data_dict[key] = value
                    nextrow += 1
            return nextrow, data_dict

        row = 0
        col = 0
        data = {}

        while row < rows:
            key_item = self.table.item(row, col)  # 获取当前单元格的键项
            key = (
                key_item.text() if key_item else None
            )  # 获取键项的文本内容，如果键项为空则设置为None
            if self.check_single_cell(row) != -1:
                row, subdict = get_subdict(row + 1, col + 1)
                data[key] = subdict
            elif self.check_double_cell(row) != -1:
                value_item = (
                    self.table.item(row, col + 1) if col + 1 < cols else None
                )  # 获取当前单元格的值项
                value = (
                    value_item.text() if value_item else None
                )  # 获取值项的文本内容，如果值项为空则设置为None
                data[key] = value
                row += 1

        print(data)
        self.save_preferences_to_file(data)

    def check_single_cell(self, row):
        """
        判断表格某行是否只有一列有数据
        返回值：
            如果只有一个单元格有数据，则返回该单元格的列索引，否则返回 -1
        """
        column_count = self.table.columnCount()  # 获取列数

        count_non_empty = 0  # 计数非空单元格的数量
        non_empty_column = -1  # 非空单元格的列索引，默认为 -1

        # 遍历行中的每一列
        for col in range(column_count):
            item = self.table.item(row, col)  # 获取当前单元格的项
            if item is not None and item.text() != "":  # 如果单元格不为空
                count_non_empty += 1
                non_empty_column = col

        # 如果只有一个非空单元格，则返回该列索引，否则返回 -1
        return non_empty_column if count_non_empty == 1 else -1

    def check_double_cell(self, row):
        """
        判断表格某行是否只有两列有数据
        返回值：
            如果只有两个单元格有数据，则返回最后有值的单元格的列索引，否则返回 -1
        """
        column_count = self.table.columnCount()  # 获取列数

        count_non_empty = 0  # 计数非空单元格的数量
        non_empty_column = -1  # 非空单元格的列索引，默认为 -1

        # 遍历行中的每一列
        for col in range(column_count):
            item = self.table.item(row, col)  # 获取当前单元格的项
            if item is not None and item.text() != "":  # 如果单元格不为空
                count_non_empty += 1
                non_empty_column = col

        # 如果只有一个非空单元格，则返回该列索引，否则返回 -1
        return non_empty_column if count_non_empty == 2 else -1


class CenterWidget(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.runCodeType = None
        self.runCode = None
        self.parent = parent
        self.parent.registerComponent("Visualization window", self, True)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        self.tabWidget = QTabWidget()
        # self.tabWidget.setTabsClosable(True)
        self.tabWidget.setMovable(True)
        self.tabWidget.setTabBarAutoHide(False)
        layout.addWidget(self.tabWidget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self.addMainOperationTabs()

    def registerComponent(self, path, component, isVisible):
        truePath = "Visualization window/" + path
        self.parent.registerComponent(truePath, component, isVisible)

    def unregisterComponent(self, path):
        truePath = "Visualization window/" + path
        self.parent.unregisterComponent(truePath)

    def toggleComponentVisibility(self, tabName):
        tab = self.parent.components["main"]["children"]["Visualization window"][
            "children"
        ][tabName]
        tab["isVisible"] = not tab["isVisible"]
        for i in range(self.tabWidget.count()):
            if self.tabWidget.tabText(i) == tabName[: -len(" Tab")]:
                # 如果选项卡已存在，则删除它
                self.tabWidget.removeTab(i)
                print("删除" + tabName)
                return
        # 如果选项卡不存在，则添加它
        component = tab["component"]
        self.tabWidget.addTab(component, tabName[: -len(" Tab")])

    def addMainOperationTabs(self):
        # vtkVisualizationTab
        self.vtkWidget = QVTKRenderWindowInteractor()  # 创建VTK渲染窗口交互器
        self.vtkWidget.Initialize()
        # self.vtkWidget.GetRenderWindow().AddRenderer(renderer)  # 将渲染器添加到渲染窗口
        # self.vtkWidget.GetRenderWindow().Render()  # 渲染一次
        self.vtkVisualizationTab = QWidget()
        vtkLayout = QVBoxLayout()
        vtkLayout.addWidget(self.vtkWidget)
        self.vtkVisualizationTab.setLayout(vtkLayout)
        self.tabWidget.addTab(self.vtkVisualizationTab, "VTK Visualization")
        self.registerComponent("VTK Visualization Tab", self.vtkVisualizationTab, True)

        #  matplotlibDisplayTab
        self.matplotlibWidget = CustomFigureCanvas()  # 创建画布控件
        self.matplotlibDisplayTab = QWidget()
        self.matplotlibLayout = QVBoxLayout()
        self.matplotlibLayout.addWidget(self.matplotlibWidget)
        self.matplotlibDisplayTab.setLayout(self.matplotlibLayout)
        self.tabWidget.addTab(self.matplotlibDisplayTab, "Matplotlib Display")
        self.registerComponent(
            "Matplotlib Display Tab", self.matplotlibDisplayTab, True
        )

        # dataTableTab
        dataTableTab = QWidget()
        dataTableLabel = QLabel("Data Table Tab")
        dataLayout = QVBoxLayout()
        dataLayout.addWidget(dataTableLabel)
        dataTableTab.setLayout(dataLayout)
        self.tabWidget.addTab(dataTableTab, "Data Table")

        # preferenceTab
        # self.preferenceTab = PreferenceTab()
        # # self.tabWidget.addTab(self.preferenceTab, "Preference")
        # self.registerComponent("Preference Tab", self.preferenceTab,False)

    def addPreferenceTab(self, data):
        print("addPreferenceTab")
        self.unregisterComponent("Preference Tab")
        self.preferenceTab = PreferenceTab(data)
        self.tabWidget.addTab(self.preferenceTab, "Preference")
        self.registerComponent("Preference Tab", self.preferenceTab, True)
        preferenceTabIndex = self.tabWidget.indexOf(self.preferenceTab)
        self.tabWidget.setCurrentIndex(preferenceTabIndex)

    def runCodeWithAnalysis(self, runCode, runCodeType, need_variable):
        self.runCode = runCode
        self.runCodeType = runCodeType
        script_path = "C:/Users/Lenovo/Desktop/sijin/stk/apps/template/pyqt/test/strain/volumn-minimum.py"  # 需要根据实际情况修改此路径
        if self.runCodeType == "vtk":
            local_vars = {}
            global_vars = {"vtk": vtk}
            self.parent.info_bar.execute_code_with_file_path(self.runCode,script_path,global_vars, local_vars)
            # exec(self.runCode, global_vars, local_vars)
            # script_directory=os.path.dirname(os.path.abspath(script_path))
            # # 保存当前工作目录
            # original_directory = os.getcwd()
            # print("执行代码")
            # print(script_directory)
            
            # # 改变当前工作目录
            # os.chdir(script_directory)
            # # 将 __file__ 替换为指定的文件路径
            # modified_code = code_string.replace("__file__", f'"{script_path}"')
            # # 执行替换后的代码字符串
            # try:
            #     exec(modified_code, global_vals, local_vals)  
            # except Exception as e:
            #     QMessageBox.critical(self, "Error", f"Failed to execute script: {str(e)}")
            #     return
            # finally:
            # # 恢复原来的工作目录
            #     os.chdir(original_directory)  
            renderer = local_vars.get(need_variable)
            if renderer:
                self.updateVTKVisualization(renderer)
        if self.runCodeType == "matplotlib":
            local_vars = {}
            global_vars = {"plt": plt}
            self.parent.info_bar.execute_code_with_file_path(self.runCode,script_path,global_vars, local_vars)
            # exec(self.runCode, global_vars, local_vars)
            fig = local_vars.get(need_variable)
            if fig:
                self.updateMatplotlibDisplay(fig)

    # 清空 QVBoxLayout 中所有子控件
    def clearLayout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            layout.removeWidget(widget)
            if widget is not None:
                widget.deleteLater()

    def updateVTKVisualization(self, vtkObject):
        # 更新VTK可视化图
        # renderer = self.vtkWidget.GetRenderWindow().GetRenderers().GetFirstRenderer()
        # renderer.RemoveAllViewProps()  # 移除当前渲染器中的所有对象
        self.vtkWidget.GetRenderWindow().AddRenderer(
            vtkObject
        )  # 将渲染器添加到渲染窗口
        self.vtkWidget.GetRenderWindow().Render()  # 渲染一次
        # 将当前选中的 tab 设置为 "Vtk Visualization"
        vtkVisualizationIndex = self.tabWidget.indexOf(self.vtkVisualizationTab)
        self.tabWidget.setCurrentIndex(vtkVisualizationIndex)

    def updateMatplotlibDisplay(self, fig):
        # 更新Matplotlib显示
        self.matplotlibWidget = CustomFigureCanvas(fig)
        self.clearLayout(self.matplotlibLayout)
        self.matplotlibLayout.addWidget(self.matplotlibWidget)
        # 将当前选中的 tab 设置为 "Matplotlib Display"
        matplotlibDisplayIndex = self.tabWidget.indexOf(self.matplotlibDisplayTab)
        self.tabWidget.setCurrentIndex(matplotlibDisplayIndex)
