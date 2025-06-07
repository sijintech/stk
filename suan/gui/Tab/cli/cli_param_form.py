"""
CLI参数表单组件，用于动态生成表单控件并收集参数
"""

from PySide6 import QtWidgets, QtCore, QtGui


class CLIParamForm(QtWidgets.QWidget):
    """CLI参数表单组件，用于动态生成表单控件并收集参数"""


    paramReady = QtCore.Signal(dict)

    paramCancelled = QtCore.Signal()

    def __init__(self, cli_manager, parent=None):
        super().__init__(parent)

        self.cli_manager = cli_manager

        self.params = []

        self.param_widgets = {}

        self.layout = QtWidgets.QVBoxLayout(self)

        self.layout.setContentsMargins(0, 0, 0, 0)

        self.title_label = QtWidgets.QLabel("CLI命令")

        self.title_label.setAlignment(QtCore.Qt.AlignCenter)

        font = self.title_label.font()
        font.setBold(True)
        self.title_label.setFont(font)
        self.layout.addWidget(self.title_label)

        self.scroll_area = QtWidgets.QScrollArea()

        self.scroll_area.setWidgetResizable(True)

        self.scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        self.layout.addWidget(self.scroll_area, 1)

        self.scroll_content = QtWidgets.QWidget()

        self.form_layout = QtWidgets.QFormLayout(self.scroll_content)

        self.form_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        self.scroll_area.setWidget(self.scroll_content)

        self.button_layout = QtWidgets.QHBoxLayout()

        self.reset_button = QtWidgets.QPushButton("重置")

        self.execute_button = QtWidgets.QPushButton("执行")

        self.cancel_button = QtWidgets.QPushButton("取消")
        self.button_layout.addWidget(self.reset_button)
        self.button_layout.addWidget(self.execute_button)
        self.button_layout.addWidget(self.cancel_button)
        self.layout.addLayout(self.button_layout)

        self.cli_manager.paramsLoaded.connect(self.create_form)

        self.reset_button.clicked.connect(self.reset_form)

        self.execute_button.clicked.connect(self.collect_params)

        self.cancel_button.clicked.connect(self.cancel_form)

    def create_form(self, params):
        """根据参数列表创建表单控件"""

        self.clear_form()

        self.params = params

        for param in params:

            label = QtWidgets.QLabel(f"{param['name']}:")

            if param['required']:
                label.setText(f"<b>{param['name']}*:</b>")

            if param['help']:
                label.setToolTip(param['help'])

            widget = self._create_param_widget(param)

            self.form_layout.addRow(label, widget)

            self.param_widgets[param['name']] = widget

    def _create_param_widget(self, param):
        """根据参数类型创建相应的控件"""

        if param['is_flag']:
            widget = QtWidgets.QCheckBox()

            widget.setChecked(param['default'])

        elif isinstance(param['type'], dict) and param['type'].get('name') == 'choice':

            widget = QtWidgets.QComboBox()

            for choice in param['type']['choices']:
                widget.addItem(str(choice))

            if param['default'] is not None:
                widget.setCurrentText(str(param['default']))

        elif param['type'] == 'int':

            widget = QtWidgets.QSpinBox()

            widget.setMinimum(-999999)
            widget.setMaximum(999999)

            if param['default'] is not None:
                widget.setValue(int(param['default']))

        elif param['type'] == 'float':
            widget = QtWidgets.QDoubleSpinBox()

            widget.setMinimum(-999999)
            widget.setMaximum(999999)

            widget.setDecimals(6)

            if param['default'] is not None:
                widget.setValue(float(param['default']))

        else:
            widget = QtWidgets.QLineEdit()

            if param['default'] is not None:
                widget.setText(str(param['default']))

            if param['type'] in ['file', 'dir']:

                container = QtWidgets.QWidget()
                layout = QtWidgets.QHBoxLayout(container)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.addWidget(widget)

                browse_btn = QtWidgets.QPushButton("浏览")
                layout.addWidget(browse_btn)

                if param['type'] == 'file':
                    browse_btn.clicked.connect(lambda: self._browse_file(widget))
                else:  # dir
                    browse_btn.clicked.connect(lambda: self._browse_dir(widget))

                return container

        return widget

    def _browse_file(self, line_edit):
        """打开文件选择对话框"""

        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "选择文件")

        if file_path:
            line_edit.setText(file_path)

    def _browse_dir(self, line_edit):
        """打开目录选择对话框"""

        dir_path = QtWidgets.QFileDialog.getExistingDirectory(self, "选择目录")

        if dir_path:
            line_edit.setText(dir_path)

    def clear_form(self):
        """清除表单内容"""

        while self.form_layout.rowCount() > 0:
            self.form_layout.removeRow(0)

        self.param_widgets.clear()

    def reset_form(self):
        """重置表单为默认值"""

        for param in self.params:

            widget = self.param_widgets.get(param['name'])

            if not widget:
                continue

            if param['is_flag']:
                widget.setChecked(param['default'] or False)

            elif isinstance(widget, QtWidgets.QComboBox):
                if param['default'] is not None:
                    widget.setCurrentText(str(param['default']))
                else:
                    widget.setCurrentIndex(0)

            elif isinstance(widget, QtWidgets.QSpinBox) or isinstance(widget, QtWidgets.QDoubleSpinBox):
                if param['default'] is not None:
                    widget.setValue(param['default'])
                else:
                    widget.setValue(0)

            elif isinstance(widget, QtWidgets.QLineEdit):
                widget.setText(str(param['default']) if param['default'] is not None else "")

            elif isinstance(widget, QtWidgets.QWidget):

                line_edit = widget.findChild(QtWidgets.QLineEdit)
                if line_edit:
                    line_edit.setText(str(param['default']) if param['default'] is not None else "")

    def collect_params(self):
        """收集表单中的参数并发出信号"""

        params = {}

        for param in self.params:
            name = param['name']

            widget = self.param_widgets.get(name)

            if not widget:
                continue

            if param['is_flag']:
                params[name] = widget.isChecked()

            elif isinstance(widget, QtWidgets.QComboBox):
                params[name] = widget.currentText()

            elif isinstance(widget, QtWidgets.QSpinBox) or isinstance(widget, QtWidgets.QDoubleSpinBox):
                params[name] = widget.value()

            elif isinstance(widget, QtWidgets.QLineEdit):
                params[name] = widget.text()

            elif isinstance(widget, QtWidgets.QWidget):

                line_edit = widget.findChild(QtWidgets.QLineEdit)
                if line_edit:
                    params[name] = line_edit.text()

        self.paramReady.emit(params)

    def cancel_form(self):
        """取消参数表单，发出取消信号"""

        self.clear_form()

        self.paramCancelled.emit()
