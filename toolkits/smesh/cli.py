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
    from pathlib import Path
    if not input or not output:
        raise click.UsageError('--input and --output are required')
    try:
        if Path(input).suffix.lower() == '.toml':
            from .core import generate_structure
            click.echo(generate_structure(input, output))
        else:
            from toolkits.sviz.field import read_field, write_field
            click.echo(write_field(output, read_field(input)))
    except (ValueError, OSError, KeyError) as exc:
        raise click.ClickException(str(exc)) from exc

@click.command()
@click.option('--file', '-f', required=True, help='要显示信息的网格文件')
def info(file):
    """
    显示网格文件或网格参数信息

    示例:
      smesh info --file mesh.out
    """
    import json
    from toolkits.sviz.field import field_info
    try:
        click.echo(json.dumps(field_info(file), ensure_ascii=False))
    except (ValueError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc

smesh.add_command(run)
smesh.add_command(info)

if __name__ == "__main__":
    smesh()
