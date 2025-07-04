# STK CLI接入GUI实现方案

## 用户视角的功能效果

STK CLI的GUI集成将为用户提供以下体验：

### 功能概述
将所有命令行工具集成到图形界面中，让用户无需手动输入命令，通过点击和填写表单即可使用全部CLI功能。

### 用户界面组成
1. **命令选择按钮(CLI)**：位于主窗口第一行工具栏中，点击后显示命令组和具体命令的下拉菜单
2. **文档显示区域**：在用户选择命令后，在中心区域显示一个标签页，展示所选命令的详细说明文档
3. **参数表单**：在用户选择命令后，在主窗口右侧边栏显示，并根据所选命令动态生成表单控件
4. **终端窗口**：在底部信息栏的Console标签页中显示命令执行结果，模拟命令行终端体验

### 交互流程
1. 用户点击第一行工具栏中的"CLI"按钮，弹出命令组和命令的层级下拉菜单
2. 用户从下拉菜单中选择特定命令后：
   - 中心区域自动切换到CLI文档标签页（如果不存在则创建）
   - 右侧边栏显示与所选命令对应的参数表单
3. 用户在文档区域阅读命令说明和参数用途
4. 用户在右侧参数表单中填写必要参数，点击"执行"按钮
5. 系统根据选择的命令和参数自动生成命令行指令
6. 命令在底部终端窗口(Console标签页)中执行，用户可实时查看执行结果
7. 执行完成后，终端窗口保留执行历史，方便用户查看和分析

### 核心优势
1. **无缝集成**：CLI功能直接集成到主窗口工具栏，易于访问
2. **按需显示**：只有在用户选择命令后才显示相关界面，不占用额外空间
3. **智能参数表单**：根据参数类型提供不同的输入控件，如文件选择器、数值滑块等
4. **真实终端体验**：在集成的终端窗口中执行命令，保留熟悉的命令行体验
5. **执行历史记录**：终端窗口保留历史命令和输出，方便回顾和分析

## 实现步骤

### 1. 创建CLI命令按钮
创建一个CLI按钮组件(`cli_toolbar_button.py`)，添加到主窗口第一行工具栏：
- 显示命令组和命令的层级下拉菜单
- 当用户选择具体命令时发出信号

**实现代码示例：**

```python
# cli_toolbar_button.py
from PySide6 import QtWidgets, QtCore, QtGui  # 导入PySide6库的基本组件

class CLIToolbarButton(QtWidgets.QToolButton):
    """CLI工具栏按钮，显示命令组和命令的下拉菜单"""
    
    # 自定义信号：当用户选择命令时发出，传递命令组名称和命令名称
    commandSelected = QtCore.Signal(str, str)  
    
    def __init__(self, cli_manager, parent=None):
        """初始化按钮并设置基本属性"""
        super().__init__(parent)  # 调用父类初始化方法
        # 保存CLI管理器的引用
        self.cli_manager = cli_manager
        
        # 设置按钮文本和提示信息
        self.setText("CLI")  # 按钮显示文本为"CLI"
        self.setToolTip("命令行工具")  # 鼠标悬停时的提示文本
        # 设置点击按钮立即显示弹出菜单，而不是先按下再弹出
        self.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        
        # 创建下拉菜单对象
        self.menu = QtWidgets.QMenu(self)
        # 将菜单设置为按钮的弹出菜单
        self.setMenu(self.menu)
        
        # 加载所有可用命令到菜单中
        self.load_commands()
        
    def load_commands(self):
        """加载所有可用的命令组和命令到菜单中"""
        # 从CLI管理器获取所有命令组
        group_names = self.cli_manager.get_command_groups()
        
        # 遍历所有命令组
        for group_name in group_names:
            try:
                # 为该命令组创建子菜单
                group_menu = QtWidgets.QMenu(group_name, self.menu)
                # 将子菜单添加到主菜单
                self.menu.addMenu(group_menu)
                
                # 从CLI管理器获取该命令组下的所有命令
                cmd_names = self.cli_manager.get_commands(group_name)
                
                # 遍历所有命令，添加到子菜单
                for cmd_name in cmd_names:
                    # 创建菜单项，显示命令名称
                    action = group_menu.addAction(cmd_name)
                    # 菜单动作的 triggered 信号被激活
                    # 对应的 lambda 函数被调用，接收 checked 参数（表示动作是否被选中）
                    # lambda 函数使用它捕获的 g 和 c 值（对应特定的命令组和命令名）
                    # lambda 函数发射 commandSelected 自定义信号，将这两个值传递出去
                    action.triggered.connect(
                        # 使用lambda绑定固定的参数值，注意使用默认参数避免闭包问题
                        # 闭包问题：如果不使用默认参数，所有lambda都会引用for循环结束时的值
                        lambda checked, g=group_name, c=cmd_name: 
                        self.commandSelected.emit(g, c)
                    )
            except Exception as e:
                # 出错时打印错误信息，继续处理其他命令组
                print(f"加载命令组 {group_name} 失败: {e}")
```

### 2. 创建CLI管理器
创建一个CLI管理器(`cli_manager.py`)，负责管理CLI功能的核心逻辑：
- 加载命令和文档
- 管理参数表单和文档显示
- 执行命令并处理结果

**实现代码示例：**

```python
# cli_manager.py
from PySide6 import QtCore, QtWidgets  # 导入PySide6库核心组件
import os  # 操作系统模块，用于文件路径操作
import sys  # 系统模块，用于修改Python模块搜索路径
import importlib  # 动态导入模块
import inspect  # 用于检查对象属性和方法
import click  # 命令行接口创建库
import markdown  # Markdown转HTML库

class CLIManager(QtCore.QObject):
    """CLI管理器，负责加载CLI命令、管理文档和参数信息"""
    
    # 定义信号
    docLoaded = QtCore.Signal(str)      # 当文档加载完成时发出，参数为HTML格式的文档内容
    paramsLoaded = QtCore.Signal(list)  # 当参数加载完成时发出，参数为参数列表
    
    def __init__(self, parent=None):
        """初始化CLI管理器"""
        super().__init__(parent)  # 调用父类初始化方法
        # 获取toolkits目录的路径，用于加载命令和文档
        current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        self.toolkits_path = os.path.join(current_dir, '../../../../toolkits')
        
        # 当前选中的命令组和命令，初始为None
        self.current_group = None
        self.current_command = None
        
        # 命令组字典，存储所有加载的命令组和命令
        # 格式: {'组名': {'object': 组对象, 'commands': {'命令名': 命令对象}}}
        self.command_groups = {}
        
        # 初始化时加载所有命令组
        self.load_command_groups()
        
    def load_command_groups(self):
        """加载所有命令组和子命令到内存中"""
        # 确保sys.path中包含必要的路径，以便动态导入模块
        sys.path.insert(0, os.path.dirname(self.toolkits_path))
        
        # 遍历toolkits目录下的所有文件夹
        for group_name in os.listdir(self.toolkits_path):
            group_path = os.path.join(self.toolkits_path, group_name)
            cli_path = os.path.join(group_path, 'cli.py')
            
            # 检查是否是有效的命令组：必须是目录且包含cli.py文件
            if os.path.isdir(group_path) and os.path.exists(cli_path):
                try:
                    # 动态导入CLI模块 动态导入允许系统仅在需要时加载模块，而不是在程序启动时就加载所有可能的命令模块。这提高了启动性能，特别是当 CLI 工具数量众多时。动态导入允许系统在运行时发现和加载位于 toolkits 目录下的各种命令组，而无需事先知道哪些插件可用。
                    
                    spec = importlib.util.spec_from_file_location(f"{group_name}.cli", cli_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    # 获取命令组对象 (click.Group)
                    if hasattr(module, group_name):
                        group_obj = getattr(module, group_name)
                        if isinstance(group_obj, click.Group):
                            # 将命令组添加到字典
                            self.command_groups[group_name] = {
                                'object': group_obj,  # 命令组对象
                                'commands': {}        # 子命令字典
                            }
                            
                            # 获取命令组中的所有子命令并保存到字典中
                            for cmd_name, cmd_obj in group_obj.commands.items():
                                self.command_groups[group_name]['commands'][cmd_name] = cmd_obj
                                
                except Exception as e:
                    # 出错时打印错误信息，继续处理其他命令组
                    print(f"加载命令组 {group_name} 失败: {e}")
                    
    def get_command_groups(self):
        """获取所有命令组名称，返回列表"""
        # 返回命令组字典的所有键（即命令组名称）
        return list(self.command_groups.keys())
    
    def get_commands(self, group_name):
        """获取指定命令组下的所有子命令名称，返回列表"""
        # 先检查指定的命令组是否存在
        if group_name in self.command_groups:
            # 返回该命令组下所有命令的名称列表
            return list(self.command_groups[group_name]['commands'].keys())
        # 如果命令组不存在，返回空列表
        return []
        
    def load_command_doc_and_params(self, group_name, command_name):
        """加载命令的文档并转换为HTML格式"""
        # 更新当前选中的命令组和命令
        self.current_group = group_name
        self.current_command = command_name
        
        # 尝试从文档文件中加载文档
        # 文档路径格式: toolkits/{group_name}/docs/{command_name}.md
        doc_path = os.path.join(self.toolkits_path, group_name, 'docs', f"{command_name}.md")
        
        # 读取文档文件并转换为HTML
        doc_html = ""
        if os.path.exists(doc_path):
            try:
                with open(doc_path, 'r', encoding='utf-8') as f:
                    doc_content = f.read()
                # 将Markdown转换为HTML
                doc_html = markdown.markdown(doc_content)
            except Exception as e:
                doc_html = f"<p>无法加载文档: {str(e)}</p>"
        else:
            # 如果文档文件不存在，生成默认文档
            doc_html = f"<h1>{group_name} {command_name}</h1><p>没有找到此命令的文档。</p>"
            
        # 发射文档加载完成信号
        self.docLoaded.emit(doc_html)
        
        params = []  # 参数列表
        cmd_obj = self.command_groups[group_name]['commands'].get(command_name)
        
        if cmd_obj:
            # 遍历命令对象的所有参数
            for param in cmd_obj.params:
                # 只处理选项类型的参数，不处理参数类型
                if isinstance(param, click.Option):
                    # 提取参数信息
                    param_info = {
                        'name': param.name,    # 参数名称
                        'opts': [opt for opt in param.opts if opt.startswith('-')],# 参数选项 (如 --name, -n)
                        'required': param.required,  # 是否必需
                        'default': param.default if not param.is_flag else False,  # 默认值
                        'help': param.help,  # 帮助文本
                        'type': self._get_param_type(param),  # 参数类型
                        'is_flag': param.is_flag,  # 是否为标志参数
                        'multiple': param.multiple      # 是否允许多个值
                    }
                    params.append(param_info)
                    
        # 发射参数加载完成的信号，传递参数列表
        self.paramsLoaded.emit(params)
        
    def _get_param_type(self, param):
        """获取参数类型，以便创建适当的表单控件"""
        # 如果是标志参数，类型为flag
        if param.is_flag:
            return 'flag'
        # 如果有类型信息
        elif param.type:
            # 如果是选择类型，返回选择项列表
            if isinstance(param.type, click.types.Choice):
                return {
                    'name': 'choice',
                    'choices': param.type.choices
                }
            else:
                # 否则返回类型名称 (如 'string', 'int', 'float')
                return param.type.name
        # 默认为文本类型
        return 'text'
        
    def execute_command(self, group_name, command_name, params):
        """
        准备命令执行的各项参数，验证命令是否有效
        
        返回:
            - 成功时: (True, {'command_obj': cmd_obj, 'args': args})
            - 失败时: (False, 错误信息)
        
        注意: 实际命令执行将在终端组件中进行，此方法仅验证命令有效性并准备参数
        """
        # 获取命令对象
        cmd_obj = self.command_groups[group_name]['commands'].get(command_name)
        if not cmd_obj:
            return False, "命令不存在"
        
        # 构建命令行参数列表
        args = []
        for param_name, param_value in params.items():
            # 如果参数有值
            if param_value is not None and param_value != "":
                if isinstance(param_value, bool) and param_value:
                    # 布尔型参数为True时，只添加选项名
                    args.append(f"--{param_name}")
                else:
                    # 其他类型参数添加选项名和值
                    args.append(f"--{param_name}")
                    args.append(str(param_value))
        
        try:
            # 验证命令和参数是否有效，但不实际执行
            # 返回命令对象和参数，供终端组件使用
            return True, {"command_obj": cmd_obj, "args": args}
        except Exception as e:
            return False, str(e)  # 返回验证失败和错误信息
```

### 3. 创建CLI文档显示组件

- 文档显示区显示命令说明和参数用途
- 按需添加到中心区域的标签管理器中

**实现代码示例：**

```python

from PySide6 import QtWidgets, QtCore, QtGui
from .cli_doc_viewer import CLIDocViewer

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
        styled_html = f"""
        <html>
        <head>
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
        super().setHtml(styled_html)
```

### 4. 创建CLI参数表单组件
创建一个参数表单组件(`cli_param_form.py`)，用于显示和收集命令参数：
- 设计为可添加到右侧边栏的小部件
- 根据命令参数动态生成表单控件
- 默认隐藏，仅在用户选择命令后显示

**实现代码示例：**

```python
# cli_param_form.py
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
        self.title_label = QtWidgets.QLabel("cli命令")
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
            # if param['help']:
            #     label.setToolTip(param['help'])
            
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
        elif isinstance(param['type'], dict) and param['type']['name'] == 'choice':
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
```

### 5. 创建CLI集成器
创建一个CLI集成器(`cli_integrator.py`)，负责将CLI功能集成到主窗口：
- 添加CLI按钮到第一行工具栏
- 按需创建和显示文档标签页和参数表单
- 将命令执行结果重定向到主窗口的终端窗口

**实现代码示例：**

1. 右侧边栏应采用 `QStackedLayout` 或类似机制，将变量表格（如 RightSidebar.table_widget）和 CLI 参数表单（param_form）作为不同的页面添加。
2. 平时显示变量表格，用户选择CLI命令时切换显示参数表单，参数表单关闭再切回变量表格。

**推荐实现方式：**

```python
# 在RightSidebar中
from PySide6.QtWidgets import QStackedLayout

class RightSidebar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        # 堆叠布局类似于一叠卡片或选项卡系统，但没有选项卡按钮。它将多个组件放在彼此之上，并提供编程方式来控制哪个组件当前可见。用户界面中同一时刻只会显示当前活动的组件，其他组件虽然存在但被隐藏。
        self.stacked_layout = QStackedLayout()
        self.table_widget = QTableWidget()
        self.param_form = None  # 由CLI集成器注入
        self.stacked_layout.addWidget(self.table_widget)
        self.setLayout(self.stacked_layout)
        # ...existing code...

     def set_param_form(self, param_form):
        """注入CLI参数表单，并加入堆叠布局"""
        self.param_form = param_form
        self.stacked_layout.addWidget(param_form)

    def show_variable_table(self):
        """显示变量表格"""
        self.stacked_layout.setCurrentWidget(self.table_widget)

    def show_param_form(self):
        """显示CLI参数表单"""
        if self.param_form:
            self.stacked_layout.setCurrentWidget(self.param_form)

```

```python
# cli_integrator.py
from PySide6 import QtCore, QtWidgets
from .cli_toolbar_button import CLIToolbarButton
from .cli_result_tab import CLITab
from .cli_param_form import CLIParamForm
from .cli_manager import CLIManager

class CLIIntegrator(QtCore.QObject):
    """CLI功能集成器，负责将CLI功能集成到主窗口"""
    
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        # 保存主窗口的引用
        self.main_window = main_window
        
        # 创建CLI管理器
        self.cli_manager = CLIManager(self)
        
        # 创建CLI工具栏按钮，传入CLI管理器
        self.cli_button = CLIToolbarButton(self.cli_manager)
        
        # 创建CLI参数表单
        self.param_form = CLIParamForm(self.cli_manager)
        
        # 集成各组件到主窗口
        self.integrate()
        
    def integrate(self):
        """将CLI功能集成到主窗口"""
        # 将CLI按钮添加到主窗口第一行工具栏
        # 创建一个动作并连接到显示CLI菜单的函数
        self.main_window.toolbar.toolbar1.addAction("CLI").triggered.connect(
            lambda: self.cli_button.menu.exec(
                # 将工具栏的局部坐标转换为整个屏幕的全局坐标系，确保菜单无论窗口在哪里都能显示在正确位置
                self.main_window.toolbar.toolbar1.mapToGlobal(
                    # 获取该动作的几何信息（位置和尺寸）
                    self.main_window.toolbar.toolbar1.actionGeometry(
                        #  获取工具栏中的最后一个动作（通常是刚添加的CLI按钮）
                        self.main_window.toolbar.toolbar1.actions()[-1]
                    ).bottomLeft() # 取这个几何区域的左下角坐标，这是菜单应该出现的理想位置
                )
            )
        )
        
        # 使用右侧边栏的set_param_form方法注入参数表单
        self.main_window.right_sidebar.set_param_form(self.param_form)
        
        # 连接信号
        # 当用户选择命令时，commandSelected 信号（被定义在CLI工具栏按钮中）被发射，携带所选命令的组名和命令名作为参数
        self.cli_button.commandSelected.connect(self.handle_command_selected)
        # 当用户提交参数时，执行命令
        self.param_form.paramReady.connect(self.execute_command)
        # 当用户取消参数表单时，切换回变量表格
        self.param_form.paramCancelled.connect(self.close_param_form)
    def handle_command_selected(self, group_name, command_name):
        """处理命令选择事件"""
        print(f"选择命令: {group_name} {command_name}")
        
        # 确保文档标签页先创建好
        doc_tab = self._get_or_create_doc_tab()
        print(f"文档标签页已创建/加载: {doc_tab}")
        
        # 设置参数表单标题
        self.param_form.title_label.setText(f"{group_name} {command_name}")
        
        # 切换右侧边栏显示参数表单
        self.main_window.right_sidebar.show_param_form()
        
        # 确保标签页已创建后再加载文档和参数（延迟加载）
        # 解决了之前文档无法显示的问题，因为它确保了在 docLoaded 信号发出之前，接收信号的对象（doc_viewer）已经连接到了信号槽。延迟加载的机制保证了信号和槽的正确连接顺序，从而确保 setHtml 函数能够被正确调用
        QtCore.QTimer.singleShot(100, lambda: self.cli_manager.load_command_doc_and_params(group_name, command_name))
        
    def _get_or_create_doc_tab(self):
        """获取或创建文档标签页"""
        # 检查是否已存在CLI文档标签页
        for i in range(self.main_window.center_widget.tabWidget.count()):
            tab_text = self.main_window.center_widget.tabWidget.tabText(i)
            if tab_text == "命令解析":
                # 如果存在，切换到该标签页
                self.main_window.center_widget.tabWidget.setCurrentIndex(i)
                return self.main_window.center_widget.tabWidget.widget(i)
        
        # 如果不存在，创建新标签页
        doc_tab = CLITab(self.cli_manager)
        tab_index = self.main_window.center_widget.tabWidget.addTab(
            doc_tab, "命令解析"
        )
        # 切换到新标签页
        self.main_window.center_widget.tabWidget.setCurrentIndex(tab_index)
        return doc_tab
    def close_param_form(self):
        """关闭参数表单，切换回变量表格"""
        # 切换回变量表格
        self.main_window.right_sidebar.show_variable_table()
    
    def execute_command(self, params):
        """执行命令，将结果显示在终端窗口"""
        # 检查是否已选择命令
        if not self.cli_manager.current_group or not self.cli_manager.current_command:
            return
            
        # 构建命令字符串
        cmd_str = f"{self.cli_manager.current_group} {self.cli_manager.current_command}"
        # 添加参数
        for name, value in params.items():
            if isinstance(value, bool) and value:
                # 布尔参数为True时，只添加选项名
                cmd_str += f" --{name}"
            elif value:
                # 对值进行适当的引用，确保特殊字符被正确处理
                quoted_value = f'"{value}"' if isinstance(value, str) and any(c in str(value) for c in ' <>|&;()$`\\"\'+') else value
                cmd_str += f" --{name} {quoted_value}"
        
        # 确保终端标签页可见
        self._ensure_console_visible()
        
        # 将命令发送到终端执行
        self._send_to_terminal(cmd_str, params)
        
        
    def _ensure_console_visible(self):
        """确保终端标签页可见"""
        # 切换到底部信息栏的Console标签页
        for i in range(self.main_window.info_bar.tabWidget.count()):
            if self.main_window.info_bar.tabWidget.tabText(i) == "Terminal":
                # 如果找到Console标签页，切换到它
                self.main_window.info_bar.tabWidget.setCurrentIndex(i)
                return
    
    def _send_to_terminal(self, cmd_str, params):
        """将命令发送到终端执行"""
        # 获取Console标签页的文本编辑器
        console = self.main_window.info_bar.consoleTab
        
        # 判断控制台是否支持终端功能
        if hasattr(console, "execute_stk_command"):
            # 如果是终端组件，使用其专用方法执行STK命令
            group_name = self.cli_manager.current_group
            command_name = self.cli_manager.current_command
            
            # 对输入参数值进行预处理，去除前后空格
            processed_params = {}
            for name, value in params.items():
                if isinstance(value, str):
                    # 去除前后空格
                    processed_value = value.strip()
                    processed_params[name] = processed_value
                else:
                    processed_params[name] = value
            
            # 构建完整的Python命令
            stk_cmd = f"python -m suan.cli.main {group_name} {command_name}"
            # 调用终端的执行命令方法，传递处理后的参数
            console.execute_stk_command(stk_cmd, processed_params)
        else:
            # 如果不支持，则使用基本方法：显示命令和执行结果
            # 显示执行的命令
            console.append(f"\n> {cmd_str}")
            
            # 使用CLI管理器执行命令并获取结果
            try:
                result = self.cli_manager.execute_command(
                    self.cli_manager.current_group,
                    self.cli_manager.current_command,
                    params
                )
                
                # 将执行结果显示在控制台
                if result[0]:  # 成功
                    console.append(str(result[1]) if result[1] else "命令执行成功")
                else:  # 失败
                    console.append(f"错误: {result[1]}")
            except Exception as e:
                # 显示执行错误
                console.append(f"执行错误: {str(e)}")
```

## 技术要点
- 使用PySide6进行GUI开发
- 动态加载命令和创建界面组件
- 按需显示文档和参数表单，提高界面利用率
- 利用信号和槽机制实现组件间通信
- 保持核心组件的解耦，便于后期维护和扩展


## 建议实现顺序
1. 首先实现CLI按钮和下拉菜单
2. 创建CLI管理器，实现命令加载和参数解析
3. 实现文档和结果显示组件
4. 实现参数表单组件
5. 创建CLI集成器，将所有组件整合起来
6. 最后在主窗口中集成CLI功能
