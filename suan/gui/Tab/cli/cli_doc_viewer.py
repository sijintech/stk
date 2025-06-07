"""
CLI文档查看器，用于显示命令文档
"""

from PySide6 import QtWidgets, QtCore, QtGui


class CLIDocViewer(QtWidgets.QTextBrowser):
    """CLI文档查看器，用于显示命令文档"""

    def __init__(self, cli_manager, parent=None):
        super().__init__(parent)
        # 保存CLI管理器的引用
        self.cli_manager = cli_manager

        # 设置查看器属性
        self.setOpenLinks(False)  # 禁止直接打开链接，以便可以自定义链接处理
        self.setOpenExternalLinks(True)  # 允许打开外部链接

        # 设置样式
        self.setStyleSheet("""
            QTextBrowser {
                background-color: white;
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 8px;
            }
        """)

        # 连接链接点击信号
        self.anchorClicked.connect(self._handle_link_clicked)

    def _handle_link_clicked(self, url):
        """处理链接点击事件"""
        # 获取链接URL
        url_str = url.toString()

        # 如果是http或https链接，使用默认浏览器打开
        if url_str.startswith("http://") or url_str.startswith("https://"):
            QtGui.QDesktopServices.openUrl(url)

        # 如果是内部命令链接，可以添加特殊处理
        # 例如：cli://group_name/command_name
        elif url_str.startswith("cli://"):
            parts = url_str[6:].split("/")
            if len(parts) == 2:
                group_name, command_name = parts
                # 加载对应的命令文档和参数
                self.cli_manager.load_command_doc_and_params(group_name, command_name)

    def setHtml(self, html):
        """重写setHtml方法，添加自定义样式和处理"""
        # 添加基本样式
        print(f"接收到HTML内容: {len(html)} 字符")
        if not html or len(html) < 5:
            html = "<p>未接收到有效文档内容</p>"

        styled_html = f"""
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 10px; }}
                h1 {{ color: #333; border-bottom: 1px solid #ddd; padding-bottom: 10px; }}
                h2 {{ color: #444; margin-top: 20px; }}
                code {{ background-color: #f5f5f5; padding: 2px 4px; border-radius: 3px; }}
                pre {{ background-color: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                a {{ color: #0066cc; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
            </style>
        </head>
        <body>
            {html}
        </body>
        </html>
        """
        # 调用父类的setHtml方法
        print("设置HTML内容到文档查看器")
        super().setHtml(styled_html)
        print("HTML内容已设置")


class CLITab(QtWidgets.QWidget):
    """CLI文档标签页，只显示命令文档"""

    def __init__(self, cli_manager, parent=None):
        super().__init__(parent)
        # 保存CLI管理器的引用
        self.cli_manager = cli_manager

        # 创建垂直布局
        self.layout = QtWidgets.QVBoxLayout(self)

        # 创建文档查看器，用于显示命令文档
        self.doc_viewer = CLIDocViewer(self.cli_manager)
        self.layout.addWidget(self.doc_viewer)

        # 当 docLoaded 信号发出时，它会携带 HTML 格式的文档内容作为参数，这些参数会自动传递给 setHtml 方法，从而更新文档显示。
        self.cli_manager.docLoaded.connect(self.doc_viewer.setHtml)
