import click

@click.group()
def sviz():
    """
    sviz - 可视化工具

    主要功能:
      对科学数据进行可视化，包括标量场、矢量场等

    主要命令:
      plot-scalar    绘制标量场
      plot-vector    绘制矢量场
      info           显示可视化支持信息

    用法:
      一定要先查看子命令具体帮助再使用，不能想当然的输入参数，要根据具体帮助来输入参数。

    示例:
      sviz plot-scalar --input data.dat --output fig.png
      sviz plot-vector --input vec.dat --output fig.png
      sviz info

    获取帮助:
      sviz --help
      sviz plot-scalar --help
      sviz plot-vector --help
    """
    pass

@click.command()
@click.option('--input', '-i', required=True, help='输入数据文件')
@click.option('--output', '-o', required=False, help='输出图片文件')
@click.option('--axis', type=click.Choice(['x', 'y', 'z']), default='z')
@click.option('--index', type=int)
@click.option('--component', type=int, default=0)
def plot_scalar(input, output, axis, index, component):
    """
    绘制标量场

    示例:
      sviz plot-scalar --input data.dat --output fig.png
    """
    from .field import plot_field
    try:
        click.echo(plot_field(input, output or 'scalar.png', axis=axis, index=index, component=component))
    except (ValueError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc

@click.command()
@click.option('--input', '-i', required=True, help='输入矢量数据文件')
@click.option('--output', '-o', required=False, help='输出图片文件')
@click.option('--axis', type=click.Choice(['x', 'y', 'z']), default='z')
@click.option('--index', type=int)
def plot_vector(input, output, axis, index):
    """
    绘制矢量场

    示例:
      sviz plot-vector --input vec.dat --output fig.png
    """
    from .field import plot_field
    try:
        click.echo(plot_field(input, output or 'vector.png', vector=True, axis=axis, index=index))
    except (ValueError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc

@click.command()
def info():
    """
    显示可视化支持信息

    示例:
      sviz info
    """
    click.echo("[sviz] 支持标量场、矢量场等多种科学数据可视化")

sviz.add_command(plot_scalar, name='plot-scalar')
sviz.add_command(plot_vector, name='plot-vector')
sviz.add_command(info)

if __name__ == "__main__":
    sviz()
