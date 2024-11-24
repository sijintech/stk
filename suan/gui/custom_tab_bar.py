from PySide6.QtWidgets import QTabBar
from PySide6.QtCore import Qt, QSize


class CustomTabBar(QTabBar):
    def __init__(self, parent=None):
        super().__init__(parent)

    def tabSizeHint(self, index):
        """根据内容动态计算 Tab 的宽度"""
        base_size = super().tabSizeHint(index)
        text_width = self.fontMetrics().horizontalAdvance(self.tabText(index))
        padding = 0  # Tab 的左右额外空间
        return base_size.expandedTo(QSize(text_width + padding, base_size.height()))
