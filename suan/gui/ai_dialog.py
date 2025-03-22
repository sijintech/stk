from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFormLayout
)
from PySide6.QtCore import Qt

class AIConnectionDialog(QDialog):
    def __init__(self, parent=None, host="127.0.0.1", port="11435", model="deepseek-r1:1.5b"):
        super().__init__(parent)
        self.setWindowTitle("AI对话连接设置")
        self.host = host
        self.port = port
        self.model = model
        self.initUI()
        
    def initUI(self):
        layout = QVBoxLayout()
        
        # 表单布局
        formLayout = QFormLayout()
        
        # Host输入
        self.hostInput = QLineEdit(self.host)
        formLayout.addRow("Host:", self.hostInput)
        
        # Port输入
        self.portInput = QLineEdit(self.port)
        formLayout.addRow("Port:", self.portInput)
        
        # 模型输入
        self.modelInput = QLineEdit(self.model)
        formLayout.addRow("模型:", self.modelInput)
        
        layout.addLayout(formLayout)
        
        # 按钮布局
        buttonLayout = QHBoxLayout()
        self.cancelButton = QPushButton("取消")
        self.cancelButton.clicked.connect(self.reject)
        
        self.connectButton = QPushButton("连接")
        self.connectButton.clicked.connect(self.accept)
        self.connectButton.setDefault(True)
        
        buttonLayout.addWidget(self.cancelButton)
        buttonLayout.addWidget(self.connectButton)
        
        layout.addLayout(buttonLayout)
        
        self.setLayout(layout)
        self.resize(300, 150)
        
    def getConnectionParams(self):
        return {
            "host": self.hostInput.text(),
            "port": self.portInput.text(),
            "model": self.modelInput.text()
        } 