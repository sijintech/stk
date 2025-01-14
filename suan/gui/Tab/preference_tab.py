from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTableWidgetItem,
    QPushButton,
    QTableWidget,
    QMenu,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

from custom_logger import CustomLogger


class CustomFigureCanvas(FigureCanvasQTAgg):
    def __init__(self, figure=None):
        super().__init__(figure)
        self.logger = CustomLogger()
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
    def __init__(self, data, parent):
        super().__init__()
        self.logger = CustomLogger()
        self.data = data
        self.parent = parent
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
        self.parent.preferences = preferences
        self.parent.save_preferences

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

        self.logger.debug(data)
        self.data = data
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
