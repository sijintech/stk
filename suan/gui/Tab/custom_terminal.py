from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Qt, Signal

from pyqode.core.widgets.terminal import Terminal


class CustomTerminal(Terminal):
    """
    自定义终端组件，继承自 pyqode.core.widgets.terminal.Terminal
    可以在此基础上添加更多自定义功能
    """
    
    command_executed = Signal(str)  # 用于发送命令执行完成的信号
    
    def __init__(self, parent=None, color_scheme=None):
        super(CustomTerminal, self).__init__(parent=parent, color_scheme=color_scheme)
        # 自定义终端初始化
        self.setObjectName("customTerminal")
        
    def execute_command(self, command):
        """
        执行指定的命令
        
        :param command: 要执行的命令
        """
        if command:
            self._process.write((command + '\n').encode())
            self.command_executed.emit(command)
            
    def clear_terminal(self):
        """
        清空终端内容
        """
        self.clear()
        
    def change_directory(self, directory):
        """
        更改当前工作目录
        
        :param directory: 目标目录路径
        """
        super(CustomTerminal, self).change_directory(directory)


class CustomTerminalWidget(QWidget):
    """
    包装 CustomTerminal 的容器 Widget，方便布局管理
    """
    
    def __init__(self, parent=None):
        super(CustomTerminalWidget, self).__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.terminal = CustomTerminal(self)
        self.layout.addWidget(self.terminal)
