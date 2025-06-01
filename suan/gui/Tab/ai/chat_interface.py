from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QComboBox,
    QToolButton,
    QFrame,
    QScrollArea,
    QMessageBox,
    QApplication,
    QProgressDialog,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon

import os
import json
import time
import traceback
import ollama

from .message_components import ChatHistoryWidget
from .model_config import ModelConfigDialog, loadModelConfigs, saveModelConfigs
from .workers import RagWorker, ResponseGenerationWorker
from .utils import (
    get_config_path,
    ensure_config_dir,
    log_query,
    check_memory_usage,
    estimate_model_memory_requirement,
    connect_to_ollama,
    validate_ollama_connection,
    is_sentence_transformer_available,
)
from custom_logger import CustomLogger


class AIChatTab(QWidget):
    """AI聊天界面主类"""

    modelConfigChanged = Signal()  # 信号：模型配置变更

    def __init__(self, parent=None):
        super().__init__()
        self.logger = CustomLogger()
        self.parent = parent
        self.client = None
        self.currentModelConfig = None
        self.modelConfigs = []


        self.rag_worker = None
        self.response_worker = None
        self.progress_dialog = None


        self.configPath = get_config_path()
        ensure_config_dir()


        self.loadModelConfigs()


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
        """初始化界面"""
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)


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


        chatHistoryContainer = QFrame()
        chatHistoryContainer.setFrameShape(QFrame.StyledPanel)
        chatHistoryContainer.setFrameShadow(QFrame.Sunken)
        chatHistoryContainer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)


        scrollArea = QScrollArea()
        scrollArea.setWidgetResizable(True)
        scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scrollArea.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)


        self.chatHistory = ChatHistoryWidget()
        scrollArea.setWidget(self.chatHistory)


        chatHistoryLayout = QVBoxLayout(chatHistoryContainer)
        chatHistoryLayout.setContentsMargins(0, 0, 0, 0)
        chatHistoryLayout.addWidget(scrollArea)

        layout.addWidget(chatHistoryContainer)


        inputLayout = QHBoxLayout()
        self.inputField = QLineEdit()
        self.inputField.setPlaceholderText("输入你的问题...")
        self.inputField.returnPressed.connect(self.sendMessage)
        self.sendButton = QPushButton("发送")
        self.sendButton.setIcon(QIcon.fromTheme("document-send"))
        self.sendButton.clicked.connect(self.sendMessage)


        self.clearButton = QPushButton("清除历史")
        self.clearButton.clicked.connect(self.clearChatHistory)

        inputLayout.addWidget(self.inputField)
        inputLayout.addWidget(self.sendButton)
        inputLayout.addWidget(self.clearButton)

        layout.addLayout(inputLayout)


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


        self.modelCombo.currentIndexChanged.connect(self.onModelChanged)


        if self.modelConfigs:
            self.currentModelConfig = self.modelConfigs[0]
            self.modelCombo.setCurrentIndex(0)

    def clearChatHistory(self):
        """清除聊天历史"""
        reply = QMessageBox.question(
            self,
            "确认清除",
            "确定要清除所有聊天历史记录吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            self.chatHistory.clear()

            system_message = self.chatHistory.addAIMessage("聊天历史已清除")
            system_message.sender_label.setText("系统")

    def updateModelCombo(self):
        """更新模型下拉框"""
        self.modelCombo.clear()
        for config in self.modelConfigs:

            model_type = "公有模型" if config.get("type") == "public" else "私有模型"
            display_name = f"{config['name']} [{model_type}] ({config['model_name']})"
            self.modelCombo.addItem(display_name)

    def onModelChanged(self, index):
        """模型选择变更处理"""
        if index >= 0 and index < len(self.modelConfigs):
            self.currentModelConfig = self.modelConfigs[index]
            self.client = None  # 重置客户端
            self.statusLabel.setText("未连接")


            system_message = self.chatHistory.addAIMessage(
                f"已选择模型配置: {self.currentModelConfig['name']}"
            )
            system_message.sender_label.setText("系统")

    def loadModelConfigs(self):
        """加载模型配置"""
        self.modelConfigs = loadModelConfigs(self.configPath)

    def saveModelConfigs(self):
        """保存模型配置"""
        saveModelConfigs(self.modelConfigs, self.configPath)

    def addModelConfig(self):
        """添加新模型配置"""
        dialog = ModelConfigDialog(self)
        if dialog.exec_():
            config = dialog.config
            self.modelConfigs.append(config)
            self.saveModelConfigs()
            self.updateModelCombo()

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

            if self.client:
                self.client = None
                self.statusLabel.setText("配置已更改，需要重新连接")


                system_message = self.chatHistory.addAIMessage(
                    "模型配置已更改，需要重新连接"
                )
                system_message.sender_label.setText("系统")

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

            self.modelCombo.setCurrentIndex(0)

    def connectToModel(self):
        """连接到选定的模型"""
        if not self.currentModelConfig:

            system_message = self.chatHistory.addAIMessage("请先选择或添加一个模型配置")
            system_message.sender_label.setText("系统")
            return

        config = self.currentModelConfig
        model_type = config["type"]  # public/private

        try:

            if model_type == "public":
                return self.connectToPublicModel()

            else:
                return self.connectToPrivateModel()

        except Exception as e:
            self.statusLabel.setText(f"连接失败")


            system_message = self.chatHistory.addAIMessage(f"连接失败: {str(e)}")
            system_message.sender_label.setText("系统")

            self.logger.error(f"连接模型失败: {str(e)}")
            return False

    def connectToPublicModel(self):
        """连接到公有模型"""
        config = self.currentModelConfig
        host = config["host"]
        port = config["port"]
        model_name = config["model_name"] or "deepseek-coder"

        try:

            self.client, model_names, error = connect_to_ollama(host, port)

            if error:
                raise Exception(error)


            if model_names:
                if model_name not in model_names:

                    warning_message = self.chatHistory.addAIMessage(
                        f"警告: 模型 '{model_name}' 未在服务器上找到\n"
                        f"可用模型: {', '.join(model_names)}"
                    )
                    warning_message.sender_label.setText("系统")
            else:

                warning_message = self.chatHistory.addAIMessage(
                    "警告: 未检测到任何可用模型"
                )
                warning_message.sender_label.setText("系统")

            self.statusLabel.setText(f"已连接 ({host}:{port})")


            success_message = self.chatHistory.addAIMessage(
                f"已连接到服务器，使用模型: {model_name}"
            )
            success_message.sender_label.setText("系统")

            return True

        except Exception as e:
            self.statusLabel.setText(f"连接失败")


            error_message = self.chatHistory.addAIMessage(f"连接失败: {str(e)}")
            error_message.sender_label.setText("系统")

            self.logger.error(f"连接公有模型失败: {str(e)}")
            return False

    def connectToPrivateModel(self):
        """连接到私有模型"""
        config = self.currentModelConfig
        api_key = config["api_key"]
        host = config["host"]
        model_name = config["model_name"]

        if not api_key:

            error_message = self.chatHistory.addAIMessage(
                "错误: 使用私有模型需要提供API密钥"
            )
            error_message.sender_label.setText("系统")
            return False

        try:

            self.client = {
                "type": "private",
                "base_url": host,
                "api_key": api_key,
                "model": model_name,
                "headers": {"Authorization": f"Bearer {api_key}"},
            }

            self.statusLabel.setText(f"已连接 (私有API)")


            success_message = self.chatHistory.addAIMessage(
                f"已连接到私有API，使用模型: {model_name}"
            )
            success_message.sender_label.setText("系统")

            return True

        except Exception as e:
            self.statusLabel.setText(f"连接失败")


            error_message = self.chatHistory.addAIMessage(f"连接私有API失败: {str(e)}")
            error_message.sender_label.setText("系统")

            self.logger.error(f"连接私有API失败: {str(e)}")
            return False

    def validateConnection(self):
        """验证当前选择的模型连接"""
        if not self.currentModelConfig:

            system_message = self.chatHistory.addAIMessage("请先选择一个模型配置")
            system_message.sender_label.setText("系统")
            return

        config = self.currentModelConfig


        system_message = self.chatHistory.addAIMessage(
            f"正在验证 '{config['name']}' 连接..."
        )
        system_message.sender_label.setText("系统")

        try:
            model_type = config["type"]


            if model_type == "public":
                self.validatePublicModel()

            else:
                self.validatePrivateModel()

        except Exception as e:

            error_message = self.chatHistory.addAIMessage(f"验证过程中出错: {str(e)}")
            error_message.sender_label.setText("系统")

            self.logger.error(f"验证连接时出错: {str(e)}")

    def validatePublicModel(self):
        """验证公有模型连接"""
        config = self.currentModelConfig
        host = config["host"]
        port = config["port"]
        model_name = config["model_name"] or "deepseek-coder"

        try:

            results = validate_ollama_connection(host, port)


            if results["tcp_connection"]:

                success_message = self.chatHistory.addAIMessage("✅ TCP连接成功")
                success_message.sender_label.setText("系统")
            else:

                error_message = self.chatHistory.addAIMessage("❌ TCP连接失败")
                error_message.sender_label.setText("系统")

            if results["api_connection"]:

                success_message = self.chatHistory.addAIMessage("✅ API连接成功")
                success_message.sender_label.setText("系统")

                if results["available_models"]:

                    models_message = self.chatHistory.addAIMessage(
                        f"📋 可用模型 ({len(results['available_models'])}):\n"
                        + "\n".join(
                            [
                                f"{i+1}. {model}"
                                for i, model in enumerate(results["available_models"])
                            ]
                        )
                    )
                    models_message.sender_label.setText("系统")

                    if model_name in results["available_models"]:

                        model_message = self.chatHistory.addAIMessage(
                            f"✅ 当前选择的模型 '{model_name}' 可用"
                        )
                        model_message.sender_label.setText("系统")
                    else:

                        warning_message = self.chatHistory.addAIMessage(
                            f"⚠️ 当前选择的模型 '{model_name}' 在服务器上不可用"
                        )
                        warning_message.sender_label.setText("系统")
            else:

                error_message = self.chatHistory.addAIMessage("❌ API连接失败")
                error_message.sender_label.setText("系统")


            if results["errors"]:
                error_message = self.chatHistory.addAIMessage(
                    f"❌ 错误: {results['errors'][0]}"
                )
                error_message.sender_label.setText("系统")

        except Exception as e:

            error_message = self.chatHistory.addAIMessage(f"❌ 验证失败: {str(e)}")
            error_message.sender_label.setText("系统")

    def validatePrivateModel(self):
        """验证私有模型连接"""
        config = self.currentModelConfig
        host = config["host"]
        api_key = config["api_key"]
        if not api_key:

            error_message = self.chatHistory.addAIMessage("❌ 缺少API密钥")
            error_message.sender_label.setText("系统")
            return

        try:
            import requests


            headers = {"Authorization": f"Bearer {api_key}"}


            url = host
            if not url.startswith("http"):
                url = f"http://{url}"


            response = requests.get(url, headers=headers, timeout=5)


            success_message = self.chatHistory.addAIMessage(
                f"✅ 连接成功，状态码: {response.status_code}"
            )
            success_message.sender_label.setText("系统")


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


                        models_message = self.chatHistory.addAIMessage(
                            f"📋 API返回的模型列表 (前5个):\n"
                            + "\n".join(
                                [
                                    f"{i+1}. {model_id}"
                                    for i, model_id in enumerate(models[:5])
                                ]
                            )
                        )
                        models_message.sender_label.setText("系统")
            except:

                pass

        except Exception as e:

            error_message = self.chatHistory.addAIMessage(f"❌ 验证失败: {str(e)}")
            error_message.sender_label.setText("系统")

    def sendMessage(self):
        """发送消息处理"""

        if not self.client:
            if not self.connectToModel():
                return


        question = self.inputField.text().strip()
        if not question:
            return


        self.chatHistory.addUserMessage(question)


        self.inputField.clear()


        self.sendButton.setEnabled(False)

        try:

            start_time = time.time()


            available_memory, memory_usage = check_memory_usage()
            if available_memory is not None:
                memory_requirement = estimate_model_memory_requirement(
                    self.currentModelConfig.get("model_name", "")
                )


                if available_memory < memory_requirement:

                    warning_message = self.chatHistory.addAIMessage(
                        f"⚠️ 警告: 系统可用内存不足 ({available_memory:.2f} GB)，"
                        f"模型可能需要至少 {memory_requirement} GB。\n"
                        f"请关闭其他应用程序释放内存，或使用更小的模型。"
                    )
                    warning_message.sender_label.setText("系统")

            config = self.currentModelConfig
            model_type = config["type"]
            model_name = config["model_name"]


            temperature = config.get("temperature", 0.7)
            max_tokens = config.get("max_tokens", 1000)
            system_prompt = config.get("system_prompt", "")
            response_timeout = config.get("response_timeout", 60)


            use_rag = config.get("use_rag", False)
            manual_path = config.get("manual_path", "")


            is_rag_available, rag_error = is_sentence_transformer_available()


            if use_rag and not is_rag_available:

                warning_message = self.chatHistory.addAIMessage(
                    f"⚠️ RAG功能不可用，将使用普通模式回答。错误: {rag_error}"
                )
                warning_message.sender_label.setText("系统")
                use_rag = False


            if use_rag and manual_path and os.path.exists(manual_path):

                self.statusLabel.setText("RAG处理中...")


                processing_message = self.chatHistory.addAIMessage(
                    "正在处理文档并准备RAG上下文，请稍候..."
                )
                processing_message.sender_label.setText("系统")


                self.progress_dialog = QProgressDialog(
                    "处理中...", "取消", 0, 100, self
                )
                self.progress_dialog.setWindowTitle("RAG处理进度")
                self.progress_dialog.setAutoClose(True)
                self.progress_dialog.setMinimumDuration(500)  # 500ms后才显示


                self.rag_worker = RagWorker(manual_path, question, system_prompt)


                self.rag_worker.progress_signal.connect(self.updateRagProgress)
                self.rag_worker.finished_signal.connect(self.onRagFinished)
                self.rag_worker.error_signal.connect(self.onRagError)


                self.progress_dialog.canceled.connect(self.cancelRagProcessing)


                self.rag_worker.start()

            else:

                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})

                messages.append({"role": "user", "content": question})


                self.startResponseGeneration(messages)

        except Exception as e:
            error_msg = str(e)


            error_message = self.chatHistory.addAIMessage(
                f"处理请求时出错: {error_msg}"
            )
            error_message.sender_label.setText("系统")

            self.logger.error(f"处理请求失败: {error_msg}")
            self.sendButton.setEnabled(True)
            self.statusLabel.setText("处理出错")

    def updateRagProgress(self, progress, message):
        """更新RAG处理进度"""
        if self.progress_dialog:
            self.progress_dialog.setValue(progress)
            self.progress_dialog.setLabelText(message)

    def cancelRagProcessing(self):
        """取消RAG处理"""
        if self.rag_worker and self.rag_worker.isRunning():
            self.rag_worker.requestInterruption()
            self.rag_worker.wait(1000)  # 等待最多1秒


            cancel_message = self.chatHistory.addAIMessage("RAG处理已取消")
            cancel_message.sender_label.setText("系统")

            self.statusLabel.setText("已取消")
            self.sendButton.setEnabled(True)

    def onRagError(self, error_message):
        """处理RAG错误"""

        error_msg = self.chatHistory.addAIMessage(f"RAG处理出错: {error_message}")
        error_msg.sender_label.setText("系统")


        self.sendButton.setEnabled(True)
        self.statusLabel.setText("就绪")

    def onRagFinished(self, messages):
        """RAG处理完成，开始生成响应"""

        done_message = self.chatHistory.addAIMessage("RAG处理完成，正在生成回答...")
        done_message.sender_label.setText("系统")


        self.startResponseGeneration(messages)

    def startResponseGeneration(self, messages):
        """开始生成AI响应"""

        ai_message = self.chatHistory.addAIMessage("")
        ai_message.setGenerating(True)


        self.response_worker = ResponseGenerationWorker(
            self.client, self.currentModelConfig, messages
        )


        self.response_worker.chunk_signal.connect(self.onResponseChunk)
        self.response_worker.finished_signal.connect(self.onResponseFinished)
        self.response_worker.error_signal.connect(self.onResponseError)


        ai_message.stopGeneration.connect(self.cancelResponseGeneration)


        self.statusLabel.setText("正在生成回答...")


        self.response_worker.start()

    def cancelResponseGeneration(self):
        """取消响应生成"""
        if self.response_worker and self.response_worker.isRunning():
            self.response_worker.requestInterruption()
            self.response_worker.wait(1000)  # 等待最多1秒


            self.chatHistory.appendToLastAIMessage("\n\n[用户取消了响应生成]")


            self.chatHistory.setLastAIMessageGenerating(False)
            self.sendButton.setEnabled(True)
            self.statusLabel.setText("已取消")

    def onResponseChunk(self, chunk):
        """处理响应块"""

        self.chatHistory.appendToLastAIMessage(chunk)

    def onResponseError(self, error_message):
        """处理响应生成错误"""

        self.chatHistory.appendToLastAIMessage(f"\n\n生成失败: {error_message}")
        self.chatHistory.setLastAIMessageGenerating(False)


        self.sendButton.setEnabled(True)
        self.statusLabel.setText("生成失败")

    def onResponseFinished(self, full_response):
        """响应生成完成"""

        self.chatHistory.setLastAIMessageGenerating(False)


        if self.currentModelConfig.get("enable_analytics", False):
            end_time = time.time()
            response_time = round((end_time - time.time()) * 1000)


            analytics_message = self.chatHistory.addAIMessage(
                f"响应时间: {response_time}ms, " f"输出长度: {len(full_response)} 字符"
            )
            analytics_message.sender_label.setText("分析")
            analytics_message.setStyleSheet(
                """
                background-color: #F9F9F9;
                border: 1px solid #EEEEEE;
                border-radius: 8px;
                margin: 2px 5px 2px 20px;
                font-size: 9px;
                color: gray;
            """
            )


            if self.currentModelConfig.get("log_queries", False):
                question = self.inputField.text().strip()
                log_query(
                    self.currentModelConfig, question, full_response, response_time
                )


        self.sendButton.setEnabled(True)
        self.statusLabel.setText("就绪")
