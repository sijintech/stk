"""
CLI工具栏按钮，显示命令组和命令的下拉菜单
"""

from PySide6 import QtWidgets, QtCore, QtGui


class CLIToolbarButton(QtWidgets.QToolButton):
    """CLI工具栏按钮，显示命令组和命令的下拉菜单"""


    commandSelected = QtCore.Signal(str, str)

    def __init__(self, cli_manager, parent=None):
        """初始化按钮并设置基本属性"""
        super().__init__(parent)  # 调用父类初始化方法

        self.cli_manager = cli_manager

        self.setText("CLI")  # 按钮显示文本为"CLI"
        self.setToolTip("命令行工具")  # 鼠标悬停时的提示文本

        self.setPopupMode(QtWidgets.QToolButton.InstantPopup)

        self.menu = QtWidgets.QMenu(self)

        self.setMenu(self.menu)

        self.load_commands()

    def load_commands(self):
        """加载所有可用的命令组和命令到菜单中"""

        group_names = self.cli_manager.get_command_groups()

        for group_name in group_names:
            try:

                group_menu = QtWidgets.QMenu(group_name, self.menu)

                self.menu.addMenu(group_menu)

                cmd_names = self.cli_manager.get_commands(group_name)

                for cmd_name in cmd_names:
                    action = group_menu.addAction(cmd_name)

                    action.triggered.connect(

                        lambda g=group_name, c=cmd_name:
                        self.commandSelected.emit(g, c)
                    )
            except Exception as e:

                print(f"加载命令组 {group_name} 失败: {e}")
