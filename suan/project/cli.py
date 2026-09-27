"""Project-storage commands for exercising the first P1 slice before desktop integration."""

import json
from pathlib import Path

import click

from .store import ProjectStore


def _run(action):
    try:
        result = action()
    except (ValueError, OSError) as exc:
        raise click.ClickException(str(exc)) from None
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))


@click.group()
def project():
    """Experimental local SQLite projects (independent of the Linux task server)."""


@project.command("create")
@click.argument("directory", type=click.Path(path_type=Path, file_okay=False))
@click.option("--name", required=True, help="Project display name.")
def create(directory, name):
    """Create DIRECTORY/project.sqlite3 without replacing an existing database."""
    _run(lambda: ProjectStore.create(directory, name).snapshot())


@project.command("show")
@click.argument("directory", type=click.Path(path_type=Path, file_okay=False))
def show(directory):
    """Read a consistent snapshot of tables, typed fields and records."""
    _run(lambda: ProjectStore(directory).snapshot())


@project.command("apply")
@click.argument("directory", type=click.Path(path_type=Path, file_okay=False))
@click.option("--commands", required=True, type=click.File("r", encoding="utf-8"),
              help="JSON command-list file, or - for stdin.")
@click.option("--expected-revision", required=True, type=click.IntRange(min=0))
def apply(directory, commands, expected_revision):
    """Apply an entire edit batch, or roll it all back on failure/conflict."""
    _run(lambda: ProjectStore(directory).apply(json.load(commands), expected_revision=expected_revision))


@project.command("history")
@click.argument("directory", type=click.Path(path_type=Path, file_okay=False))
def history(directory):
    """List committed edit batches (this is not execution history or undo)."""
    _run(lambda: ProjectStore(directory).history())
