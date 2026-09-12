try:
    from .chat_interface import AIChatTab
except ModuleNotFoundError as exc:
    if exc.name not in {'ollama', 'torch', 'sentence_transformers', 'PyPDF2'}:
        raise
    from PySide6.QtCore import Signal
    from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit

    class AIChatTab(QWidget):
        """Desktop remains usable when the optional AI extra is not installed."""
        modelConfigChanged = Signal()
        client = None

        def __init__(self, parent=None):
            super().__init__(parent)
            layout = QVBoxLayout(self)
            layout.addWidget(QLabel('AI 功能为可选组件。请安装 suan_toolkits[ai] 后重新启动。'))
            self.inputField = QLineEdit()
            self.inputField.setEnabled(False)
            layout.addWidget(self.inputField)

        def connectToModel(self):
            pass
