from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QSizePolicy,
    QHeaderView,
    QPushButton,
    QMenu,
    QStackedLayout,  # 新增
)
from custom_logger import CustomLogger

class RightSidebar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.logger = CustomLogger()
        self.table_widget = None
        self.variable_info = None
        self.parent = parent
        self.param_form = None  # CLI参数表单
        self.initUI()
        self.parent.registerComponent("Status", self, True)

    def initUI(self):
        self.stacked_layout = QStackedLayout()
        # 创建表格部件
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(2)  # 设置表格列数为2
        self.table_widget.setHorizontalHeaderLabels([
            "变量名", "变量值"
        ])  # 设置表头标签
        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.stacked_layout.addWidget(self.table_widget)
        self.setLayout(self.stacked_layout)

    def set_param_form(self, param_form):
        """注入CLI参数表单，并加入堆叠布局"""
        self.param_form = param_form
        self.stacked_layout.addWidget(param_form)

    def show_variable_table(self):
        """显示变量表格"""
        self.stacked_layout.setCurrentWidget(self.table_widget)

    def show_param_form(self):
        """显示CLI参数表单"""
        if self.param_form:
            self.stacked_layout.setCurrentWidget(self.param_form)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        saveData = menu.addAction("保存修改")
        saveDataAndrun = menu.addAction("保存修改并运行")

        action = menu.exec_(event.globalPos())

        if action == saveData:
            self.saveData()
        elif action == saveDataAndrun:
            self.saveData()
            self.parent.get_component_by_name('Code Tab').runCodeWithAnalysis()

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
        self.parent.get_component_by_name('Code Tab').update_initial_value(self.variable_info)
        self.parent.toolbar.save_file()

    def updateData(self, variable_info):
        self.variable_info = variable_info
        # 清空表格
        self.logger.debug("清空表格")
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
