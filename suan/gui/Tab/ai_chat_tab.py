from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QPushButton,
    QLineEdit,
    QLabel,
    QApplication,
    QComboBox,
    QToolButton,
    QDialog,
    QFormLayout,
    QTabWidget,
    QMessageBox,
    QCheckBox,
    QSlider,
    QSpinBox,
    QFileDialog,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QPixmap, QTextOption, QTextCursor
import ollama
import json
import os
import requests
import psutil
import time
from custom_logger import CustomLogger

# 导入RAG相关依赖 - 更健壮的错误处理
import PyPDF2

# 全局常量定义
SENTENCE_TRANSFORMER_AVAILABLE = False
SENTENCE_TRANSFORMER_ERROR = None

try:
    # 首先验证 PyTorch 版本
    import torch
    # if not torch.__version__.startswith(('1.13', '2.0')):
    #     raise ImportError(f"不兼容的 PyTorch 版本 {torch.__version__}，需要 1.13.x 或 2.0.x")
        
    from sentence_transformers import SentenceTransformer, util
    SENTENCE_TRANSFORMER_AVAILABLE = True
    
except Exception as e:
    import traceback
    error_message = str(e)
    error_traceback = traceback.format_exc()
    SENTENCE_TRANSFORMER_ERROR = error_message
    
    # 记录详细错误信息到日志
    logger = CustomLogger()
    logger.error(f"无法导入sentence_transformers库: {error_message}")
    logger.debug(f"详细错误: {error_traceback}")
    
    # 如果是特定的版本不兼容错误，提供更具体的错误信息
    if "LRScheduler" in error_message:
        logger.error("检测到版本不兼容问题。请按照以下步骤解决：\n"
                    "1. 卸载现有包：\n"
                    "   pip uninstall torch transformers sentence-transformers\n"
                    "2. 安装兼容版本：\n"
                    "   pip install torch==1.13.1\n"
                    "   pip install transformers==4.30.2\n"
                    "   pip install sentence-transformers==2.2.2")


class ModelConfigDialog(QDialog):
    """AI模型配置对话框"""

    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self.setWindowTitle("AI模型配置")
        self.setMinimumWidth(450)
        self.config = config or {}
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        # 创建选项卡布局，分离基本设置和高级设置
        tabWidget = QTabWidget()

        # 基本设置选项卡
        basicTab = QWidget()
        basicForm = QFormLayout(basicTab)

        # 模型名称
        self.nameInput = QLineEdit(self.config.get("name", ""))
        basicForm.addRow("配置名称:", self.nameInput)

        # 模型类型选择 (公有/私有)
        self.modelTypeCombo = QComboBox()
        self.modelTypeCombo.addItems(
            ["公有模型 (仅需API地址)", "私有模型 (需要API密钥)"]
        )

        # 调整存储的模型类型与显示的对应关系
        if "type" in self.config:
            self.modelTypeCombo.setCurrentIndex(
                0 if self.config["type"] == "public" else 1
            )
        else:
            self.modelTypeCombo.setCurrentIndex(0)

        self.modelTypeCombo.currentIndexChanged.connect(self.updateFormFields)
        basicForm.addRow("模型类型:", self.modelTypeCombo)

        # 主机/API端点
        self.hostInput = QLineEdit(self.config.get("host", "127.0.0.1"))
        basicForm.addRow("主机/端点:", self.hostInput)

        # 端口
        self.portInput = QLineEdit(self.config.get("port", "11434"))
        basicForm.addRow("端口:", self.portInput)

        # API密钥
        self.apiKeyInput = QLineEdit(self.config.get("api_key", ""))
        self.apiKeyInput.setEchoMode(QLineEdit.Password)
        basicForm.addRow("API密钥:", self.apiKeyInput)

        # 模型名称
        self.modelNameInput = QLineEdit(self.config.get("model_name", ""))
        basicForm.addRow("模型名称:", self.modelNameInput)

        # 添加基本设置选项卡
        tabWidget.addTab(basicTab, "基本设置")

        # 高级设置选项卡
        advancedTab = QWidget()
        advancedForm = QFormLayout(advancedTab)

        # 模型参数设置
        self.temperatureLabel = QLabel("温度:")
        self.temperatureSlider = QSlider(Qt.Horizontal)
        self.temperatureSlider.setRange(0, 100)  # 0-1.0的温度值，乘以100
        self.temperatureValue = self.config.get("temperature", 0.7)
        self.temperatureSlider.setValue(int(self.temperatureValue * 100))
        self.temperatureDisplay = QLabel(f"{self.temperatureValue:.2f}")
        self.temperatureSlider.valueChanged.connect(self.updateTemperatureDisplay)

        tempLayout = QHBoxLayout()
        tempLayout.addWidget(self.temperatureSlider)
        tempLayout.addWidget(self.temperatureDisplay)

        advancedForm.addRow(self.temperatureLabel, tempLayout)

        # 最大输出长度
        self.maxTokensLabel = QLabel("最大输出长度:")
        self.maxTokensInput = QSpinBox()
        self.maxTokensInput.setRange(100, 8000)
        self.maxTokensInput.setSingleStep(100)
        self.maxTokensInput.setValue(self.config.get("max_tokens", 1000))
        advancedForm.addRow(self.maxTokensLabel, self.maxTokensInput)

        # 系统提示词
        self.systemPromptLabel = QLabel("系统提示词:")
        self.systemPromptInput = QTextEdit()
        self.systemPromptInput.setPlaceholderText(
            "输入系统提示词，定义AI助手的行为和角色..."
        )
        self.systemPromptInput.setText(self.config.get("system_prompt", ""))
        self.systemPromptInput.setMaximumHeight(100)
        advancedForm.addRow(self.systemPromptLabel, self.systemPromptInput)

        # 添加RAG使用手册选项
        self.useRagCheck = QCheckBox("导入使用手册(使用RAG技术)")
        self.useRagCheck.setChecked(self.config.get("use_rag", False))
        self.useRagCheck.setToolTip("启用后模型会参考使用手册内容回答问题")
        self.useRagCheck.stateChanged.connect(self.updateRagOptions)

        # 手册文件选择
        self.manualPathLayout = QHBoxLayout()
        self.manualPathInput = QLineEdit(self.config.get("manual_path", ""))
        self.manualPathInput.setPlaceholderText("选择PDF使用手册路径...")
        self.manualPathInput.setEnabled(self.config.get("use_rag", False))

        self.browseManualBtn = QPushButton("浏览...")
        self.browseManualBtn.clicked.connect(self.browseManualFile)
        self.browseManualBtn.setEnabled(self.config.get("use_rag", False))

        self.manualPathLayout.addWidget(self.manualPathInput)
        self.manualPathLayout.addWidget(self.browseManualBtn)

        # 添加到表单
        advancedForm.addRow(self.useRagCheck, QWidget())  # 使用空的QWidget作为占位符
        advancedForm.addRow("使用手册路径:", self.manualPathLayout)

        # 添加高级设置选项卡
        tabWidget.addTab(advancedTab, "高级设置")

        # 分析选项卡
        analyticsTab = QWidget()
        analyticsForm = QFormLayout(analyticsTab)

        # 模型分析选项
        self.enableAnalyticsCheck = QCheckBox("启用性能分析")
        self.enableAnalyticsCheck.setChecked(self.config.get("enable_analytics", False))
        analyticsForm.addRow("性能分析:", self.enableAnalyticsCheck)

        self.logQueriesCheck = QCheckBox("记录查询")
        self.logQueriesCheck.setChecked(self.config.get("log_queries", False))
        analyticsForm.addRow("查询日志:", self.logQueriesCheck)

        self.responseTimeoutInput = QSpinBox()
        self.responseTimeoutInput.setRange(5, 300)
        self.responseTimeoutInput.setSingleStep(5)
        self.responseTimeoutInput.setValue(self.config.get("response_timeout", 60))
        analyticsForm.addRow("响应超时(秒):", self.responseTimeoutInput)

        # 添加分析选项卡
        tabWidget.addTab(analyticsTab, "分析与日志")

        layout.addWidget(tabWidget)

        # 按钮
        buttonLayout = QHBoxLayout()
        self.saveBtn = QPushButton("保存")
        self.saveBtn.clicked.connect(self.saveConfig)
        self.cancelBtn = QPushButton("取消")
        self.cancelBtn.clicked.connect(self.reject)
        self.testBtn = QPushButton("测试连接")
        self.testBtn.clicked.connect(self.testConnection)

        buttonLayout.addWidget(self.cancelBtn)
        buttonLayout.addWidget(self.testBtn)
        buttonLayout.addWidget(self.saveBtn)

        layout.addLayout(buttonLayout)
        self.setLayout(layout)

        # 初始化表单显示
        self.updateFormFields()

    def updateTemperatureDisplay(self, value):
        """更新温度显示值"""
        temp = value / 100.0
        self.temperatureDisplay.setText(f"{temp:.2f}")
        self.temperatureValue = temp

    def testConnection(self):
        """测试模型连接"""
        # 获取当前表单值
        model_type = "public" if self.modelTypeCombo.currentIndex() == 0 else "private"
        host = self.hostInput.text()
        port = self.portInput.text()
        api_key = self.apiKeyInput.text()

        # 测试连接
        QApplication.setOverrideCursor(Qt.WaitCursor)

        try:
            # 公有模型
            if model_type == "public":
                url = f"http://{host}:{port}/api/tags"
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    QMessageBox.information(self, "连接成功", f"成功连接到服务器")
                else:
                    QMessageBox.warning(
                        self, "连接失败", f"连接失败: HTTP {response.status_code}"
                    )
            # 私有模型
            else:
                if not api_key:
                    QMessageBox.warning(self, "缺少API密钥", "私有模型需要提供API密钥")
                    return

                # 尝试基本连接
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

    def updateFormFields(self):
        """根据选择的模型类型更新表单字段显示"""
        model_type = self.modelTypeCombo.currentIndex()

        # 公有模型 - 不需要API密钥
        if model_type == 0:
            self.apiKeyInput.setEnabled(False)
            self.apiKeyInput.setPlaceholderText("公有模型不需要API密钥")
            self.hostInput.setPlaceholderText("127.0.0.1")
            self.portInput.setEnabled(True)
            self.portInput.setPlaceholderText("11434")
            self.modelNameInput.setPlaceholderText("模型名称，如：deepseek-coder")
        # 私有模型 - 需要API密钥
        else:
            self.apiKeyInput.setEnabled(True)
            self.apiKeyInput.setPlaceholderText("输入您的API密钥")
            self.hostInput.setPlaceholderText("https://api.example.com")
            self.portInput.setEnabled(False)
            self.modelNameInput.setPlaceholderText("模型部署名称")

    def updateRagOptions(self, state):
        """更新RAG选项可用性"""
        enabled = state == Qt.Checked
        self.manualPathInput.setEnabled(enabled)
        self.browseManualBtn.setEnabled(enabled)

        # 如果启用RAG但软件包不可用，显示警告
        if enabled and not SENTENCE_TRANSFORMER_AVAILABLE:
            QMessageBox.warning(
                self,
                "RAG功能不可用",
                "无法启用RAG功能，因为sentence_transformers库加载失败。\n\n"
                "可能原因:\n"
                "1. 未安装sentence_transformers库\n"
                "2. PyTorch和transformers版本不兼容\n\n"
                "建议:\n"
                "尝试运行: pip install sentence-transformers torch==1.13.1",
            )

    def browseManualFile(self):
        """选择使用手册PDF文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择使用手册PDF", "", "PDF文件 (*.pdf)"
        )
        if file_path:
            self.manualPathInput.setText(file_path)

    def saveConfig(self):
        """保存模型配置"""
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
            # 添加RAG相关配置
            "use_rag": self.useRagCheck.isChecked(),
            "manual_path": self.manualPathInput.text(),
        }

        self.config = config
        self.accept()


class AIChatTab(QWidget):
    modelConfigChanged = Signal()  # 信号：模型配置变更

    def __init__(self, parent=None):
        super().__init__()
        self.logger = CustomLogger()
        self.parent = parent
        self.client = None
        self.currentModelConfig = None
        self.modelConfigs = []
        self.configPath = os.path.join(
            os.path.expanduser("~"), ".stk", "ai_models.json"
        )

        # RAG相关属性
        self.manual_text = None
        self.sentence_model = None

        # 确保配置目录存在
        os.makedirs(os.path.dirname(self.configPath), exist_ok=True)

        # 加载已保存的模型配置
        self.loadModelConfigs()

        # 如果没有配置，添加默认配置
        if not self.modelConfigs:
            self.modelConfigs.append(
                {
                    "name": "默认公有模型",
                    "type": "public",
                    "host": "127.0.0.1",
                    "port": "11434",
                    "api_key": "",
                    "model_name": "deepseek-coder",
                    "temperature": 0.7,
                    "max_tokens": 1000,
                }
            )
            self.saveModelConfigs()

        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        # 模型选择区域
        modelSelectLayout = QHBoxLayout()
        self.modelSelectLabel = QLabel("选择AI模型:")
        self.modelCombo = QComboBox()
        self.updateModelCombo()

        self.addModelBtn = QToolButton()
        self.addModelBtn.setText("+")
        self.addModelBtn.setToolTip("添加新模型配置")
        self.addModelBtn.clicked.connect(self.addModelConfig)

        self.editModelBtn = QToolButton()
        self.editModelBtn.setText("⚙")
        self.editModelBtn.setToolTip("编辑当前模型配置")
        self.editModelBtn.clicked.connect(self.editModelConfig)

        self.deleteModelBtn = QToolButton()
        self.deleteModelBtn.setText("×")
        self.deleteModelBtn.setToolTip("删除当前模型配置")
        self.deleteModelBtn.clicked.connect(self.deleteModelConfig)

        modelSelectLayout.addWidget(self.modelSelectLabel)
        modelSelectLayout.addWidget(self.modelCombo, 1)
        modelSelectLayout.addWidget(self.addModelBtn)
        modelSelectLayout.addWidget(self.editModelBtn)
        modelSelectLayout.addWidget(self.deleteModelBtn)

        layout.addLayout(modelSelectLayout)

        # 聊天历史区域 - 增强设置
        self.chatHistory = QTextEdit()
        self.chatHistory.setReadOnly(True)
        self.chatHistory.setMinimumHeight(300)

        # 确保自动换行设置正确
        self.chatHistory.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.chatHistory.setLineWrapMode(QTextEdit.WidgetWidth)

        # 设置合适的字体和字号
        font = self.chatHistory.font()
        font.setPointSize(10)
        self.chatHistory.setFont(font)

        # 设置文本文档选项
        doc = self.chatHistory.document()
        option = doc.defaultTextOption()
        option.setAlignment(Qt.AlignLeft)
        option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        doc.setDefaultTextOption(option)

        layout.addWidget(self.chatHistory)

        # 输入区域
        inputLayout = QHBoxLayout()
        self.inputField = QLineEdit()
        self.inputField.setPlaceholderText("输入你的问题...")
        self.inputField.returnPressed.connect(self.sendMessage)
        self.sendButton = QPushButton("发送")
        self.sendButton.clicked.connect(self.sendMessage)
        inputLayout.addWidget(self.inputField)
        inputLayout.addWidget(self.sendButton)

        layout.addLayout(inputLayout)

        # 连接状态
        statusLayout = QHBoxLayout()
        self.statusLabel = QLabel("未连接")
        self.connectButton = QPushButton("连接")
        self.connectButton.clicked.connect(self.connectToModel)
        self.validateButton = QPushButton("连接情况")
        self.validateButton.clicked.connect(self.validateConnection)
        statusLayout.addWidget(QLabel("状态:"))
        statusLayout.addWidget(self.statusLabel)
        statusLayout.addStretch()
        statusLayout.addWidget(self.validateButton)
        statusLayout.addWidget(self.connectButton)

        layout.addLayout(statusLayout)

        self.setLayout(layout)

        # 连接模型选择变化事件
        self.modelCombo.currentIndexChanged.connect(self.onModelChanged)

        # 如果有默认配置，连接到第一个配置
        if self.modelConfigs:
            self.currentModelConfig = self.modelConfigs[0]
            self.modelCombo.setCurrentIndex(0)

    def updateModelCombo(self):
        """更新模型下拉框"""
        self.modelCombo.clear()
        for config in self.modelConfigs:
            # 显示模型类型
            model_type = "公有模型" if config.get("type") == "public" else "私有模型"
            display_name = f"{config['name']} [{model_type}] ({config['model_name']})"
            self.modelCombo.addItem(display_name)

    def onModelChanged(self, index):
        """模型选择变更处理"""
        if index >= 0 and index < len(self.modelConfigs):
            self.currentModelConfig = self.modelConfigs[index]
            self.client = None  # 重置客户端
            self.statusLabel.setText("未连接")
            self.chatHistory.append(
                f"<b>系统:</b> 已选择模型配置: {self.currentModelConfig['name']}<br>"
            )

    def addModelConfig(self):
        """添加新模型配置"""
        dialog = ModelConfigDialog(self)
        if dialog.exec_():
            config = dialog.config
            self.modelConfigs.append(config)
            self.saveModelConfigs()
            self.updateModelCombo()
            # 选择新添加的配置
            self.modelCombo.setCurrentIndex(len(self.modelConfigs) - 1)

    def editModelConfig(self):
        """编辑当前模型配置"""
        if not self.currentModelConfig:
            return

        index = self.modelCombo.currentIndex()
        dialog = ModelConfigDialog(self, self.currentModelConfig.copy())
        if dialog.exec_():
            self.modelConfigs[index] = dialog.config
            self.currentModelConfig = self.modelConfigs[index]
            self.saveModelConfigs()
            self.updateModelCombo()
            self.modelCombo.setCurrentIndex(index)
            # 如果已连接，断开后重新连接
            if self.client:
                self.client = None
                self.statusLabel.setText("配置已更改，需要重新连接")

    def deleteModelConfig(self):
        """删除当前模型配置"""
        if not self.currentModelConfig or len(self.modelConfigs) <= 1:
            QMessageBox.warning(self, "警告", "至少保留一个模型配置")
            return

        index = self.modelCombo.currentIndex()
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确认删除配置 '{self.currentModelConfig['name']}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            self.modelConfigs.pop(index)
            self.saveModelConfigs()
            self.updateModelCombo()
            # 切换到第一个配置
            self.modelCombo.setCurrentIndex(0)

    def loadModelConfigs(self):
        """加载模型配置"""
        try:
            if os.path.exists(self.configPath):
                with open(self.configPath, "r", encoding="utf-8") as f:
                    self.modelConfigs = json.load(f)
        except Exception as e:
            self.logger.error(f"加载AI模型配置失败: {str(e)}")
            self.modelConfigs = []

    def saveModelConfigs(self):
        """保存模型配置"""
        try:
            with open(self.configPath, "w", encoding="utf-8") as f:
                json.dump(self.modelConfigs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"保存AI模型配置失败: {str(e)}")

    def connectToModel(self):
        """连接到选定的模型"""
        if not self.currentModelConfig:
            self.chatHistory.append("<b>系统:</b> 请先选择或添加一个模型配置<br>")
            return

        config = self.currentModelConfig
        model_type = config["type"]  # public/private

        try:
            # 公有模型 (无需API密钥)
            if model_type == "public":
                return self.connectToPublicModel()
            # 私有模型 (需要API密钥)
            else:
                return self.connectToPrivateModel()

        except Exception as e:
            self.statusLabel.setText(f"连接失败")
            self.chatHistory.append(f"<b>系统:</b> 连接失败: {str(e)}<br>")
            self.logger.error(f"连接模型失败: {str(e)}")
            return False

    def connectToPublicModel(self):
        """连接到公有模型"""
        config = self.currentModelConfig
        host = config["host"]
        port = config["port"]
        model_name = config["model_name"] or "deepseek-coder"

        try:
            # 创建客户端
            self.client = ollama.Client(host=f"http://{host}:{port}")

            # 测试连接
            response = requests.get(f"http://{host}:{port}/api/tags", timeout=5)
            if response.status_code != 200:
                raise Exception(f"服务器返回状态码: {response.status_code}")

            # 获取模型列表
            models_info = self.client.list()
            model_names = []

            if isinstance(models_info, dict) and "models" in models_info:
                for model in models_info.get("models", []):
                    if isinstance(model, dict) and "name" in model:
                        model_names.append(model["name"])

            # 检查模型是否可用
            if model_names:
                if model_name not in model_names:
                    self.chatHistory.append(
                        f"<b>系统:</b> 警告: 模型 '{model_name}' 未在服务器上找到<br>"
                    )
                    self.chatHistory.append(
                        f"<b>系统:</b> 可用模型: {', '.join(model_names)}<br>"
                    )
            else:
                self.chatHistory.append(f"<b>系统:</b> 警告: 未检测到任何可用模型<br>")

            self.statusLabel.setText(f"已连接 ({host}:{port})")
            self.chatHistory.append(
                f"<b>系统:</b> 已连接到服务器，使用模型: {model_name}<br>"
            )
            return True

        except Exception as e:
            self.statusLabel.setText(f"连接失败")
            self.chatHistory.append(f"<b>系统:</b> 连接失败: {str(e)}<br>")
            self.logger.error(f"连接公有模型失败: {str(e)}")
            return False

    def connectToPrivateModel(self):
        """连接到私有模型"""
        config = self.currentModelConfig
        api_key = config["api_key"]
        host = config["host"]
        model_name = config["model_name"]

        if not api_key:
            self.chatHistory.append(
                "<b>系统:</b> 错误: 使用私有模型需要提供API密钥<br>"
            )
            return False

        try:
            # 创建简单的API客户端记录
            self.client = {
                "type": "private",
                "base_url": host,
                "api_key": api_key,
                "model": model_name,
                "headers": {"Authorization": f"Bearer {api_key}"},
            }

            self.statusLabel.setText(f"已连接 (私有API)")
            self.chatHistory.append(
                f"<b>系统:</b> 已连接到私有API，使用模型: {model_name}<br>"
            )
            return True

        except Exception as e:
            self.statusLabel.setText(f"连接失败")
            self.chatHistory.append(f"<b>系统:</b> 连接私有API失败: {str(e)}<br>")
            self.logger.error(f"连接私有API失败: {str(e)}")
            return False

    def extract_text_from_pdf(self, pdf_path):
        """从PDF中提取文本"""
        if not os.path.exists(pdf_path):
            self.logger.error(f"PDF文件不存在: {pdf_path}")
            return ""

        try:
            text = ""
            with open(pdf_path, "rb") as file:
                reader = PyPDF2.PdfReader(file)
                for page in reader.pages:
                    text += page.extract_text()
            return text
        except Exception as e:
            self.logger.error(f"提取PDF文本失败: {str(e)}")
            return ""

    def load_sentence_model(self):
        """加载句子变换器模型"""
        if not SENTENCE_TRANSFORMER_AVAILABLE:
            error_hint = ""
            if SENTENCE_TRANSFORMER_ERROR and "LRScheduler" in SENTENCE_TRANSFORMER_ERROR:
                error_hint = ("请运行以下命令安装兼容版本：\n"
                             "pip uninstall torch transformers sentence-transformers\n"
                             "pip install torch==1.13.1\n"
                             "pip install transformers==4.30.2\n"
                             "pip install sentence-transformers==2.2.2")
            
            self.logger.warning(f"sentence-transformers库不可用，RAG功能将被禁用\n{error_hint}")
            self.chatHistory.append(
                "<b>系统:</b> ⚠️ sentence-transformers库不可用，RAG功能被禁用。<br>"
                f"错误信息: {SENTENCE_TRANSFORMER_ERROR}<br><br>"
                f"{error_hint}<br>"
            )
            return False

        try:
            self.chatHistory.append("<b>系统:</b> 正在加载语义搜索模型...<br>")
            self.sentence_model = SentenceTransformer("all-MiniLM-L6-v2")
            return True
        except Exception as e:
            self.logger.error(f"加载sentence-transformer模型失败: {str(e)}")
            self.chatHistory.append(
                f"<b>系统:</b> ❌ 加载语义搜索模型失败: {str(e)}<br>"
            )
            return False

    def sendMessage(self):
        if not self.client:
            if not self.connectToModel():
                return

        question = self.inputField.text().strip()
        if not question:
            return

        self.chatHistory.append(f"<b>用户:</b> {question}<br>")
        self.inputField.clear()

        try:
            # 添加性能分析
            start_time = time.time()

            # 检查内存使用情况
            self.checkMemoryUsage()

            config = self.currentModelConfig
            model_type = config["type"]  # public/private
            model_name = config["model_name"]

            # 获取高级参数
            temperature = config.get("temperature", 0.7)
            max_tokens = config.get("max_tokens", 1000)
            system_prompt = config.get("system_prompt", "")
            response_timeout = config.get("response_timeout", 60)

            # 检查是否启用RAG
            use_rag = config.get("use_rag", False)
            manual_path = config.get("manual_path", "")

            # 如果启用RAG但sentence_transformers不可用，使用普通模式
            if use_rag and not SENTENCE_TRANSFORMER_AVAILABLE:
                self.chatHistory.append(
                    "<b>系统:</b> ⚠️ RAG功能不可用，将使用普通模式回答。<br>"
                )
                use_rag = False

            # 如果启用RAG且指定了手册路径
            if use_rag and manual_path and os.path.exists(manual_path):
                # 如果尚未加载手册文本，加载它
                if self.manual_text is None:
                    self.chatHistory.append("<b>系统:</b> 正在加载使用手册...<br>")
                    self.manual_text = self.extract_text_from_pdf(manual_path)
                    if not self.manual_text:
                        self.chatHistory.append(
                            "<b>系统:</b> ⚠️ 无法提取手册内容，将使用普通模式<br>"
                        )
                        use_rag = False

                # 如果启用RAG但没有加载sentence模型，尝试加载
                if use_rag and self.sentence_model is None:
                    if not self.load_sentence_model():
                        use_rag = False
            else:
                use_rag = False

            # 构建消息
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})

            # 如果使用RAG，提取相关上下文并添加到提示中
            if use_rag and self.manual_text:
                # 简化RAG处理，不使用sentence_transformers进行相似度计算
                # 而是直接使用整个手册作为上下文
                context = self.manual_text

                # 构造带有上下文的提示
                rag_prompt = (
                    f"请基于以下软件使用手册内容回答问题。如果手册中没有相关信息，请明确说明。\n\n"
                    f"使用手册内容:\n{context}\n\n"
                    f"用户问题: {question}"
                )
                messages.append({"role": "user", "content": rag_prompt})
            else:
                # 普通模式，直接添加用户问题
                messages.append({"role": "user", "content": question})

            # 开始生成回答
            self.chatHistory.append("<b>AI:</b> ")

            # 获取光标并移动到末尾，为使用insertPlainText做准备
            cursor = self.chatHistory.textCursor()
            cursor.movePosition(QTextCursor.End)  # 使用QTextCursor.End而不是cursor.End
            self.chatHistory.setTextCursor(cursor)

            response_text = ""

            # 公有模型 - 使用Ollama API
            if model_type == "public":
                # 修复：将temperature移到options字典中
                stream = self.client.chat(
                    model=model_name,
                    messages=messages,
                    stream=True,
                    options={"num_predict": max_tokens, "temperature": temperature},
                )

                for chunk in stream:
                    content = chunk["message"]["content"]
                    # 使用insertPlainText而不是append，确保文本连续
                    self.chatHistory.insertPlainText(content)
                    response_text += content
                    self.chatHistory.ensureCursorVisible()
                    QApplication.processEvents()  # 确保UI更新

            # 私有模型 - 使用自定义API
            else:
                headers = self.client["headers"]
                url = self.client["base_url"]
                if not url.startswith("http"):
                    url = f"http://{url}"

                response = requests.post(
                    f"{url}/chat/completions",
                    headers=headers,
                    json={
                        "model": self.client["model"],
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                    timeout=response_timeout,
                )

                if response.status_code == 200:
                    content = (
                        response.json()
                        .get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    )
                    # 使用insertPlainText而不是append
                    self.chatHistory.insertPlainText(content)
                    response_text += content
                else:
                    raise Exception(f"API返回错误: {response.status_code}")

            # 添加换行，确保下一个消息从新行开始
            self.chatHistory.insertPlainText("\n\n")

            # 记录分析数据
            if config.get("enable_analytics", False):
                end_time = time.time()
                response_time = round((end_time - start_time) * 1000)
                self.chatHistory.append(
                    f"<span style='color: gray; font-size: 9px;'>响应时间: {response_time}ms, "
                    f"输出长度: {len(response_text)} 字符</span><br>"
                )

                # 记录查询日志
                if config.get("log_queries", False):
                    self.logQuery(question, response_text, response_time)

        except Exception as e:
            error_msg = str(e)
            self.chatHistory.append(f"<b>系统:</b> 获取回答时出错: {error_msg}<br>")
            self.logger.error(f"获取AI回答失败: {error_msg}")

            # 处理特定错误类型
            self.handleSpecificErrors(error_msg)

    def validateConnection(self):
        """验证当前选择的模型连接"""
        if not self.currentModelConfig:
            self.chatHistory.append("<b>系统:</b> 请先选择一个模型配置<br>")
            return

        config = self.currentModelConfig
        self.chatHistory.append(f"<b>系统:</b> 正在验证 '{config['name']}' 连接...<br>")
        try:
            model_type = config["type"]

            # 公有模型验证
            if (model_type == "public"):
                self.validatePublicModel()
            # 私有模型验证
            else:
                self.validatePrivateModel()

        except Exception as e:
            self.chatHistory.append(f"<b>系统:</b> 验证过程中出错: {str(e)}<br>")
            self.logger.error(f"验证连接时出错: {str(e)}")

    def validatePublicModel(self):
        """验证公有模型连接"""
        config = self.currentModelConfig
        host = config["host"]
        port = config["port"]
        model_name = config["model_name"] or "deepseek-coder"

        try:
            import socket
            import requests

            # 测试TCP连接
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            sock.connect((host, int(port)))
            sock.close()
            self.chatHistory.append(f"<b>系统:</b> ✅ TCP连接成功<br>")

            # 测试API
            response = requests.get(f"http://{host}:{port}/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if "models" in data:
                    models = [model["name"] for model in data["models"]]
                    self.chatHistory.append(f"<b>系统:</b> ✅ API连接成功<br>")
                    self.chatHistory.append(
                        f"<b>系统:</b> 📋 可用模型 ({len(models)}):<br>"
                    )
                    for i, model in enumerate(models, 1):
                        self.chatHistory.append(f"<b>系统:</b> {i}. {model}<br>")

                    if model_name in models:
                        self.chatHistory.append(
                            f"<b>系统:</b> ✅ 当前选择的模型 '{model_name}' 可用<br>"
                        )
                    else:
                        self.chatHistory.append(
                            f"<b>系统:</b> ⚠️ 当前选择的模型 '{model_name}' 在服务器上不可用<br>"
                        )
                else:
                    self.chatHistory.append(
                        f"<b>系统:</b> ✅ API连接成功，但返回的数据格式不符合预期<br>"
                    )
            else:
                self.chatHistory.append(
                    f"<b>系统:</b> ❌ API请求返回错误状态码: {response.status_code}<br>"
                )
        except Exception as e:
            self.chatHistory.append(f"<b>系统:</b> ❌ 验证失败: {str(e)}<br>")

    def validatePrivateModel(self):
        """验证私有模型连接"""
        config = self.currentModelConfig
        host = config["host"]
        api_key = config["api_key"]
        if not api_key:
            self.chatHistory.append("<b>系统:</b> ❌ 缺少API密钥<br>")
            return

        try:
            import requests

            # 设置请求头
            headers = {"Authorization": f"Bearer {api_key}"}

            # 组合URL
            url = host
            if not url.startswith("http"):
                url = f"http://{url}"

            # 尝试一个简单的GET请求
            response = requests.get(url, headers=headers, timeout=5)
            self.chatHistory.append(
                f"<b>系统:</b> ✅ 连接成功，状态码: {response.status_code}<br>"
            )

            # 尝试获取模型列表
            try:
                models_response = requests.get(
                    f"{url}/models", headers=headers, timeout=5
                )

                if models_response.status_code == 200:
                    models_data = models_response.json()
                    if "data" in models_data and isinstance(models_data["data"], list):
                        models = [
                            model.get("id", "Unknown") for model in models_data["data"]
                        ]
                        self.chatHistory.append(
                            f"<b>系统:</b> 📋 API返回的模型列表 (前5个):<br>"
                        )
                        for i, model_id in enumerate(models[:5], 1):
                            self.chatHistory.append(f"<b>系统:</b> {i}. {model_id}<br>")
            except:
                # 忽略模型列表获取错误
                pass

        except Exception as e:
            self.chatHistory.append(f"<b>系统:</b> ❌ 验证失败: {str(e)}<br>")

    def logQuery(self, question, response, response_time):
        """记录查询日志"""
        try:
            log_dir = os.path.join(os.path.expanduser("~"), ".stk", "logs")
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, "chat_queries.log")
            with open(log_file, "a", encoding="utf-8") as f:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                model_info = f"{self.currentModelConfig['name']} ({self.currentModelConfig['model_name']})"
                log_entry = f"[{timestamp}] 模型: {model_info}\n问: {question}\n答: {response}\n响应时间: {response_time}ms\n{'='*50}\n"
                f.write(log_entry)
        except Exception as e:
            self.logger.error(f"记录查询日志时出错: {str(e)}")

    def checkMemoryUsage(self):
        """检查系统内存使用情况并提供警告"""
        try:
            mem = psutil.virtual_memory()
            available_gb = mem.available / (1024**3)

            # 根据模型类型估计内存需求
            model_type = self.currentModelConfig["type"]
            model_name = self.currentModelConfig["model_name"]

            # 基于模型名称估计内存需求
            memory_requirement = 1.0  # 默认值
            if "ollama" in model_type:
                if "1.5b" in model_name or "1b" in model_name:
                    memory_requirement = 1.2
                elif "7b" in model_name:
                    memory_requirement = 4.0
                elif "13b" in model_name:
                    memory_requirement = 8.0
                elif "30b" in model_name:
                    memory_requirement = 16.0

            # 内存不足警告
            if available_gb < memory_requirement:
                self.chatHistory.append(
                    f"<b>系统:</b> ⚠️ 警告: 系统可用内存不足 ({available_gb:.2f} GB)，"
                    f"模型可能需要至少 {memory_requirement} GB。<br>"
                    f"请关闭其他应用程序释放内存，或使用更小的模型。<br>"
                )

                # 尝试释放内存
                import gc

                gc.collect()
        except:
            # 忽略内存检查中的错误
            pass

    def handleSpecificErrors(self, error_msg):
        """处理特定的错误类型"""
        if "requires more system memory" in error_msg or "memory" in error_msg.lower():
            self.chatHistory.append(
                f"<b>系统:</b> 这是内存不足错误。请尝试:<br>"
                f"1. 关闭其他应用程序释放内存<br>"
                f"2. 增加服务器的虚拟内存/页面文件大小<br>"
                f"3. 使用更小的模型<br>"
            )
            try:
                mem = psutil.virtual_memory()
                self.chatHistory.append(
                    f"<b>系统:</b> 当前内存状态: 总计 {mem.total/(1024**3):.2f} GB, "
                    f"可用 {mem.available/(1024**3):.2f} GB, 使用率 {mem.percent}%<br>"
                )
            except:
                pass
        elif "API key" in error_msg or "authentication" in error_msg.lower():
            self.chatHistory.append(
                f"<b>系统:</b> 这似乎是API密钥认证错误。请检查:<br>"
                f"1. API密钥是否正确<br>"
                f"2. API密钥是否有效<br>"
                f"3. 服务器是否需要其他认证方式<br>"
            )
        elif "timeout" in error_msg.lower():
            self.chatHistory.append(
                f"<b>系统:</b> 连接超时。请检查:<br>"
                f"1. 服务器是否可访问<br>"
                f"2. 是否需要代理<br>"
                f"3. 网络连接是否稳定<br>"
            )
