"""
CLI功能集成器，负责将CLI功能集成到主窗口
"""

from PySide6 import QtCore, QtWidgets
from .cli_toolbar_button import CLIToolbarButton
from .cli_doc_viewer import CLITab
from .cli_param_form import CLIParamForm
from .cli_manager import CLIManager


class CLIIntegrator(QtCore.QObject):
    """CLI功能集成器，负责将CLI功能集成到主窗口"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)

        self.main_window = main_window


        self.cli_manager = CLIManager(self)


        self.cli_button = CLIToolbarButton(self.cli_manager)

        self.param_form = CLIParamForm(self.cli_manager)

        self.integrate()

    def integrate(self):
        """将CLI功能集成到主窗口"""

        cli_action = self.main_window.toolbar.toolbar1.addAction("CLI")
        cli_action.triggered.connect(
            lambda: self.cli_button.menu.exec(

                self.main_window.toolbar.toolbar1.mapToGlobal(

                    self.main_window.toolbar.toolbar1.actionGeometry(

                        self.main_window.toolbar.toolbar1.actions()[-1]
                    ).bottomLeft()  # 取这个几何区域的左下角坐标，这是菜单应该出现的理想位置
                )
            )
        )

        self.main_window.right_sidebar.set_param_form(self.param_form)

        self.cli_button.commandSelected.connect(self.handle_command_selected)

        self.param_form.paramReady.connect(self.execute_command)

        self.param_form.paramCancelled.connect(self.close_param_form)

    def handle_command_selected(self, group_name, command_name):
        """处理命令选择事件"""
        print(f"选择命令: {group_name} {command_name}")

        doc_tab = self._get_or_create_doc_tab()
        print(f"文档标签页已创建/加载: {doc_tab}")

        self.param_form.title_label.setText(f"{group_name} {command_name}")

        self.main_window.right_sidebar.show_param_form()

        QtCore.QTimer.singleShot(100, lambda: self.cli_manager.load_command_doc_and_params(group_name, command_name))

    def _get_or_create_doc_tab(self):
        """获取或创建文档标签页"""

        for i in range(self.main_window.center_widget.tabWidget.count()):
            tab_text = self.main_window.center_widget.tabWidget.tabText(i)
            if tab_text == "命令解析":
                self.main_window.center_widget.tabWidget.setCurrentIndex(i)
                return self.main_window.center_widget.tabWidget.widget(i)

        doc_tab = CLITab(self.cli_manager)
        tab_index = self.main_window.center_widget.tabWidget.addTab(
            doc_tab, "命令解析"
        )

        self.main_window.center_widget.tabWidget.setCurrentIndex(tab_index)
        return doc_tab

    def close_param_form(self):
        """关闭参数表单，切换回变量表格"""

        self.main_window.right_sidebar.show_variable_table()

    def execute_command(self, params):
        """执行命令，将结果显示在终端窗口"""

        if not self.cli_manager.current_group or not self.cli_manager.current_command:
            return

        cmd_str = f"{self.cli_manager.current_group} {self.cli_manager.current_command}"

        for name, value in params.items():
            if isinstance(value, bool) and value:

                cmd_str += f" --{name}"
            elif value:

                quoted_value = f'"{value}"' if isinstance(value, str) and any(
                    c in str(value) for c in ' <>|&;()$`\\"\'+') else value
                cmd_str += f" --{name} {quoted_value}"

        self._ensure_console_visible()

        self._send_to_terminal(cmd_str, params)

    def _ensure_console_visible(self):
        """确保终端标签页可见"""

        for i in range(self.main_window.info_bar.tabWidget.count()):
            if self.main_window.info_bar.tabWidget.tabText(i) == "Terminal":
                self.main_window.info_bar.tabWidget.setCurrentIndex(i)
                return

    def _send_to_terminal(self, cmd_str, params):
        """将命令发送到终端执行"""

        console = self.main_window.info_bar.consoleTab

        if hasattr(console, "execute_stk_command"):

            group_name = self.cli_manager.current_group
            command_name = self.cli_manager.current_command

            processed_params = {}
            for name, value in params.items():
                if isinstance(value, str):

                    processed_value = value.strip()
                    processed_params[name] = processed_value
                else:
                    processed_params[name] = value

            stk_cmd = f"-m suan.cli.main {group_name} {command_name}"

            console.execute_stk_command(stk_cmd, processed_params)
        else:

            console.append(f"\n> {cmd_str}")

            try:
                result = self.cli_manager.execute_command(
                    self.cli_manager.current_group,
                    self.cli_manager.current_command,
                    params
                )

                if result[0]:  # 成功
                    console.append(str(result[1]) if result[1] else "命令执行成功")
                else:  # 失败
                    console.append(f"错误: {result[1]}")
            except Exception as e:

                console.append(f"执行错误: {str(e)}")
