from setuptools import setup, find_packages
import os


def find_toolkits_with_cli():
    """返回 toolkits 下有 cli.py 文件的子目录列表"""
    toolkits_dir = os.path.join(os.path.dirname(__file__), '../../toolkits')
    toolkits_with_cli = []

    # 遍历 toolkits 目录中的每个子目录
    for plugin_name in os.listdir(toolkits_dir):
        plugin_path = os.path.join(toolkits_dir, plugin_name)
        # 只处理目录
        if os.path.isdir(plugin_path):
            cli_path = os.path.join(plugin_path, 'cli.py')
            if os.path.exists(cli_path):
                toolkits_with_cli.append(plugin_name)

    return toolkits_with_cli


# 找到有 cli.py 文件的插件目录
toolkits_with_cli = find_toolkits_with_cli()

setup(
    name='suan',  # 包的名字
    version='1.0.0',
    packages=find_packages(where='cli') + toolkits_with_cli,  # 仅包括包含cli.py文件的插件目录
    install_requires=[  # 如果有其他依赖包，可以在这里列出
        'click',
    ],
    package_data={  # 包括toolkits下的所有插件目录
        'toolkits': [f'../../toolkits/{plugin_name}/cli.py' for plugin_name in toolkits_with_cli],  # 仅包含有cli.py的插件目录
    },
    entry_points={  # 定义命令行入口
        'console_scripts': [
            'suan = cli.main:cli',  # suan 是命令行指令，指向 cli.main 文件中的 cli 对象
        ],
    },
    include_package_data=True,
    package_dir={
        '': 'cli',  # 设置包根目录为cli
    },
)
