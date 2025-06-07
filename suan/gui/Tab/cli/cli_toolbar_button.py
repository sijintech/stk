"""
CLI工具栏按钮，显示命令组和命令的下拉菜单
"""

from PySide6 import QtWidgets, QtCore, QtGui


class CLIToolbarButton(QtWidgets.QToolButton):
    """CLI工具栏按钮，显示命令组和命令的下拉菜单"""

    # 自定义信号：当用户选择命令时发出，传递命令组名称和命令名称
    commandSelected = QtCore.Signal(str, str)

    def __init__(self, cli_manager, parent=None):
        """初始化按钮并设置基本属性"""
        super().__init__(parent)  # 调用父类初始化方法
        # 保存CLI管理器的引用
        self.cli_manager = cli_manager

        # 设置按钮文本和提示信息
        self.setText("CLI")  # 按钮显示文本为"CLI"
        self.setToolTip("命令行工具")  # 鼠标悬停时的提示文本
        # 设置点击按钮立即显示弹出菜单，而不是先按下再弹出
        self.setPopupMode(QtWidgets.QToolButton.InstantPopup)

        # 创建下拉菜单对象
        self.menu = QtWidgets.QMenu(self)
        # 将菜单设置为按钮的弹出菜单
        self.setMenu(self.menu)

        # 加载所有可用命令到菜单中
        self.load_commands()

    def load_commands(self):
        """加载所有可用的命令组和命令到菜单中"""
        # 从CLI管理器获取所有命令组
        group_names = self.cli_manager.get_command_groups()

        # 遍历所有命令组
        for group_name in group_names:
            try:
                # 为该命令组创建子菜单
                group_menu = QtWidgets.QMenu(group_name, self.menu)
                # 将子菜单添加到主菜单
                self.menu.addMenu(group_menu)

                # 从CLI管理器获取该命令组下的所有命令
                cmd_names = self.cli_manager.get_commands(group_name)

                # 遍历所有命令，添加到子菜单
                for cmd_name in cmd_names:
                    # 创建菜单项，显示命令名称
                    action = group_menu.addAction(cmd_name)
                    # 菜单动作的 triggered 信号被激活
                    # 对应的 lambda 函数被调用，接收 checked 参数（表示动作是否被选中）
                    # lambda 函数使用它捕获的 g 和 c 值（对应特定的命令组和命令名）
                    # lambda 函数发射 commandSelected 自定义信号，将这两个值传递出去
                    action.triggered.connect(
                        # 使用lambda绑定固定的参数值，注意使用默认参数避免闭包问题
                        # 闭包问题：如果不使用默认参数，所有lambda都会引用for循环结束时的值
                        lambda g=group_name, c=cmd_name:
                        self.commandSelected.emit(g, c)
                    )
            except Exception as e:
                # 出错时打印错误信息，继续处理其他命令组
                print(f"加载命令组 {group_name} 失败: {e}")
