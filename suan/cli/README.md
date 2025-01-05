## 命令行项目结构

└── suan/
│ ├── cli/ # 主命令行程序目录
│ ├── main.py # 主 CLI 程序文件
│ ├── main.spec # 用于打包成可执行文件的配置文件
│
└── toolkits/ # 插件目录
├── sjob/
│ └── cli.py # 插件的 CLI 逻辑
├── sdata/
│ └── cli.py # 插件的 CLI 逻辑
└── ... # 更多插件

## 命令行编码要求

命令行程序使用click库编写，详情请查阅click使用文档(https://click-docs-zh-cn.readthedocs.io/zh/latest/)
为了方便该程序的运行，在toolkits目录下扩充和修改插件时，请遵守下面约束
1.该命令行程序只能识别注册在toolkits目录下的插件
2.插件的目录名即为该插件的命令行名称，在命名组时请保持一致，否则会出现注册失败的情况
3.只有插件的目录下包含cli.py文件，才会被识别注册该插件，并且打包该插件进入命令行程序中。插件有关命令行的代码请放在该文件中

## cli.py文件示例

```python
import click
#创建子命令组
@click.group()
def sjob():
    """与sjob插件相关的命令"""
    pass

#往指定子命令组里添加子命令
@sjob.command()
@click.option('--command', '-c', type=str, default='', help='每个目录中要执行的命令字符串')
@click.option('--folder_pattern', '-f', type=str, default='./*', help='目录通配符，默认为当前目录下的所有子目录')
def batch_all_command(command, folder_pattern):
    """遍历所有符合指定模式的目录，并在每个目录中执行指定的命令"""
    pass

@sjob.command()
@click.option('--name', '-n',type=str,default='job')
@click.option('--message', '-m', multiple=True)
def create():
    """创建一个新任务"""
    pass

```

## 如何打包

在当前目录下执行：
pyinstaller main.spec

## 如何使用命令行

如果不知道有什么命令可以使用--help"查询命令，如：
./suan.exe sjob --help
命令参数赋值可以用等号连接(如果值使用了通配符，请务必用等号连接)，也可以把值直接放在参数名后面，如：
./suan.exe sjob batchCommand -f='./*' -c 'dir'
    