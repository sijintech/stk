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
    """List committed edits and undo/redo actions (not simulation execution history)."""
    _run(lambda: ProjectStore(directory).history())


@project.command("backup")
@click.argument("directory", type=click.Path(path_type=Path, file_okay=False))
def backup(directory):
    """Create a consistent database backup in DIRECTORY/backups (external assets are separate)."""
    _run(lambda: ProjectStore(directory).backup())


@project.command("upgrade")
@click.argument("directory", type=click.Path(path_type=Path, file_okay=False))
@click.option("--expected-revision", required=True, type=click.IntRange(min=0))
def upgrade(directory, expected_revision):
    """Back up and explicitly upgrade an older project; opening alone never migrates it."""
    _run(lambda: ProjectStore(directory).upgrade(expected_revision=expected_revision))


@project.command("undo")
@click.argument("directory", type=click.Path(path_type=Path, file_okay=False))
@click.option("--expected-revision", required=True, type=click.IntRange(min=0))
def undo(directory, expected_revision):
    """Undo the latest active edit batch as a new revision."""
    _run(lambda: ProjectStore(directory).undo(expected_revision=expected_revision))


@project.command("redo")
@click.argument("directory", type=click.Path(path_type=Path, file_okay=False))
@click.option("--expected-revision", required=True, type=click.IntRange(min=0))
def redo(directory, expected_revision):
    """Reapply the next undone batch; a new edit discards redo."""
    _run(lambda: ProjectStore(directory).redo(expected_revision=expected_revision))


@project.group("files")
def files():
    """Index ordinary local files in project tables; never copy or remove their contents."""


@files.command("index")
@click.argument("directory", type=click.Path(path_type=Path, file_okay=False))
@click.argument("paths", nargs=-1, required=True)
@click.option("--expected-revision", required=True, type=click.IntRange(min=0))
def index_files(directory, paths, expected_revision):
    """Register up to 100 file paths; relative paths are relative to the project directory."""
    _run(lambda: ProjectStore(directory).files.index(list(paths), expected_revision=expected_revision))


@files.command("list")
@click.argument("directory", type=click.Path(path_type=Path, file_okay=False))
def list_files(directory):
    """Read saved file observations without scanning the filesystem."""
    _run(lambda: ProjectStore(directory).files.list())


@files.command("refresh")
@click.argument("directory", type=click.Path(path_type=Path, file_okay=False))
@click.argument("record_ids", nargs=-1, required=True)
@click.option("--expected-revision", required=True, type=click.IntRange(min=0))
def refresh_files(directory, record_ids, expected_revision):
    """Refresh metadata for up to 100 explicit file record IDs."""
    _run(lambda: ProjectStore(directory).files.refresh(list(record_ids), expected_revision=expected_revision))


@files.command("resolve")
@click.argument("directory", type=click.Path(path_type=Path, file_okay=False))
@click.argument("record_id")
@click.option("--expected-revision", required=True, type=click.IntRange(min=0))
def resolve_file(directory, record_id, expected_revision):
    """Check an indexed location and return its absolute path; do not open it."""
    _run(lambda: ProjectStore(directory).files.resolve(record_id, expected_revision=expected_revision))
