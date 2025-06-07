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


    docLoaded = QtCore.Signal(str)  # 当文档加载完成时发出，参数为HTML格式的文档内容
    paramsLoaded = QtCore.Signal(list)  # 当参数加载完成时发出，参数为参数列表

    def __init__(self, parent=None):
        """初始化CLI管理器"""
        super().__init__(parent)

        current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        self.toolkits_path = os.path.join(current_dir, '../toolkits')


        self.current_group = None
        self.current_command = None

        self.command_groups = {}

        self.load_command_groups()

    def load_command_groups(self):
        """加载所有命令组和子命令到内存中"""

        sys.path.insert(0, os.path.dirname(self.toolkits_path))

        try:
            for group_name in os.listdir(self.toolkits_path):

                group_path = os.path.join(self.toolkits_path, group_name)
                print(f'{group_name}:{group_path}')
                cli_path = os.path.join(group_path, 'cli.py')

                if os.path.isdir(group_path) and os.path.exists(cli_path):
                    try:

                        spec = importlib.util.spec_from_file_location(f"{group_name}.cli", cli_path)
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)

                        if hasattr(module, group_name):
                            group_obj = getattr(module, group_name)
                            if isinstance(group_obj, click.Group):

                                self.command_groups[group_name] = {
                                    'object': group_obj,  # 命令组对象
                                    'commands': {}  # 子命令字典
                                }

                                for cmd_name, cmd_obj in group_obj.commands.items():
                                    self.command_groups[group_name]['commands'][cmd_name] = cmd_obj
                    except Exception as e:

                        print(f"加载命令组 {group_name} 失败: {e}")
        except Exception as e:
            print(f"加载命令组失败: {e}")

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

        self.command_groups["test"] = {
            'object': test_group,
            'commands': {
                'hello': hello,
                'read_file': read_file
            }
        }

    def get_command_groups(self):
        """获取所有命令组名称，返回列表"""

        return list(self.command_groups.keys())

    def get_commands(self, group_name):
        """获取指定命令组下的所有子命令名称，返回列表"""

        if group_name in self.command_groups:
            return list(self.command_groups[group_name]['commands'].keys())

        return []

    def load_command_doc_and_params(self, group_name, command_name):
        """加载命令的文档并转换为HTML格式"""

        self.current_group = group_name
        self.current_command = command_name

        doc_path = os.path.join(self.toolkits_path, group_name, 'docs', f"{command_name}.md")
        print(f"尝试加载文档: {doc_path}")
        print(f"文件是否存在: {os.path.exists(doc_path)}")

        doc_html = ""
        if os.path.exists(doc_path):
            try:

                try:
                    with open(doc_path, 'r', encoding='utf-8') as f:
                        doc_content = f.read()
                except UnicodeDecodeError:

                    print("UTF-8编码失败，尝试GBK编码")
                    with open(doc_path, 'r', encoding='gbk') as f:
                        doc_content = f.read()

                print(f"文档内容长度: {len(doc_content)}")
                print(f"文档内容前100字符: {doc_content[:100]}")

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

            cmd_obj = self.command_groups[group_name]['commands'].get(command_name)
            if cmd_obj and cmd_obj.__doc__:
                doc_html = f"<h1>{group_name} {command_name}</h1><p>{cmd_obj.__doc__}</p>"
            else:

                doc_html = f"<h1>{group_name} {command_name}</h1><p>没有找到此命令的文档。</p>"

        self.docLoaded.emit(doc_html)

        params = []  # 参数列表
        cmd_obj = self.command_groups[group_name]['commands'].get(command_name)

        if cmd_obj:

            for param in cmd_obj.params:

                if isinstance(param, click.Option):
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

        self.paramsLoaded.emit(params)

    def _get_param_type(self, param):
        """获取参数类型，以便创建适当的表单控件"""

        if param.is_flag:
            return 'flag'

        elif param.type:

            if isinstance(param.type, click.types.Choice):
                return {
                    'name': 'choice',
                    'choices': param.type.choices
                }
            else:

                return param.type.name

        return 'text'

    def execute_command(self, group_name, command_name, params):
        """
        准备命令执行的各项参数，验证命令是否有效
        
        返回:
            - 成功时: (True, {'command_obj': cmd_obj, 'args': args})
            - 失败时: (False, 错误信息)
        
        注意: 实际命令执行将在终端组件中进行，此方法仅验证命令有效性并准备参数
        """

        cmd_obj = self.command_groups[group_name]['commands'].get(command_name)
        if not cmd_obj:
            return False, "命令不存在"

        args = []
        for param_name, param_value in params.items():

            if param_value is not None and param_value != "":
                if isinstance(param_value, bool) and param_value:

                    args.append(f"--{param_name}")
                else:

                    args.append(f"--{param_name}")
                    args.append(str(param_value))

        try:

            return True, {"command_obj": cmd_obj, "args": args}
        except Exception as e:
            return False, str(e)  # 返回验证失败和错误信息
