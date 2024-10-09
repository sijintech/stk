from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QTabWidget,
    QTableWidgetItem,
    QPushButton,
    QTableWidget,
    QMenu,
    QHBoxLayout,
    QLineEdit,
)
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
import vtk
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
import matplotlib.pyplot as plt
import toml
from PySide6.QtCore import Qt
import math



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


PreferenceColumnCount = 7


class PreferenceTab(QWidget):
    def __init__(self, data, preference_toml_path):
        super().__init__()
        self.data = data
        self.preference_toml_path = preference_toml_path
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        self.table = QTableWidget()
        self.table.setRowCount(len(self.data))
        self.table.setColumnCount(PreferenceColumnCount)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setVisible(False)
        self.table.setShowGrid(False)
        layout.addWidget(self.table)
        layout.setContentsMargins(0, 0, 0, 0)

        # 添加保存按钮
        self.saveButton = QPushButton("Save")
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
        addRowAbove = menu.addAction("Add Row Above")
        addRowBelow = menu.addAction("Add Row Below")
        deleteRow = menu.addAction("Delete Row")
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
        with open(self.preference_toml_path, "w") as file:
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

                    if father_index < col:  # 不是上一个父子典的子字典
                        return nextrow, data_dict
                    elif father_index == col:
                        nextrow, sub_dict = get_subdict(nextrow + 1, col + 1)
                        if sub_dict is not None:
                            data_dict[key] = sub_dict
                        else:
                            data_dict[key] = {}
                        # nextrow += 1

                else:  # 是叶字典
                    value_item = (
                        self.table.item(nextrow, col + 1) if col + 1 < cols else None
                    )  # 获取当前单元格的值项
                    value = (
                        value_item.text() if value_item else None
                    )  # 获取值项的文本内容，如果值项为空则设置为None
                    if value == "True":
                        value = True
                    elif value == "False":
                        value = False
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
                if value == "True":
                    value = True
                elif value == "False":
                    value = False
                data[key] = value
                row += 1

        # print(data)
        self.data=data
        self.save_preferences_to_file(self.data)

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

class DataTableTab(QWidget):
    def __init__(self, data, ColumnCount):
        super().__init__()
        self.data = data
        self.initUI(ColumnCount)

    def initUI(self, ColumnCount):
        layout = QVBoxLayout()

        input_layout = QHBoxLayout()
        label1 = QLabel("x:")
        input1 = QLineEdit()
        input1.setPlaceholderText("输入x坐标")
        input1.setFixedWidth(150)
        label2 = QLabel("y:")
        input2 = QLineEdit()
        input2.setPlaceholderText("输入y坐标")
        input2.setFixedWidth(150)
        label3 = QLabel("z:")
        input3 = QLineEdit()
        input3.setPlaceholderText("输入z坐标")
        input3.setFixedWidth(150)
        button = QPushButton("Goto")
        button.setFixedWidth(100)

        input_layout.addStretch()
        input_layout.addWidget(label1)
        input_layout.addWidget(input1)
        input_layout.addWidget(label2)
        input_layout.addWidget(input2)
        input_layout.addWidget(label3)
        input_layout.addWidget(input3)
        input_layout.addWidget(button)
        input_layout.addStretch()

        table_layout=QHBoxLayout()
        self.table = QTableWidget()
        # self.table.setRowCount(len(self.data))
        # self.table.setColumnCount(ColumnCount)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setShowGrid(False)
        # table_layout.addStretch(1)
        table_layout.addWidget(self.table)
        # table_layout.addStretch(1)
        
        layout.addLayout(input_layout)
        layout.addLayout(table_layout)
        layout.setContentsMargins(0, 0, 0, 0)

        self.setLayout(layout)

        self.populateTable(self.data,ColumnCount)
        
        # 创建用于跳转的槽函数
        def gotoRow():
            x = float(input1.text())
            y = float(input2.text())
            z = float(input3.text())
            matching_items = self.table.findItems(str(x), Qt.MatchExactly)
            if not matching_items:
                return
            for item in matching_items:
                row = item.row()
                if (
                    math.isclose(float(self.table.item(row, 1).text()), y)
                    and math.isclose(float(self.table.item(row, 2).text()), z)
                ):
                    self.table.setCurrentCell(row, 3)
                    self.table.scrollToItem(item)
                    return
        button.clicked.connect(gotoRow)


    def beautify(self):
        for row in range(0, self.table.rowCount()):
            for col in range(0, 3):
                no_item = self.table.item(row, col)
                no_item.setFlags(
                    no_item.flags() & ~Qt.ItemIsEnabled & ~Qt.ItemIsSelectable
                )


    def populateTable(self, data, ColumnCount):
        if data != None:
            self.table.clearContents()
            self.data = data
            row = 0
            self.table.setRowCount(len(self.data))
            self.table.setColumnCount(ColumnCount)
            for key, value in self.data.items():
                x, y, z = key
                x_item = QTableWidgetItem(str(x))
                y_item = QTableWidgetItem(str(y))
                z_item = QTableWidgetItem(str(z))
                value_item = QTableWidgetItem(str(value))

                self.table.setItem(row, 0, x_item)
                self.table.setItem(row, 1, y_item)
                self.table.setItem(row, 2, z_item)
                self.table.setItem(row, 3, value_item)

                row += 1

            self.beautify()
        

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
        self.tabWidget.setTabsClosable(True)
        self.tabWidget.tabCloseRequested.connect(self.close_tab)
        self.tabWidget.setMovable(True)
        self.tabWidget.setTabBarAutoHide(False)
        layout.addWidget(self.tabWidget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self.addMainOperationTabs()

    def initWorkspace(self):
        active_tab_index = self.parent.get_workspace_data('center_widget/active_tab_index')
        self.tabWidget.setCurrentIndex(active_tab_index)
        # self.vtkObject=self.parent.get_workspaceData('center_widget/vtk/view_port')
        # self.vtkWidget.GetRenderWindow().AddRenderer(
        #     self.vtkObject
        # )

    def close_tab(self, index):
        tabName = self.tabWidget.tabText(index) + " Tab"
        tab = self.parent.components["main"]["children"]["Visualization window"][
            "children"
        ][tabName]
        tab["isVisible"] = not tab["isVisible"]
        self.tabWidget.removeTab(index)
        
    def closeEvent(self, QCloseEvent):
        super().closeEvent(QCloseEvent)
        self.vtkWidget.Finalize()

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
        self.dataTableTab = DataTableTab({},4)
        self.tabWidget.addTab(self.dataTableTab, "Data Table")
        self.registerComponent("Data Table Tab", self.dataTableTab, True)

        # preferenceTab
        # self.preferenceTab = PreferenceTab()
        # # self.tabWidget.addTab(self.preferenceTab, "Preference")
        # self.registerComponent("Preference Tab", self.preferenceTab,False)

    def addPreferenceTab(self, data):
        # print("addPreferenceTab")
        self.unregisterComponent("Preference Tab")
        self.preferenceTab = PreferenceTab(data, self.parent.preference_toml_path)
        self.tabWidget.addTab(self.preferenceTab, "Preference")
        self.registerComponent("Preference Tab", self.preferenceTab, True)
        preferenceTabIndex = self.tabWidget.indexOf(self.preferenceTab)
        self.tabWidget.setCurrentIndex(preferenceTabIndex)
        
    def runCodeWithAnalysis(self, runCode, runCodeType, need_variable):
        self.runCode = runCode
        self.runCodeType = runCodeType
        script_path = self.parent.curWorkFile
        if self.runCodeType == "vtk":
            local_vars = {}
            global_vars = {"vtk": vtk}
            self.parent.info_bar.execute_code_with_file_path(
                self.runCode, script_path, global_vars, local_vars
            )
            renderer = local_vars.get(need_variable)
            if renderer:
                self.updateVTKVisualization(renderer)
        if self.runCodeType == "matplotlib":
            local_vars = {}
            global_vars = {"plt": plt}
            self.parent.info_bar.execute_code_with_file_path(
                self.runCode, script_path, global_vars, local_vars
            )
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
        self.vtkObject=vtkObject
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

    def updateDataTable(self, data):
        # print(data)
        # self.unregisterComponent("Data Table Tab")
        # self.dataTableTab = DataTableTab(data,4)
        # self.tabWidget.addTab(self.dataTableTab, "Data Table")
        # self.registerComponent("Data Table Tab", self.dataTableTab, True)
        self.dataTableTab.populateTable(data, 4)
        dataTableIndex = self.tabWidget.indexOf(self.dataTableTab)
        self.tabWidget.setCurrentIndex(dataTableIndex)
