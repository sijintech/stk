import click
import importlib
import os
import sys


@click.group()
@click.version_option('1.0.0')  # 添加版本信息
# @click.group(invoke_without_command=True)
def cli():
    pass


# toolkits_path = '../../toolkits'  # 未打包时测试用


toolkits_path= 'toolkits' #打包时用
def load_plugins():
    """加载插件并返回每个插件的click.Group对象"""
    # 获取toolkits目录的绝对路径
    plugins_dir = os.path.join(os.path.dirname(__file__), toolkits_path)

    # 将toolkits目录添加到sys.path，确保可以动态导入插件
    sys.path.insert(0, plugins_dir)

    for plugin_name in os.listdir(plugins_dir):
        plugin_path = os.path.join(plugins_dir, plugin_name, 'cli.py')
        if os.path.exists(plugin_path):
            # 动态加载插件的cli.py文件
            plugin_module = importlib.import_module(f'{plugin_name}.cli')

            # 获取插件定义的click.Group对象，插件的命令组函数名即为插件名称
            if hasattr(plugin_module, plugin_name):
                plugin_group = getattr(plugin_module, plugin_name)
                cli.add_command(plugin_group)


if __name__ == '__main__':
    load_plugins()
    cli()
