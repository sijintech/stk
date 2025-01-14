import math

import matplotlib.pyplot as plt
import vtk
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QTabWidget,
    QTableWidgetItem,
    QPushButton,
    QTableWidget,
    QHBoxLayout,
    QLineEdit,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

from custom_logger import CustomLogger


class DataTableTab(QWidget):
    def __init__(self, data, ColumnCount):
        super().__init__()
        self.logger = CustomLogger()
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

        table_layout = QHBoxLayout()
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

        self.populateTable(self.data, ColumnCount)

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
