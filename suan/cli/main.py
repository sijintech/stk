"""Installed and source-tree CLI entry point."""

import importlib
from pathlib import Path
import sys

import click

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@click.group()
@click.version_option(package_name="suan_toolkits")
def cli():
    """STK scientific tools and persistent task runtime."""


def load_plugins():
    """Use package imports so discovery also works from an installed wheel."""
    import toolkits
    # sjob and third-party toolkits may be namespace packages without __init__.
    names = {path.parent.name for root in toolkits.__path__ for path in Path(root).glob('*/cli.py')}
    for name in sorted(names):
        module = importlib.import_module(f"toolkits.{name}.cli")
        command = getattr(module, name, None)
        if isinstance(command, click.Command):
            cli.add_command(command)


load_plugins()
from suan.runtime.cli import server, jobs, workspaces, connect

for command in (server, jobs, workspaces, connect):
    cli.add_command(command)


if __name__ == "__main__":
    cli()
