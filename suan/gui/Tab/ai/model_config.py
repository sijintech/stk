from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QSpinBox,
    QPushButton,
    QTabWidget,
    QWidget,
    QSlider,
    QTextEdit,
    QMessageBox,
    QFileDialog,
    QApplication,
    QProgressDialog,
)
from PySide6.QtCore import Qt
import os
import json
import requests
import time
from custom_logger import CustomLogger


class ModelConfigDialog(QDialog):
    """AI模型配置对话框

    用于创建和编辑AI模型配置的对话框，支持公有模型和私有模型的配置
    通过选项卡分组显示基本设置、高级设置和分析选项
    """

    def __init__(self, parent=None, config=None):
        """
        初始化配置对话框

        参数:
            parent (QWidget): 父组件
            config (dict): 现有配置字典，用于编辑模式
        """
        super().__init__(parent)
        self.setWindowTitle("AI模型配置")
        self.setMinimumWidth(450)  # 设置最小宽度，确保UI元素显示完整
        self.config = config or {}  # 如果没有传入配置，使用空字典
        self.logger = CustomLogger()  # 用于记录错误和调试信息
        self.initUI()  # 初始化界面

    def initUI(self):
        """
        初始化用户界面

        创建所有UI组件并设置布局结构，包括：
        - 基本设置选项卡：配置名称、模型类型、主机地址等
        - 高级设置选项卡：温度、最大输出长度、系统提示词等
        - 分析与日志选项卡：性能分析、查询日志设置等
        """
        layout = QVBoxLayout()


        tabWidget = QTabWidget()


        basicTab = QWidget()
        basicForm = QFormLayout(basicTab)


        self.nameInput = QLineEdit(self.config.get("name", ""))
        basicForm.addRow("配置名称:", self.nameInput)


        self.modelTypeCombo = QComboBox()
        self.modelTypeCombo.addItems(
            ["公有模型 (仅需API地址)", "私有模型 (需要API密钥)"]
        )


        if "type" in self.config:
            self.modelTypeCombo.setCurrentIndex(
                0 if self.config["type"] == "public" else 1
            )
        else:
            self.modelTypeCombo.setCurrentIndex(0)  # 默认选择公有模型


        self.modelTypeCombo.currentIndexChanged.connect(self.updateFormFields)
        basicForm.addRow("模型类型:", self.modelTypeCombo)


        self.hostInput = QLineEdit(self.config.get("host", "127.0.0.1"))
        basicForm.addRow("主机/端点:", self.hostInput)


        self.portInput = QLineEdit(self.config.get("port", "11434"))
        basicForm.addRow("端口:", self.portInput)


        self.apiKeyInput = QLineEdit(self.config.get("api_key", ""))
        self.apiKeyInput.setEchoMode(QLineEdit.Password)  # 密码模式不显示实际文本
        basicForm.addRow("API密钥:", self.apiKeyInput)


        self.modelNameInput = QLineEdit(self.config.get("model_name", ""))
        basicForm.addRow("模型名称:", self.modelNameInput)


        tabWidget.addTab(basicTab, "基本设置")


        advancedTab = QWidget()
        advancedForm = QFormLayout(advancedTab)


        self.temperatureLabel = QLabel("温度:")
        self.temperatureSlider = QSlider(Qt.Horizontal)
        self.temperatureSlider.setRange(
            0, 100
        )  # 0-1.0的温度值，乘以100以便滑块使用整数值
        self.temperatureValue = self.config.get("temperature", 0.7)  # 默认温度0.7
        self.temperatureSlider.setValue(int(self.temperatureValue * 100))
        self.temperatureDisplay = QLabel(
            f"{self.temperatureValue:.2f}"
        )  # 显示当前温度值
        self.temperatureSlider.valueChanged.connect(self.updateTemperatureDisplay)

        tempLayout = QHBoxLayout()
        tempLayout.addWidget(self.temperatureSlider)
        tempLayout.addWidget(self.temperatureDisplay)

        advancedForm.addRow(self.temperatureLabel, tempLayout)


        self.maxTokensLabel = QLabel("最大输出长度:")
        self.maxTokensInput = QSpinBox()
        self.maxTokensInput.setRange(100, 8000)  # 设置合理的范围
        self.maxTokensInput.setSingleStep(100)  # 调整步长为100
        self.maxTokensInput.setValue(self.config.get("max_tokens", 1000))  # 默认1000
        advancedForm.addRow(self.maxTokensLabel, self.maxTokensInput)


        self.systemPromptLabel = QLabel("系统提示词:")
        self.systemPromptInput = QTextEdit()
        self.systemPromptInput.setPlaceholderText(
            "输入系统提示词，定义AI助手的行为和角色..."
        )
        self.systemPromptInput.setText(self.config.get("system_prompt", ""))
        self.systemPromptInput.setMaximumHeight(100)  # 限制高度，避免对话框过大
        advancedForm.addRow(self.systemPromptLabel, self.systemPromptInput)


        self.useRagCheck = QCheckBox("导入使用手册(使用RAG技术)")
        self.useRagCheck.setChecked(self.config.get("use_rag", False))
        self.useRagCheck.setToolTip("启用后模型会参考使用手册内容回答问题")
        self.useRagCheck.stateChanged.connect(self.updateRagOptions)


        self.manualPathLayout = QHBoxLayout()
        self.manualPathInput = QLineEdit(self.config.get("manual_path", ""))
        self.manualPathInput.setPlaceholderText("选择PDF使用手册路径...")
        self.manualPathInput.setEnabled(self.config.get("use_rag", False))  # 默认禁用

        self.browseManualBtn = QPushButton("浏览...")
        self.browseManualBtn.clicked.connect(self.browseManualFile)
        self.browseManualBtn.setEnabled(self.config.get("use_rag", False))  # 默认禁用

        self.manualPathLayout.addWidget(self.manualPathInput)
        self.manualPathLayout.addWidget(self.browseManualBtn)


        advancedForm.addRow(self.useRagCheck, QWidget())  # 使用空的QWidget作为占位符
        advancedForm.addRow("使用手册路径:", self.manualPathLayout)


        tabWidget.addTab(advancedTab, "高级设置")


        analyticsTab = QWidget()
        analyticsForm = QFormLayout(analyticsTab)


        self.enableAnalyticsCheck = QCheckBox("启用性能分析")
        self.enableAnalyticsCheck.setChecked(self.config.get("enable_analytics", False))
        analyticsForm.addRow("性能分析:", self.enableAnalyticsCheck)

        self.logQueriesCheck = QCheckBox("记录查询")
        self.logQueriesCheck.setChecked(self.config.get("log_queries", False))
        analyticsForm.addRow("查询日志:", self.logQueriesCheck)

        self.responseTimeoutInput = QSpinBox()
        self.responseTimeoutInput.setRange(5, 300)  # 5-300秒的合理范围
        self.responseTimeoutInput.setSingleStep(5)  # 5秒为步长
        self.responseTimeoutInput.setValue(
            self.config.get("response_timeout", 60)
        )  # 默认60秒
        analyticsForm.addRow("响应超时(秒):", self.responseTimeoutInput)


        tabWidget.addTab(analyticsTab, "分析与日志")

        layout.addWidget(tabWidget)


        buttonLayout = QHBoxLayout()
        self.saveBtn = QPushButton("保存")
        self.saveBtn.clicked.connect(self.saveConfig)
        self.cancelBtn = QPushButton("取消")
        self.cancelBtn.clicked.connect(self.reject)  # 关闭对话框，返回QDialog.Rejected
        self.testBtn = QPushButton("测试连接")
        self.testBtn.clicked.connect(self.testConnection)

        buttonLayout.addWidget(self.cancelBtn)
        buttonLayout.addWidget(self.testBtn)
        buttonLayout.addWidget(self.saveBtn)

        layout.addLayout(buttonLayout)
        self.setLayout(layout)


        self.updateFormFields()

    def updateTemperatureDisplay(self, value):
        """
        更新温度显示值

        参数:
            value (int): 滑块位置值(0-100)

        将滑块整数值转换为0-1.0范围的浮点数，并更新显示标签
        """
        temp = value / 100.0  # 转换为0-1.0的浮点数
        self.temperatureDisplay.setText(f"{temp:.2f}")  # 显示两位小数
        self.temperatureValue = temp  # 保存当前温度值

    def updateFormFields(self):
        """
        根据选择的模型类型更新表单字段显示

        当模型类型切换时，调整相关字段的启用状态和提示文本
        """
        model_type = self.modelTypeCombo.currentIndex()


        if model_type == 0:
            self.apiKeyInput.setEnabled(False)
            self.apiKeyInput.setPlaceholderText("公有模型不需要API密钥")
            self.hostInput.setPlaceholderText("127.0.0.1")
            self.portInput.setEnabled(True)
            self.portInput.setPlaceholderText("11434")
            self.modelNameInput.setPlaceholderText("模型名称，如：deepseek-coder")

        else:
            self.apiKeyInput.setEnabled(True)
            self.apiKeyInput.setPlaceholderText("输入您的API密钥")
            self.hostInput.setPlaceholderText("https://api.example.com")
            self.portInput.setEnabled(False)  # 私有模型通常使用标准端口，在URL中指定
            self.modelNameInput.setPlaceholderText("模型部署名称")

    def updateRagOptions(self, state):
        """
        更新RAG选项可用性

        参数:
            state (int): 复选框状态

        根据RAG复选框的状态，启用或禁用相关字段
        """
        enabled = state == Qt.Checked
        self.manualPathInput.setEnabled(enabled)
        self.browseManualBtn.setEnabled(enabled)




    def testConnection(self):
        """
        测试模型连接

        根据当前配置测试与AI服务器的连接，显示连接结果
        """

        model_type = "public" if self.modelTypeCombo.currentIndex() == 0 else "private"
        host = self.hostInput.text()
        port = self.portInput.text()
        api_key = self.apiKeyInput.text()


        QApplication.setOverrideCursor(Qt.WaitCursor)

        try:

            if model_type == "public":
                url = f"http://{host}:{port}/api/tags"
                response = requests.get(url, timeout=5)  # 5秒超时
                if response.status_code == 200:
                    QMessageBox.information(self, "连接成功", f"成功连接到服务器")
                else:
                    QMessageBox.warning(
                        self, "连接失败", f"连接失败: HTTP {response.status_code}"
                    )

            else:
                if not api_key:
                    QMessageBox.warning(self, "缺少API密钥", "私有模型需要提供API密钥")
                    return


                url = host
                if port and not host.startswith("http"):
                    url = f"http://{host}:{port}"

                headers = {"Authorization": f"Bearer {api_key}"}
                response = requests.get(url, headers=headers, timeout=5)

                QMessageBox.information(
                    self,
                    "连接测试",
                    f"已连接到端点: {url}\n状态码: {response.status_code}",
                )

        except Exception as e:

            QMessageBox.warning(self, "连接失败", f"连接失败: {str(e)}")

        finally:

            QApplication.restoreOverrideCursor()

    def browseManualFile(self):
        """
        选择使用手册PDF文件

        打开文件选择对话框，用户选择PDF文件后更新路径输入框
        """
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择使用手册PDF", "", "PDF文件 (*.pdf)"
        )
        if file_path:
            self.manualPathInput.setText(file_path)

    def saveConfig(self):
        """
        保存模型配置

        从表单收集所有配置信息，保存到self.config，然后关闭对话框
        返回QDialog.Accepted状态，表示配置已保存
        """

        if not self.nameInput.text():
            QMessageBox.warning(self, "警告", "配置名称不能为空")
            return


        model_type = "public" if self.modelTypeCombo.currentIndex() == 0 else "private"


        config = {
            "name": self.nameInput.text(),
            "type": model_type,
            "host": self.hostInput.text(),
            "port": self.portInput.text() if self.portInput.isEnabled() else "",
            "api_key": self.apiKeyInput.text() if model_type == "private" else "",
            "model_name": self.modelNameInput.text(),
            "temperature": self.temperatureValue,
            "max_tokens": self.maxTokensInput.value(),
            "system_prompt": self.systemPromptInput.toPlainText(),
            "enable_analytics": self.enableAnalyticsCheck.isChecked(),
            "log_queries": self.logQueriesCheck.isChecked(),
            "response_timeout": self.responseTimeoutInput.value(),

            "use_rag": self.useRagCheck.isChecked(),
            "manual_path": self.manualPathInput.text(),
        }


        self.config = config
        self.accept()  # 关闭对话框，返回QDialog.Accepted状态


def loadModelConfigs(config_path):
    """
    加载模型配置

    参数:
        config_path (str): 配置文件路径

    返回:
        list: 模型配置列表，每个配置是一个字典

    从JSON文件加载保存的模型配置，如果文件不存在或出错，返回空列表
    """
    try:
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                configs = json.load(f)


                if not isinstance(configs, list):
                    logger = CustomLogger()
                    logger.error("配置文件格式错误，应为列表")
                    return []


                return configs
        return []
    except Exception as e:
        logger = CustomLogger()
        logger.error(f"加载AI模型配置失败: {str(e)}")
        return []


def saveModelConfigs(configs, config_path):
    """
    保存模型配置

    参数:
        configs (list): 模型配置列表
        config_path (str): 保存配置的文件路径

    返回:
        bool: 保存成功返回True，失败返回False

    将模型配置列表保存到JSON文件，确保目录存在
    """
    try:

        os.makedirs(os.path.dirname(config_path), exist_ok=True)


        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(
                configs, f, ensure_ascii=False, indent=2
            )  # 使用缩进美化JSON，保留中文
        return True
    except Exception as e:
        logger = CustomLogger()
        logger.error(f"保存AI模型配置失败: {str(e)}")
        return False
