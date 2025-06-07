from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QSizePolicy,
    QMenu,
    QApplication,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon, QAction, QColor, QPalette, QTextOption
import time


class MessageWidget(QFrame):
    """基础消息组件

    作为用户消息和AI消息的基类，提供共享的功能如复制内容、时间戳显示等
    使用QFrame作为基类，可以设置边框和背景样式
    """

    def __init__(self, text="", sender="", timestamp=None, parent=None):
        """
        初始化消息组件

        参数:
            text (str): 消息文本内容
            sender (str): 发送者名称（"用户"或"AI"）
            timestamp (float): 时间戳，默认为当前时间
            parent (QWidget): 父组件
        """
        super().__init__(parent)
        self.sender = sender  # 发送者名称
        self.text = text  # 消息文本内容
        self.timestamp = timestamp or time.time()  # 消息时间戳


        self.setFrameShape(QFrame.StyledPanel)  # 带面板效果的边框
        self.setFrameShadow(QFrame.Raised)  # 轻微凸起的阴影效果
        self.setLineWidth(1)  # 边框宽度
        self.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Minimum
        )  # 水平方向扩展，垂直方向最小


        self._initUI()

    def _initUI(self):
        """初始化界面元素

        创建消息的布局结构，包括：
        1. 顶部区域 - 发送者名称和时间戳
        2. 中间区域 - 消息内容
        3. 底部区域 - 操作按钮（如复制按钮）
        """

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)  # 内边距，使内容不会贴边
        layout.setSpacing(4)  # 元素间距


        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 4)


        self.sender_label = QLabel(self.sender)
        self.sender_label.setStyleSheet("font-weight: bold;")  # 加粗显示发送者


        time_str = time.strftime("%H:%M:%S", time.localtime(self.timestamp))
        self.time_label = QLabel(time_str)
        self.time_label.setStyleSheet(
            "color: gray; font-size: 9px;"
        )  # 灰色小字显示时间
        self.time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)  # 右对齐

        header_layout.addWidget(self.sender_label)
        header_layout.addStretch()  # 添加弹性空间，使发送者和时间分开排列
        header_layout.addWidget(self.time_label)


        self.content_label = QLabel(self.text)
        self.content_label.setWordWrap(True)  # 允许文本自动换行
        self.content_label.setTextFormat(Qt.RichText)  # 支持富文本（HTML）
        self.content_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard  # 允许选择文本
        )


        actions_layout = QHBoxLayout()
        actions_layout.setContentsMargins(0, 4, 0, 0)


        self.copy_btn = QPushButton("复制")
        self.copy_btn.setIcon(QIcon.fromTheme("edit-copy"))  # 设置复制图标
        self.copy_btn.setFixedSize(QSize(80, 40))  # 调大按钮大小
        self.copy_btn.clicked.connect(self.copyContent)  # 连接点击事件
        self.copy_btn.setStyleSheet("font-size: 13px; font-weight: bold;")  # 设置更大更明显的字体

        actions_layout.addStretch()  # 添加弹性空间，使按钮靠右
        actions_layout.addWidget(self.copy_btn)


        layout.addLayout(header_layout)
        layout.addWidget(self.content_label)
        layout.addLayout(actions_layout)

    def copyContent(self):
        """复制消息内容到剪贴板

        当用户点击复制按钮时调用此方法
        """

        plain_text = self.content_label.text()



        clipboard = QApplication.clipboard()
        clipboard.setText(plain_text)



class UserMessageWidget(MessageWidget):
    """用户消息组件

    继承自MessageWidget，代表用户发送的消息
    使用蓝色背景和偏右侧的显示方式
    """

    def __init__(self, text="", timestamp=None, parent=None):
        """
        初始化用户消息组件

        参数:
            text (str): 消息内容
            timestamp (float): 时间戳
            parent (QWidget): 父组件
        """
        super().__init__(text, "用户", timestamp, parent)
        self.setObjectName("userMessage")  # 设置对象名，用于CSS样式选择器


        self.setStyleSheet(
            """

                background-color: #E6F7FF;  /* 浅蓝色背景 */
                border: 1px solid #91D5FF;  /* 蓝色边框 */
                border-radius: 8px;         /* 圆角边框 */
                margin: 5px 20px 5px 5px;   /* 右侧边距大，表示用户消息偏右 */
            }
        """
        )


class AIMessageWidget(MessageWidget):
    """AI消息组件

    继承自MessageWidget，代表AI回复的消息
    使用灰色背景和偏左侧的显示方式
    添加了停止生成按钮，用于中断长回答的生成
    """


    stopGeneration = Signal()  # 停止生成信号，会连接到主界面的取消方法

    def __init__(self, text="", timestamp=None, parent=None):
        """
        初始化AI消息组件

        参数:
            text (str): 消息内容
            timestamp (float): 时间戳
            parent (QWidget): 父组件
        """
        super().__init__(text, "AI", timestamp, parent)
        self.setObjectName("aiMessage")  # 设置对象名，用于CSS样式
        self.is_generating = False  # 标记是否正在生成回答


        self.setStyleSheet(
            """

                background-color: #F0F0F0;  /* 浅灰色背景 */
                border: 1px solid #D9D9D9;  /* 灰色边框 */
                border-radius: 8px;         /* 圆角边框 */
                margin: 5px 5px 5px 20px;   /* 左侧边距大，表示AI消息偏左 */
            }
        """
        )

        self.stop_btn = QPushButton("停止")
        self.stop_btn.setIcon(QIcon.fromTheme("process-stop"))  # 停止图标
        self.stop_btn.setFixedSize(QSize(80, 40))  # 调大按钮大小
        self.stop_btn.setStyleSheet("font-size: 13px; font-weight: bold; color: #d32f2f;")  # 设置更大更明显的字体，红色突出显示
        self.stop_btn.clicked.connect(self.stopGeneration)  # 连接停止信号
        self.stop_btn.setVisible(False)  # 初始隐藏，只在生成回答时显示

        actions_layout = self.layout().itemAt(2).layout()
        actions_layout.insertWidget(1, self.stop_btn)  # 插入到复制按钮之前

    def setGenerating(self, is_generating):
        """设置是否正在生成状态

        参数:
            is_generating (bool): 是否正在生成回答

        根据状态显示或隐藏停止按钮
        """
        self.is_generating = is_generating
        self.stop_btn.setVisible(is_generating)  # 只在生成时显示停止按钮

    def appendText(self, text):
        """追加文本内容

        用于流式生成回答时，逐步追加生成的内容

        参数:
            text (str): 要追加的文本
        """
        current_text = self.content_label.text()
        self.content_label.setText(current_text + text)  # 追加新内容


class ChatHistoryWidget(QWidget):
    """聊天历史记录组件

    管理所有消息组件，维护消息列表和布局
    提供添加、删除和更新消息的方法
    """

    def __init__(self, parent=None):
        """
        初始化聊天历史组件

        参数:
            parent (QWidget): 父组件
        """
        super().__init__(parent)
        self.messages = []  # 存储所有消息组件的列表
        self.current_ai_message = None  # 当前活动的AI消息组件，用于追加内容


        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)  # 设置边距
        self.layout.setSpacing(10)  # 设置消息间距
        self.layout.setAlignment(Qt.AlignTop)  # 消息从顶部开始排列



        self.layout.addStretch()

    def addUserMessage(self, text):
        """添加用户消息

        参数:
            text (str): 消息内容

        返回:
            UserMessageWidget: 创建的用户消息组件
        """
        message = UserMessageWidget(text)

        self.layout.insertWidget(self.layout.count() - 1, message)
        self.messages.append(message)
        return message

    def addAIMessage(self, text=""):
        """添加AI消息并返回

        参数:
            text (str): 初始消息内容，可为空

        返回:
            AIMessageWidget: 创建的AI消息组件
        """
        message = AIMessageWidget(text)

        self.layout.insertWidget(self.layout.count() - 1, message)
        self.messages.append(message)
        self.current_ai_message = message  # 记录当前活动的AI消息
        return message

    def appendToLastAIMessage(self, text):
        """向最后一条AI消息追加内容

        用于流式生成回答时，逐步更新AI消息内容

        参数:
            text (str): 要追加的文本
        """
        if self.current_ai_message:
            self.current_ai_message.appendText(text)

    def setLastAIMessageGenerating(self, is_generating):
        """设置最后一条AI消息的生成状态

        用于控制停止按钮的显示/隐藏

        参数:
            is_generating (bool): 是否正在生成
        """
        if self.current_ai_message:
            self.current_ai_message.setGenerating(is_generating)

    def clear(self):
        """清空所有消息

        移除并销毁所有消息组件
        """
        for message in self.messages:
            self.layout.removeWidget(message)
            message.deleteLater()  # 删除组件，避免内存泄漏

        self.messages.clear()
        self.current_ai_message = None
