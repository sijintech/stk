


from PySide6 import QtWidgets, QtCore, QtGui
import os
import sys
import subprocess


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
            
            if self.is_windows:


                self.process.start("cmd.exe", ["/c", command])
            else:

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

            text = bytes(data).decode(self.system_encoding, errors='replace')
        except UnicodeDecodeError:

            text = bytes(data).decode('utf-8', errors='replace')
        self.append_output(text)
    
    def handle_stderr(self):
        data = self.process.readAllStandardError()
        try:

            text = bytes(data).decode(self.system_encoding, errors='replace')
        except UnicodeDecodeError:

            text = bytes(data).decode('utf-8', errors='replace')
        self.append_error(text)
    
    def handle_finished(self, exit_code, exit_status):
        if exit_code != 0:
            self.append_error(f"\n命令退出，代码: {exit_code}\n")
            self.commandExecuted.emit(self.last_command, False)
        else:
            self.append_output("\n")
            self.commandExecuted.emit(self.last_command, True)
    
    def execute_stk_command(self, command, args_dict=None):
        cmd_str = command
        
        if args_dict:
            for name, value in args_dict.items():
                if isinstance(value, bool) and value:
                    cmd_str += f" --{name}"
                elif value:
                    cmd_str += f" --{name} {value}"
        
        self.last_command = cmd_str
        
        self.execute_command(cmd_str)
        
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
