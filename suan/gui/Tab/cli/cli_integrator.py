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
        # 保存主窗口的引用
        self.main_window = main_window

        # 创建CLI管理器
        self.cli_manager = CLIManager(self)

        # 创建CLI工具栏按钮，传入CLI管理器
        self.cli_button = CLIToolbarButton(self.cli_manager)

        # 创建CLI参数表单
        self.param_form = CLIParamForm(self.cli_manager)

        # 集成各组件到主窗口
        self.integrate()

    def integrate(self):
        """将CLI功能集成到主窗口"""
        # 将CLI按钮添加到主窗口第一行工具栏
        # 创建一个动作并连接到显示CLI菜单的函数
        cli_action = self.main_window.toolbar.toolbar1.addAction("CLI")
        cli_action.triggered.connect(
            lambda: self.cli_button.menu.exec(
                # 将工具栏的局部坐标转换为整个屏幕的全局坐标系，确保菜单无论窗口在哪里都能显示在正确位置
                self.main_window.toolbar.toolbar1.mapToGlobal(
                    # 获取该动作的几何信息（位置和尺寸）
                    self.main_window.toolbar.toolbar1.actionGeometry(
                        #  获取工具栏中的最后一个动作（通常是刚添加的CLI按钮）
                        self.main_window.toolbar.toolbar1.actions()[-1]
                    ).bottomLeft()  # 取这个几何区域的左下角坐标，这是菜单应该出现的理想位置
                )
            )
        )

        # 使用右侧边栏的set_param_form方法注入参数表单
        self.main_window.right_sidebar.set_param_form(self.param_form)
        # 连接信号
        # 当用户选择命令时，commandSelected 信号（被定义在CLI工具栏按钮中）被发射，携带所选命令的组名和命令名作为参数
        self.cli_button.commandSelected.connect(self.handle_command_selected)
        # 当用户提交参数时，执行命令
        self.param_form.paramReady.connect(self.execute_command)
        # 当用户取消参数表单时，切换回变量表格
        self.param_form.paramCancelled.connect(self.close_param_form)

    def handle_command_selected(self, group_name, command_name):
        """处理命令选择事件"""
        print(f"选择命令: {group_name} {command_name}")

        # 确保文档标签页先创建好
        doc_tab = self._get_or_create_doc_tab()
        print(f"文档标签页已创建/加载: {doc_tab}")

        # 设置参数表单标题
        self.param_form.title_label.setText(f"{group_name} {command_name}")

        # 切换右侧边栏显示参数表单
        self.main_window.right_sidebar.show_param_form()

        # 确保标签页已创建后再加载文档和参数（延迟加载）
        QtCore.QTimer.singleShot(100, lambda: self.cli_manager.load_command_doc_and_params(group_name, command_name))

    def _get_or_create_doc_tab(self):
        """获取或创建文档标签页"""
        # 检查是否已存在CLI文档标签页
        for i in range(self.main_window.center_widget.tabWidget.count()):
            tab_text = self.main_window.center_widget.tabWidget.tabText(i)
            if tab_text == "命令解析":
                # 如果存在，切换到该标签页
                self.main_window.center_widget.tabWidget.setCurrentIndex(i)
                return self.main_window.center_widget.tabWidget.widget(i)

        # 如果不存在，创建新标签页
        doc_tab = CLITab(self.cli_manager)
        tab_index = self.main_window.center_widget.tabWidget.addTab(
            doc_tab, "命令解析"
        )
        # 切换到新标签页
        self.main_window.center_widget.tabWidget.setCurrentIndex(tab_index)
        return doc_tab

    def close_param_form(self):
        """关闭参数表单，切换回变量表格"""
        # 切换回变量表格
        self.main_window.right_sidebar.show_variable_table()

    def execute_command(self, params):
        """执行命令，将结果显示在终端窗口"""
        # 检查是否已选择命令
        if not self.cli_manager.current_group or not self.cli_manager.current_command:
            return

        # 构建命令字符串
        cmd_str = f"{self.cli_manager.current_group} {self.cli_manager.current_command}"
        # 添加参数
        for name, value in params.items():
            if isinstance(value, bool) and value:
                # 布尔参数为True时，只添加选项名
                cmd_str += f" --{name}"
            elif value:
                # 对值进行适当的引用，确保特殊字符被正确处理
                quoted_value = f'"{value}"' if isinstance(value, str) and any(
                    c in str(value) for c in ' <>|&;()$`\\"\'+') else value
                cmd_str += f" --{name} {quoted_value}"

        # 确保终端标签页可见
        self._ensure_console_visible()

        # 将命令发送到终端执行
        self._send_to_terminal(cmd_str, params)

    def _ensure_console_visible(self):
        """确保终端标签页可见"""
        # 切换到底部信息栏的Console标签页
        for i in range(self.main_window.info_bar.tabWidget.count()):
            if self.main_window.info_bar.tabWidget.tabText(i) == "Terminal":
                # 如果找到Console标签页，切换到它
                self.main_window.info_bar.tabWidget.setCurrentIndex(i)
                return

    def _send_to_terminal(self, cmd_str, params):
        """将命令发送到终端执行"""
        # 获取Console标签页的文本编辑器
        console = self.main_window.info_bar.consoleTab
        # 判断控制台是否支持终端功能
        if hasattr(console, "execute_stk_command"):
            # 如果是终端组件，使用其专用方法执行STK命令
            group_name = self.cli_manager.current_group
            command_name = self.cli_manager.current_command

            # 对参数进行处理，保留原始参数值但去除前后空格
            processed_params = {}
            for name, value in params.items():
                if isinstance(value, str):
                    # 只去除前后空格，保留内部空格和内容
                    processed_value = value.strip()
                    processed_params[name] = processed_value
                else:
                    processed_params[name] = value

            # 构建Python模块导入命令
            stk_cmd = f"-m suan.cli.main {group_name} {command_name}"

            # 调用终端的执行命令方法，传递模块名和处理后的参数
            console.execute_stk_command(stk_cmd, processed_params)
        else:
            # 如果不支持，则使用基本方法：显示命令和执行结果
            # 显示执行的命令
            console.append(f"\n> {cmd_str}")

            # 使用CLI管理器执行命令并获取结果
            try:
                result = self.cli_manager.execute_command(
                    self.cli_manager.current_group,
                    self.cli_manager.current_command,
                    params
                )

                # 将执行结果显示在控制台
                if result[0]:  # 成功
                    console.append(str(result[1]) if result[1] else "命令执行成功")
                else:  # 失败
                    console.append(f"错误: {result[1]}")
            except Exception as e:
                # 显示执行错误
                console.append(f"执行错误: {str(e)}")
