import click
import os
import locale
import glob
import subprocess


@click.group()
def sjob():
    """与sjob插件相关的命令"""
    pass


@sjob.command(name='batCommand')
@click.option('--command', '-c', type=str, default='', help='每个目录中要执行的命令字符串')
@click.option('--folder_pattern', '-f', type=str, default='./*', help='目录通配符，默认为当前目录下的所有子目录')
def batch_all_command(command, folder_pattern):
    """
    遍历所有符合指定模式的目录，并在每个目录中执行指定的命令。
    """

    # 去掉前面的等号
    if folder_pattern.startswith('='):
        folder_pattern = folder_pattern[1:]  # 去掉前面的等号

    # 去掉外层的双引号或单引号
    if (folder_pattern.startswith('"') and folder_pattern.endswith('"')) or \
            (folder_pattern.startswith("'") and folder_pattern.endswith("'")):
        folder_pattern = folder_pattern[1:-1]
    if (command.startswith('"') and command.endswith('"')) or \
            (command.startswith("'") and command.endswith("'")):
        command = command[1:-1]

    # 获取当前工作目录的绝对路径
    current_dir = os.getcwd()
    # 获取系统默认编码
    system_encoding = locale.getpreferredencoding()

    # 使用 glob 模块解析通配符
    folder_list = [f for f in glob.glob(folder_pattern) if os.path.isdir(f)]

    # 遍历所有找到的目录
    for folder in folder_list:
        # 确保路径是一个有效目录
        if os.path.isdir(folder):
            # 切换到目标目录
            os.chdir(folder)

            # 输出正在执行的命令及目录信息
            print(f"-- 在目录 {folder} 中执行命令: {command}")

            try:
                # 使用 subprocess 捕获输出并解码
                result = subprocess.run(command, shell=True, check=True, text=True, capture_output=True,
                                        encoding=system_encoding)
                print(result.stdout)  # 输出正确解码的结果
            except subprocess.CalledProcessError as e:
                # 如果命令执行失败，输出错误信息
                print(f"命令执行失败: {e}")

                # 切换回初始工作目录
            os.chdir(current_dir)


@sjob.command()
@click.option('--name', '-n', type=str, default='job')
@click.option('--message', '-m', multiple=True)
def create():
    """创建一个新任务"""
    pass


# 测试示例：列出每个目录的内容
if __name__ == "__main__":
    # 指定命令和目录模式
    test_command = "dir"
    test_folder_pattern = "./*"  # 当前目录下的所有子目录

    # 调用批量执行命令函数
    batch_all_command(test_command, test_folder_pattern)
