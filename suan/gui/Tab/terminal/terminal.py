
from PySide6 import QtWidgets, QtCore, QtGui
import os
import sys



class Terminal(QtWidgets.QWidget):
    
    commandExecuted = QtCore.Signal(str, bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.history = []
        self.history_index = 0
        self.current_directory = os.getcwd()
        
        self.last_command = ""
        

        import locale
        import platform
        self.is_windows = platform.system().lower() == 'windows'

        self.system_encoding = locale.getpreferredencoding(False) if self.is_windows else 'utf-8'
        
        self.setup_ui()
        
        self.process = QtCore.QProcess(self)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.handle_finished)
        
    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.output_area = QtWidgets.QTextEdit()
        self.output_area.setReadOnly(True)
        self.output_area.setFont(QtGui.QFont("Courier New", 10))
        layout.addWidget(self.output_area)
        
        input_layout = QtWidgets.QHBoxLayout()
        
        self.prompt_label = QtWidgets.QLabel("> ")
        input_layout.addWidget(self.prompt_label)
        
        self.input_field = QtWidgets.QLineEdit()
        self.input_field.returnPressed.connect(self.execute_current_input)
        input_layout.addWidget(self.input_field)
        
        layout.addLayout(input_layout)
        
        self.setup_context_menu()
        
        self.append_output("STK 终端 v1.0\n输入命令或通过GUI选择命令执行\n")
        self.append_output(f"当前工作目录: {self.current_directory}\n")
    
    def setup_context_menu(self):
        self.output_area.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.output_area.customContextMenuRequested.connect(self.show_context_menu)        
        self.context_menu = QtWidgets.QMenu(self)
        
        copy_action = self.context_menu.addAction("复制", self.copy_selected)
        copy_action.setShortcut(QtGui.QKeySequence.Copy)
        
        paste_action = self.context_menu.addAction("粘贴", self.paste_to_input)
        paste_action.setShortcut(QtGui.QKeySequence.Paste)
        
        select_all_action = self.context_menu.addAction("全选", self.output_area.selectAll)
        select_all_action.setShortcut(QtGui.QKeySequence.SelectAll)
        
        clear_action = self.context_menu.addAction("清空", self.clear_output)
        clear_action.setShortcut(QtGui.QKeySequence("Ctrl+L"))
    
    def show_context_menu(self, position):
        self.context_menu.exec(self.output_area.mapToGlobal(position))
    
    def copy_selected(self):
        self.output_area.copy()
        
    def clear_output(self):
        self.output_area.clear()
    
    def paste_to_input(self):
        self.input_field.paste()
        self.input_field.setFocus()
    
    def append_output(self, text):
        self.output_area.moveCursor(QtGui.QTextCursor.End)
        self.output_area.insertPlainText(text)
        self.output_area.moveCursor(QtGui.QTextCursor.End)
    
    def append_error(self, text):
        self.output_area.moveCursor(QtGui.QTextCursor.End)
        
        cursor = self.output_area.textCursor()
        current_format = cursor.charFormat()
        
        error_format = QtGui.QTextCharFormat()
        error_format.setForeground(QtCore.Qt.red)
        cursor.setCharFormat(error_format)
        
        cursor.insertText(text)
        
        cursor.setCharFormat(current_format)
        self.output_area.setTextCursor(cursor)
        self.output_area.moveCursor(QtGui.QTextCursor.End)
    
    def append_command(self, command):
        self.output_area.moveCursor(QtGui.QTextCursor.End)
        
        cursor = self.output_area.textCursor()
        current_format = cursor.charFormat()
        
        cmd_format = QtGui.QTextCharFormat()
        cmd_format.setForeground(QtCore.Qt.blue)
        cmd_format.setFontWeight(QtGui.QFont.Bold)
        cursor.setCharFormat(cmd_format)
        
        cursor.insertText(f"\n> {command}\n")
        
        cursor.setCharFormat(current_format)
        self.output_area.setTextCursor(cursor)
        self.output_area.moveCursor(QtGui.QTextCursor.End)
    
    def execute_current_input(self):
        command = self.input_field.text().strip()
        if not command:
            return
            
        self.history.append(command)
        self.history_index = len(self.history)
        
        self.input_field.clear()
        
        self.execute_command(command)
    
    def execute_command(self, command):
        self.last_command = command
        
        self.append_command(command)
        
        parts = command.split()
        if not parts:
            return
            
        if self.handle_builtin_command(parts):
            return
        try:
            self.process.setWorkingDirectory(self.current_directory)

            # 设置环境变量确保命令行使用UTF-8编码输出
            environment = QtCore.QProcessEnvironment.systemEnvironment()
            environment.insert("PYTHONIOENCODING", "utf-8")
            # 对于Windows cmd，设置代码页为65001(UTF-8)
            if self.is_windows:
                environment.insert("CHCP", "65001")
            self.process.setProcessEnvironment(environment)

            if self.is_windows:
                # Windows下使用cmd.exe执行命令，但命令需要完整传递，不能被shell拆分
                # 使用/V:OFF关闭变量延迟展开，/C表示执行命令后退出
                # 先通过chcp 65001设置控制台为UTF-8模式
                self.process.start("cmd.exe", ["/V:OFF", "/C", "chcp 65001 >nul && " + command])
            else:
                # Linux下使用bash执行命令
                self.process.start("/bin/sh", ["-c", command])
            
        except Exception as e:
            self.append_error(f"执行错误: {str(e)}\n")
    
    def handle_builtin_command(self, parts):
        cmd = parts[0].lower()
        
        if cmd == "cd":
            if len(parts) > 1:
                new_dir = parts[1]
                if os.path.isabs(new_dir):
                    target_dir = new_dir
                else:
                    target_dir = os.path.join(self.current_directory, new_dir)
                    
                if os.path.isdir(target_dir):
                    self.current_directory = os.path.normpath(target_dir)
                    os.chdir(self.current_directory)
                    self.append_output(f"当前目录: {self.current_directory}\n")
                else:
                    self.append_error(f"错误: 目录不存在 '{target_dir}'\n")
            else:
                self.append_output(f"当前目录: {self.current_directory}\n")
            return True
            
        elif cmd == "clear":
            self.clear_output()
            return True
            
        elif cmd in ["exit", "quit"]:
            self.append_output("终端仍在运行。请使用GUI关闭标签页。\n")
            return True
            
        return False
    
    def handle_stdout(self):
        data = self.process.readAllStandardOutput()
        try:
            # 首先尝试使用UTF-8解码，因为Python进程的输出通常是UTF-8编码的
            text = bytes(data).decode('utf-8', errors='replace')
        except UnicodeDecodeError:
            # 如果UTF-8失败，再尝试使用系统编码
            text = bytes(data).decode(self.system_encoding, errors='replace')
        self.append_output(text)
    
    def handle_stderr(self):
        data = self.process.readAllStandardError()
        try:
            # 首先尝试使用UTF-8解码
            text = bytes(data).decode('utf-8', errors='replace')
        except UnicodeDecodeError:
            # 如果UTF-8失败，再尝试使用系统编码
            text = bytes(data).decode(self.system_encoding, errors='replace')
        self.append_error(text)

    def handle_finished(self, exit_code, exit_status):
        if exit_code != 0:
            self.append_error(f"\n命令退出，代码: {exit_code}\n")
            self.commandExecuted.emit(self.last_command, False)
        else:
            self.append_output("\n")
            self.commandExecuted.emit(self.last_command, True)

    def execute_stk_command(self, command, args_dict=None):
        """
        执行STK命令，使用Python模块导入方式
        command: 模块路径和命令，如 "-m suan.cli.main sjob schedule"
        args_dict: 参数字典，如 {"keyword": "FREQ", "value": "1e12 1e13"}
        """
        # 准备Python命令参数列表
        cmd_parts = ["python"]

        # 添加命令模块和子命令
        cmd_parts.extend(command.split())

        # 构建显示用的命令字符串
        cmd_str = f"python {command}"

        if args_dict:
            # 处理所有选项参数
            for name, value in args_dict.items():
                # 忽略空字符串值
                if isinstance(value, str) and not value.strip():
                    continue

                # 构建显示用的命令字符串
                if isinstance(value, bool) and value:
                    cmd_str += f" --{name}"
                elif value:
                    # 对于包含特殊字符的值进行引用处理（仅用于显示）
                    if isinstance(value, str) and any(c in value for c in ' <>|&;()$`\\"\''):
                        cmd_str += f" --{name} \"{value}\""
                    else:
                        cmd_str += f" --{name} {value}"

                # 构建实际执行的参数列表
                if isinstance(value, bool) and value:
                    cmd_parts.append(f"--{name}")
                elif value:
                    cmd_parts.append(f"--{name}")
                    # 直接添加值作为单独的参数，无需引用处理
                    cmd_parts.append(str(value))

            # 处理json_file参数（位置参数）
            if 'json_file' in args_dict and args_dict['json_file']:
                json_file_value = args_dict['json_file']
                # 添加到显示字符串
                if isinstance(json_file_value, str) and any(c in json_file_value for c in ' <>|&;()$`\\"\''):
                    cmd_str += f" \"{json_file_value}\""
                else:
                    cmd_str += f" {json_file_value}"
                # 添加到参数列表（作为单独参数）
                cmd_parts.append(str(json_file_value))

        # 记录命令并显示
        self.last_command = cmd_str
        self.append_command(cmd_str)
        # 使用完整参数列表启动Python进程
        try:
            self.process.setWorkingDirectory(self.current_directory)

            # 设置环境变量确保Python使用UTF-8编码输出
            environment = QtCore.QProcessEnvironment.systemEnvironment()
            environment.insert("PYTHONIOENCODING", "utf-8")
            self.process.setProcessEnvironment(environment)

            print(f"执行命令: {' '.join(cmd_parts)}")  # 调试输出
            self.process.start(cmd_parts[0], cmd_parts[1:])
        except Exception as e:
            self.append_error(f"执行错误: {str(e)}\n")
        
    def keyPressEvent(self, event):
        if self.input_field.hasFocus():
            key = event.key()
            
            if key == QtCore.Qt.Key_Up:
                if self.history and self.history_index > 0:
                    self.history_index -= 1
                    self.input_field.setText(self.history[self.history_index])
                    
            elif key == QtCore.Qt.Key_Down:
                if self.history and self.history_index < len(self.history) - 1:
                    self.history_index += 1
                    self.input_field.setText(self.history[self.history_index])
                else:
                    self.history_index = len(self.history)
                    self.input_field.clear()
        
        super().keyPressEvent(event)


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    terminal = Terminal()
    terminal.show()
    sys.exit(app.exec())
