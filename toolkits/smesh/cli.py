import click

@click.group()
def smesh():
    """
    smesh - 网格处理工具

    主要功能:
      生成、处理和分析科学计算中的网格数据

    主要命令:
      run         运行网格生成或处理任务
      info        显示网格文件或网格参数信息

    用法:
      一定要先查看子命令具体帮助再使用，不能想当然的输入参数，要根据具体帮助来输入参数。

    示例:
      smesh run --input mesh.in --output mesh.out
      smesh info --file mesh.out

    获取帮助:
      smesh --help
      smesh run --help
      smesh info --help
    """
    pass

@click.command()
@click.option('--input', '-i', required=False, help='输入网格文件')
@click.option('--output', '-o', required=False, help='输出网格文件')
def run(input, output):
    """
    运行网格生成或处理任务

    示例:
      smesh run --input mesh.in --output mesh.out
    """
    click.echo(f"[smesh] 运行网格处理: 输入={input}, 输出={output}")

@click.command()
@click.option('--file', '-f', required=True, help='要显示信息的网格文件')
def info(file):
    """
    显示网格文件或网格参数信息

    示例:
      smesh info --file mesh.out
    """
    click.echo(f"[smesh] 显示网格信息: {file}")

smesh.add_command(run)
smesh.add_command(info)

if __name__ == "__main__":
    smesh()
