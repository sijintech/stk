"""
CLI管理器，负责加载CLI命令、管理文档和参数信息
"""

from PySide6 import QtCore
import os
import sys
import importlib.util
import inspect
import click
import markdown


class CLIManager(QtCore.QObject):
    """CLI管理器，负责加载CLI命令、管理文档和参数信息"""

    # 定义信号
    docLoaded = QtCore.Signal(str)  # 当文档加载完成时发出，参数为HTML格式的文档内容
    paramsLoaded = QtCore.Signal(list)  # 当参数加载完成时发出，参数为参数列表

    def __init__(self, parent=None):
        """初始化CLI管理器"""
        super().__init__(parent)
        # 获取toolkits目录的路径，用于加载命令和文档
        current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        self.toolkits_path = os.path.join(current_dir, '../toolkits')

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
        try:
            for group_name in os.listdir(self.toolkits_path):

                group_path = os.path.join(self.toolkits_path, group_name)
                print(f'{group_name}:{group_path}')
                cli_path = os.path.join(group_path, 'cli.py')

                # 检查是否是有效的命令组：必须是目录且包含cli.py文件
                if os.path.isdir(group_path) and os.path.exists(cli_path):
                    try:
                        # 动态导入CLI模块
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
                                    'commands': {}  # 子命令字典
                                }

                                # 获取命令组中的所有子命令并保存到字典中
                                for cmd_name, cmd_obj in group_obj.commands.items():
                                    self.command_groups[group_name]['commands'][cmd_name] = cmd_obj
                    except Exception as e:
                        # 出错时打印错误信息，继续处理其他命令组
                        print(f"加载命令组 {group_name} 失败: {e}")
        except Exception as e:
            print(f"加载命令组失败: {e}")
            # 添加测试命令组，便于开发阶段测试
            self._add_test_command_group()

    def _add_test_command_group(self):
        """添加测试命令组，方便在没有真实命令时测试界面"""

        @click.group(name="test")
        def test_group():
            """测试命令组"""
            pass

        @test_group.command()
        @click.option("--name", type=str, required=True, help="用户名")
        @click.option("--age", type=int, default=18, help="年龄")
        @click.option("--is-student", is_flag=True, help="是否为学生")
        def hello(name, age, is_student):
            """打印问候语"""
            student_str = "学生" if is_student else "非学生"
            return f"你好，{name}！你的年龄是{age}，你是{student_str}。"

        @test_group.command()
        @click.option("--file", type=str, required=True, help="文件路径")
        @click.option("--lines", type=int, default=10, help="显示的行数")
        def read_file(file, lines):
            """读取文件内容"""
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    content = f.readlines()[:lines]
                return "".join(content)
            except Exception as e:
                return f"读取文件失败: {str(e)}"

        # 添加到命令组字典
        self.command_groups["test"] = {
            'object': test_group,
            'commands': {
                'hello': hello,
                'read_file': read_file
            }
        }

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
        print(f"尝试加载文档: {doc_path}")
        print(f"文件是否存在: {os.path.exists(doc_path)}")

        # 读取文档文件并转换为HTML
        doc_html = ""
        if os.path.exists(doc_path):
            try:
                # 首先尝试使用UTF-8编码打开
                try:
                    with open(doc_path, 'r', encoding='utf-8') as f:
                        doc_content = f.read()
                except UnicodeDecodeError:
                    # 如果UTF-8失败，尝试使用GBK编码
                    print("UTF-8编码失败，尝试GBK编码")
                    with open(doc_path, 'r', encoding='gbk') as f:
                        doc_content = f.read()

                print(f"文档内容长度: {len(doc_content)}")
                print(f"文档内容前100字符: {doc_content[:100]}")

                # 将Markdown转换为HTML
                try:
                    doc_html = markdown.markdown(doc_content, extensions=['tables', 'fenced_code'])
                    print(f"HTML内容长度: {len(doc_html)}")
                    print(f"HTML内容前100字符: {doc_html[:100]}")
                except Exception as md_error:
                    print(f"Markdown转换失败: {str(md_error)}")
                    doc_html = f"<pre>{doc_content}</pre>"
            except Exception as e:
                print(f"加载文档失败: {str(e)}")
                doc_html = f"<p>无法加载文档: {str(e)}</p>"
        else:
            # 如果文档文件不存在，尝试从命令对象获取文档
            cmd_obj = self.command_groups[group_name]['commands'].get(command_name)
            if cmd_obj and cmd_obj.__doc__:
                doc_html = f"<h1>{group_name} {command_name}</h1><p>{cmd_obj.__doc__}</p>"
            else:
                # 如果没有文档，生成默认文档
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
                        'name': param.name,  # 参数名称
                        'opts': [opt for opt in param.opts if opt.startswith('-')],  # 参数选项 (如 --name, -n)
                        'required': param.required,  # 是否必需
                        'default': param.default if not param.is_flag else False,  # 默认值
                        'help': param.help,  # 帮助文本
                        'type': self._get_param_type(param),  # 参数类型
                        'is_flag': param.is_flag,  # 是否为标志参数
                        'multiple': param.multiple  # 是否允许多个值
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
