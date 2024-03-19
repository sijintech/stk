from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem

class RightSidebar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.status=None
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        # 创建表格部件
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(2)  # 设置表格列数为2
        self.table_widget.setHorizontalHeaderLabels(["Statu", "Value"])  # 设置表头标签

        # 添加示例数据
        self.addTableRow("Statu 1", "Value 1")
        self.addTableRow("Statu 2", "Value 2")

        # 将表格的单元格内容更改信号连接到自定义的槽函数
        self.table_widget.cellChanged.connect(self.handleCellChanged)

        layout.addWidget(self.table_widget)
        self.setLayout(layout)

    def addTableRow(self, statu, value):
        row_count = self.table_widget.rowCount()  # 获取当前行数
        self.table_widget.insertRow(row_count)  # 在最后插入新行
        self.table_widget.setItem(row_count, 0, QTableWidgetItem(statu))  # 在第一列设置选项
        self.table_widget.setItem(row_count, 1, QTableWidgetItem(value))  # 在第二列设置值

    def handleCellChanged(self, row, column):
        # 获取编辑后的单元格内容
        statu_item = self.table_widget.item(row, 0)
        statu = statu_item.text()

        value_item = self.table_widget.item(row, 1)
        value = value_item.text()

        # 构建字典并发送给应用程序
        modified_info = {statu: value}
        print("Modified information:", modified_info)
