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


@project.command("preview")
@click.argument("directory", type=click.Path(path_type=Path, file_okay=False))
@click.option("--commands", required=True, type=click.File("r", encoding="utf-8"),
              help="JSON command-list file, or - for stdin.")
@click.option("--expected-revision", required=True, type=click.IntRange(min=0))
def preview(directory, commands, expected_revision):
    """Inspect a hypothetical edit and its formulas without saving changes."""
    _run(lambda: ProjectStore(directory).preview(json.load(commands), expected_revision=expected_revision))


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


@project.group("snapshots")
def snapshots():
    """Capture and verify immutable input copies; ordinary table undo does not remove them."""


@snapshots.command("capture")
@click.argument("directory", type=click.Path(path_type=Path, file_okay=False))
@click.argument("record_ids", nargs=-1, required=True)
@click.option("--expected-revision", required=True, type=click.IntRange(min=0))
@click.option("--max-bytes", default=256 * 1024 * 1024, show_default=True, type=click.IntRange(min=1, max=1024 ** 4))
def capture_inputs(directory, record_ids, expected_revision, max_bytes):
    """Copy 1–100 indexed files and save a manifest after a final revision check."""
    _run(lambda: ProjectStore(directory).snapshots.capture(list(record_ids), expected_revision=expected_revision,
                                                          max_bytes=max_bytes))


@snapshots.command("list")
@click.argument("directory", type=click.Path(path_type=Path, file_okay=False))
def list_snapshots(directory):
    """Read saved manifests without scanning their objects or original sources."""
    _run(lambda: ProjectStore(directory).snapshots.list())


@snapshots.command("verify")
@click.argument("directory", type=click.Path(path_type=Path, file_okay=False))
@click.argument("snapshot_id")
def verify_snapshot(directory, snapshot_id):
    """Check all frozen bytes; report missing/corrupt objects without overwriting them."""
    _run(lambda: ProjectStore(directory).snapshots.verify(snapshot_id))


@snapshots.command("resolve")
@click.argument("directory", type=click.Path(path_type=Path, file_okay=False))
@click.argument("snapshot_id")
@click.argument("record_id")
def resolve_snapshot(directory, snapshot_id, record_id):
    """Verify one frozen file and return its current local object path."""
    _run(lambda: ProjectStore(directory).snapshots.resolve(snapshot_id, record_id))


@project.group("csv")
def csv_group():
    """Import typed CSV tables or export evaluated values (not full project backups)."""


@csv_group.command("import")
@click.argument("directory", type=click.Path(path_type=Path, file_okay=False))
@click.argument("source", type=click.Path(path_type=Path, dir_okay=False))
@click.option("--name", required=True)
@click.option("--types", "field_types", default="{}", help="JSON object mapping column names to field types.")
@click.option("--units", default="{}", help="JSON object mapping numeric column names to units.")
@click.option("--tsv", is_flag=True, help="Use tabs instead of commas.")
@click.option("--expected-revision", required=True, type=click.IntRange(min=0))
def import_csv(directory, source, name, field_types, units, tsv, expected_revision):
    """Create a new table from UTF-8 SOURCE in one atomic edit batch."""
    _run(lambda: ProjectStore(directory).csv.import_file(source.absolute(), name=name,
        types=json.loads(field_types), units=json.loads(units), delimiter="\t" if tsv else ",",
        expected_revision=expected_revision))


@csv_group.command("export")
@click.argument("directory", type=click.Path(path_type=Path, file_okay=False))
@click.argument("table_id")
@click.argument("destination", type=click.Path(path_type=Path, dir_okay=False))
@click.option("--tsv", is_flag=True, help="Use tabs instead of commas.")
@click.option("--expected-revision", required=True, type=click.IntRange(min=0))
def export_csv(directory, table_id, destination, tsv, expected_revision):
    """Write UTF-8 CSV with BOM; refuse to replace an existing destination."""
    _run(lambda: ProjectStore(directory).csv.export_file(table_id, destination.absolute(),
        delimiter="\t" if tsv else ",", expected_revision=expected_revision))
