"""
CLI参数表单组件，用于动态生成表单控件并收集参数
"""

from PySide6 import QtWidgets, QtCore, QtGui


class CLIParamForm(QtWidgets.QWidget):
    """CLI参数表单组件，用于动态生成表单控件并收集参数"""

    # 定义信号：当参数收集完成时发出，参数为参数字典
    paramReady = QtCore.Signal(dict)
    # 添加取消信号：当用户取消参数表单时发出
    paramCancelled = QtCore.Signal()

    def __init__(self, cli_manager, parent=None):
        super().__init__(parent)
        # 保存CLI管理器的引用
        self.cli_manager = cli_manager
        # 存储当前命令的参数信息列表
        self.params = []
        # 存储参数控件字典，键为参数名，值为对应的控件

        self.param_widgets = {}

        # 创建垂直布局
        self.layout = QtWidgets.QVBoxLayout(self)
        # 设置无边距
        self.layout.setContentsMargins(0, 0, 0, 0)

        # 添加标题标签
        self.title_label = QtWidgets.QLabel("CLI命令")
        # 设置居中对齐
        self.title_label.setAlignment(QtCore.Qt.AlignCenter)
        # 设置粗体字
        font = self.title_label.font()
        font.setBold(True)
        self.title_label.setFont(font)
        self.layout.addWidget(self.title_label)

        # 创建滚动区域，用于容纳可能很多的参数控件
        self.scroll_area = QtWidgets.QScrollArea()
        # 设置滚动区域大小自适应内容
        self.scroll_area.setWidgetResizable(True)
        # 隐藏水平滚动条，因为右侧边栏宽度有限
        self.scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        # 让滚动区域占据大部分空间 该控件会随着窗口调整大小而扩展或收缩
        self.layout.addWidget(self.scroll_area, 1)

        # 创建滚动内容区域
        self.scroll_content = QtWidgets.QWidget()
        # 创建了一个表单布局（QFormLayout）并将其应用于滚动内容区域
        self.form_layout = QtWidgets.QFormLayout(self.scroll_content)
        # 设置字段增长策略，指示所有没有固定大小的输入字段（表单右侧列）应当自动扩展以填充可用的水平空间
        self.form_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        self.scroll_area.setWidget(self.scroll_content)

        # 创建按钮布局
        self.button_layout = QtWidgets.QHBoxLayout()
        # 重置按钮：恢复所有参数为默认值
        self.reset_button = QtWidgets.QPushButton("重置")
        # 执行按钮：收集参数并执行命令
        self.execute_button = QtWidgets.QPushButton("执行")
        # 取消按钮：关闭参数表单，切换回变量表格
        self.cancel_button = QtWidgets.QPushButton("取消")
        self.button_layout.addWidget(self.reset_button)
        self.button_layout.addWidget(self.execute_button)
        self.button_layout.addWidget(self.cancel_button)
        self.layout.addLayout(self.button_layout)

        # 连接信号
        # 当CLI管理器加载参数时，创建表单
        self.cli_manager.paramsLoaded.connect(self.create_form)
        # 当点击重置按钮时，重置表单
        self.reset_button.clicked.connect(self.reset_form)
        # 当点击执行按钮时，收集参数
        self.execute_button.clicked.connect(self.collect_params)
        # 当点击取消按钮时，发出取消信号
        self.cancel_button.clicked.connect(self.cancel_form)

    def create_form(self, params):
        """根据参数列表创建表单控件"""
        # 清除旧表单
        self.clear_form()
        # 保存新的参数列表
        self.params = params

        # 遍历参数列表，为每个参数创建控件
        for param in params:
            # 创建参数标签
            label = QtWidgets.QLabel(f"{param['name']}:")
            # 如果参数是必需的，使用粗体标记
            if param['required']:
                label.setText(f"<b>{param['name']}*:</b>")
            # 添加参数帮助信息作为工具提示
            if param['help']:
                label.setToolTip(param['help'])

            # 根据参数类型创建对应的控件
            widget = self._create_param_widget(param)

            # 将标签和控件添加到表单布局中
            self.form_layout.addRow(label, widget)
            # 保存控件到字典，以便后续访问
            self.param_widgets[param['name']] = widget

    def _create_param_widget(self, param):
        """根据参数类型创建相应的控件"""
        # 布尔类型参数使用复选框
        if param['is_flag']:
            widget = QtWidgets.QCheckBox()
            # 设置默认值
            widget.setChecked(param['default'])
        # 选择类型参数使用下拉框
        elif isinstance(param['type'], dict) and param['type'].get('name') == 'choice':
            # 创建了一个下拉选择框控件
            widget = QtWidgets.QComboBox()
            # 添加所有选项
            for choice in param['type']['choices']:
                widget.addItem(str(choice))
            # 设置默认值
            if param['default'] is not None:
                widget.setCurrentText(str(param['default']))
        # 整数类型参数使用数字微调框
        elif param['type'] == 'int':
            # QSpinBox 控件设计用于处理整数值的输入，它提供了多种交互方式：用户可以直接键入数字，也可以通过点击上下箭头按钮逐步调整值，或者使用鼠标滚轮进行快速调整。这种控件自带边界检查功能，可以设置最小值和最大值，防止用户输入超出有效范围的数值。
            widget = QtWidgets.QSpinBox()
            # 设置数值范围
            widget.setMinimum(-999999)
            widget.setMaximum(999999)
            # 设置默认值
            if param['default'] is not None:
                widget.setValue(int(param['default']))
        # 浮点数类型参数使用浮点数微调框
        elif param['type'] == 'float':
            widget = QtWidgets.QDoubleSpinBox()
            # 设置数值范围
            widget.setMinimum(-999999)
            widget.setMaximum(999999)
            # 设置小数位数
            widget.setDecimals(6)
            # 设置默认值
            if param['default'] is not None:
                widget.setValue(float(param['default']))
        # 默认使用文本输入框
        else:
            widget = QtWidgets.QLineEdit()
            # 设置默认值
            if param['default'] is not None:
                widget.setText(str(param['default']))
            # 对于文件或目录类型参数，添加浏览按钮
            if param['type'] in ['file', 'dir']:
                # 创建容器，包含输入框和浏览按钮
                container = QtWidgets.QWidget()
                layout = QtWidgets.QHBoxLayout(container)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.addWidget(widget)
                # 添加浏览按钮
                browse_btn = QtWidgets.QPushButton("浏览")
                layout.addWidget(browse_btn)
                # 根据类型连接不同的浏览函数
                if param['type'] == 'file':
                    browse_btn.clicked.connect(lambda: self._browse_file(widget))
                else:  # dir
                    browse_btn.clicked.connect(lambda: self._browse_dir(widget))
                # 返回包含输入框和浏览按钮的容器
                return container
        # 返回创建的控件
        return widget

    def _browse_file(self, line_edit):
        """打开文件选择对话框"""
        # 显示文件对话框，获取用户选择的文件路径
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择文件")
        # 如果用户选择了文件，更新输入框
        if file_path:
            line_edit.setText(file_path)

    def _browse_dir(self, line_edit):
        """打开目录选择对话框"""
        # 显示目录对话框，获取用户选择的目录路径
        dir_path = QtWidgets.QFileDialog.getExistingDirectory(self, "选择目录")
        # 如果用户选择了目录，更新输入框
        if dir_path:
            line_edit.setText(dir_path)

    def clear_form(self):
        """清除表单内容"""
        # 清除所有表单行
        while self.form_layout.rowCount() > 0:
            self.form_layout.removeRow(0)
        # 清空控件字典
        self.param_widgets.clear()

    def reset_form(self):
        """重置表单为默认值"""
        # 遍历所有参数
        for param in self.params:
            # 获取对应的控件
            widget = self.param_widgets.get(param['name'])
            # 如果控件不存在，跳过
            if not widget:
                continue

            # 根据控件类型设置默认值
            # 复选框设置选中状态
            if param['is_flag']:
                widget.setChecked(param['default'] or False)
            # 下拉框设置当前选项
            elif isinstance(widget, QtWidgets.QComboBox):
                if param['default'] is not None:
                    widget.setCurrentText(str(param['default']))
                else:
                    widget.setCurrentIndex(0)
            # 数字微调框设置数值
            elif isinstance(widget, QtWidgets.QSpinBox) or isinstance(widget, QtWidgets.QDoubleSpinBox):
                if param['default'] is not None:
                    widget.setValue(param['default'])
                else:
                    widget.setValue(0)
            # 文本框设置内容
            elif isinstance(widget, QtWidgets.QLineEdit):
                widget.setText(str(param['default']) if param['default'] is not None else "")
            # 处理容器（如带浏览按钮的输入框）
            elif isinstance(widget, QtWidgets.QWidget):
                # 会在指定控件的子控件层次结构中搜索特定类型的第一个子控件。在这个例子中，代码正在寻找类型为 QLineEdit（文本输入框）的子控件
                line_edit = widget.findChild(QtWidgets.QLineEdit)
                if line_edit:
                    line_edit.setText(str(param['default']) if param['default'] is not None else "")

    def collect_params(self):
        """收集表单中的参数并发出信号"""
        # 创建参数字典
        params = {}

        # 遍历所有参数收集值
        for param in self.params:
            name = param['name']
            # 获取对应的控件
            widget = self.param_widgets.get(name)
            # 如果控件不存在，跳过
            if not widget:
                continue

            # 根据控件类型获取参数值
            # 复选框获取选中状态
            if param['is_flag']:
                params[name] = widget.isChecked()
            # 下拉框获取当前选项
            elif isinstance(widget, QtWidgets.QComboBox):
                params[name] = widget.currentText()
            # 数字微调框获取数值
            elif isinstance(widget, QtWidgets.QSpinBox) or isinstance(widget, QtWidgets.QDoubleSpinBox):
                params[name] = widget.value()
            # 文本框获取内容
            elif isinstance(widget, QtWidgets.QLineEdit):
                params[name] = widget.text()
            # 处理容器（如带浏览按钮的输入框）
            elif isinstance(widget, QtWidgets.QWidget):
                # 在容器中查找文本框
                line_edit = widget.findChild(QtWidgets.QLineEdit)
                if line_edit:
                    params[name] = line_edit.text()

        # 发出参数准备好的信号，传递参数字典
        self.paramReady.emit(params)

    def cancel_form(self):
        """取消参数表单，发出取消信号"""
        # 清空表单
        self.clear_form()
        # 发出取消信号
        self.paramCancelled.emit()
