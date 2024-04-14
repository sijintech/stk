from PySide6.QtWidgets import QWidget, QVBoxLayout, QFileSystemModel, QTreeView
from PySide6.QtCore import QModelIndex, Qt,Signal
from PySide6.QtCore import QFileInfo

class LeftSidebar(QWidget):
    openFilePath = Signal(str)  # 定义一个信号，用于发送打开文件请求
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        self.treeView = QTreeView()


        layout.addWidget(self.treeView)
        self.setLayout(layout)
        layout.setContentsMargins(0,0,0,0)
        self.setupFileSystemModel()

    def setupFileSystemModel(self):
        # 创建文件系统模型
        self.model = QFileSystemModel(self) 
        self.model.setRootPath("")
        self.treeView.setModel(self.model)
        self.treeView.setRootIndex(self.model.index(""))  # 设置根索引为当前路径
        # 只想显示name这一列，不想显示size,type,modified的信息
        self.treeView.setColumnHidden(1, True);
        self.treeView.setColumnHidden(2, True);
        self.treeView.setColumnHidden(3, True);
        # 连接双击信号到槽函数
        self.treeView.doubleClicked.connect(self.onDoubleClick)

    def onDoubleClick(self, index: QModelIndex):
        # 获取所选项的路径
        path = self.model.filePath(index)

        # 如果是文件，则读取文件内容
        if QFileInfo(path).isFile():
            try:
                with open(path, 'r', encoding='utf-8') as file:
                    content = file.read()
                    self.openFilePath.emit(path)
                    # 发送文件内容给InfoBar
                    self.parent.info_bar.showContent(content)
            except Exception as e:
                print("Error reading file:", e)
