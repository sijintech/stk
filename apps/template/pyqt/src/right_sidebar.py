from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QSizePolicy,
    QHeaderView,
    QPushButton,
    QMenu,
)


class RightSidebar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.table_widget = None
        self.variable_info = None
        self.parent = parent
        self.parent.registerComponent("Status", self, True)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        # 创建表格部件
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(2)  # 设置表格列数为2
        self.table_widget.setHorizontalHeaderLabels(
            ["变量名", "变量值"]
        )  # 设置表头标签
        layout.addWidget(self.table_widget)

        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.setContentsMargins(0, 0, 0, 0)

        self.setLayout(layout)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        saveData = menu.addAction("保存修改")
        saveDataAndrun = menu.addAction("保存修改并运行")

        action = menu.exec_(event.globalPos())

        if action == saveData:
            self.saveData()
        elif action == saveDataAndrun:
            self.saveData()
            self.parent.info_bar.runCodeWithAnalysis()

    def saveData(self):
        # 获取表格行数
        rows = self.table_widget.rowCount()

        # 遍历表格行，更新变量信息的初始值
        for row in range(rows):
            variable_name_item = self.table_widget.item(row, 0)  # 获取变量名单元格
            variable_value_item = self.table_widget.item(row, 1)  # 获取变量值单元格

            # 获取变量名和变量值
            variable_name = variable_name_item.text() if variable_name_item else ""
            variable_value = variable_value_item.text() if variable_value_item else ""

            # 更新变量信息中的初始值
            if variable_name in self.variable_info:
                self.variable_info[variable_name]["initial_value"] = variable_value
        self.parent.info_bar.updateInitialValue(self.variable_info)
        self.parent.toolbar.save_file()

    def updateData(self, variable_info):
        self.variable_info = variable_info
        # 清空表格
        print("清空表格")
        self.table_widget.clearContents()

        # 设置表格行数
        self.table_widget.setRowCount(len(variable_info))

        # 遍历 variable_info 字典，将变量名和初始值填充到表格中
        for row, (variable_name, info) in enumerate(variable_info.items()):
            # 设置变量名
            variable_name_item = QTableWidgetItem(variable_name)
            self.table_widget.setItem(row, 0, variable_name_item)

            # 设置初始值
            initial_value_item = QTableWidgetItem(info["initial_value"])
            self.table_widget.setItem(row, 1, initial_value_item)
        # 强制刷新表格视图
        self.table_widget.viewport().update()
