# from PySide6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

# class DictionaryDisplay(QWidget):
#     def __init__(self, data):
#         super().__init__()

#         self.data = data

#         self.initUI()

#     def initUI(self):
#         layout = QVBoxLayout()
#         self.table = QTableWidget()
#         layout.addWidget(self.table)
#         self.setLayout(layout)

#         self.populateTable()

#     def populateTable(self):
#         self.table.verticalHeader().setVisible(False)  # 隐藏行号
#         self.table.horizontalHeader().setVisible(False)  # 隐藏列号
#         self.table.setShowGrid(False)  # 隐藏网格线

#         row = 0
#         for key, value in self.data.items():
#             self.table.setRowCount(row + 1)
#             item_key = QTableWidgetItem(str(key))
#             self.table.setItem(row, 0, item_key)
#             if not isinstance(value, dict):
#                 item_value = QTableWidgetItem(str(value))
#                 self.table.setItem(row, 1, item_value)
#                 row += 1
#             else:
#                 for sub_key, sub_value in value.items():
#                     row += 1
#                     self.table.setRowCount(row + 1)
#                     item_sub_key = QTableWidgetItem(str(sub_key))
#                     item_sub_value = QTableWidgetItem(str(sub_value))
#                     # 设置子节点的缩进，使其相对于父节点向右偏移一些位置
#                     item_sub_key.setIndentation(20)
#                     self.table.setItem(row, 0, item_sub_key)
#                     self.table.setItem(row, 1, item_sub_value)
#                 row += 1
#                 # 注意这里必须调整表格的行数，否则下一行直接空白，不显示表项值
#                 self.table.setRowCount(row + 1)

# if __name__ == "__main__":
#     app = QApplication([])
#     data = {
#         'server': {'host': 'localhost', 'port': 8080, 'ssl': False},
#         'database': {'url': 'mongodb://localhost:27017', 'name': 'mydb', 'username': 'myuser', 'password': 'mypassword', 'level': 'info'},
#         'op':{"lll":"3333"}
#     }
#     window = DictionaryDisplay(data)
#     window.show()
#     app.exec_()
#             item_key.setFlags(item_key.flags() & ~Qt.ItemIsEnabled & ~Qt.ItemIsSelectable)

from PySide6.QtWidgets import (
    QApplication,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QPushButton,
    QMenu,
)
from PySide6.QtCore import Qt

ColumnCount = 7  # 设定只能有ColumnCount个列


class DictionaryDisplay(QWidget):
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
                    print(key + ":" + value)
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
            print("'" + key + "':")
            row, subdict = get_subdict(row + 1, col + 1)
            data[key] = subdict

        print(data)

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


if __name__ == "__main__":
    app = QApplication([])
    data = {
        "server": {"host": "localhost", "port": 8080, "ssl": False},
        "database": {
            "url": "mongodb://localhost:27017",
            "name": "mydb",
            "username": "myuser",
            "password": "mypassword",
            "level": "info",
        },
        "op": {"lll": "3333"},
    }
    window = DictionaryDisplay(data)
    window.show()
    app.exec_()
