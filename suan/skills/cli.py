"""``suan skills``: list and export the agent skills shipped with STK."""
import json
from pathlib import Path

import click


@click.group("skills")
def skills():
    """Agent skills (SKILL.md) for LLM hosts: visualization and monitoring workflows."""


@skills.command("list")
@click.option("--json", "as_json", is_flag=True, help="Print name, description and files as JSON.")
def list_command(as_json):
    """List the packaged skills."""
    from . import list_skills
    found = list_skills()
    if as_json:
        click.echo(json.dumps(found, ensure_ascii=False, indent=1))
        return
    for item in found:
        click.echo(f"{item['name']:<16} {item['description']}")


@skills.command("export")
@click.option("--dest", required=True, type=click.Path(file_okay=False, path_type=Path),
              help="Directory that receives one folder per skill (e.g. ~/.claude/skills).")
@click.option("--name", "names", multiple=True, help="Export only this skill (repeatable).")
@click.option("--force", is_flag=True, help="Replace skill folders that already exist in DEST.")
def export_command(dest, names, force):
    """Copy skills to DEST; the node reference is regenerated from the installed catalog."""
    from . import export_skills
    try:
        written = export_skills(dest, names, force=force)
    except (ValueError, OSError) as exc:  # FileExistsError, NotADirectoryError, permissions, ...
        raise click.ClickException(str(exc)) from None
    for folder in sorted({path.relative_to(dest).parts[0] for path in written}):
        click.echo(f"exported {dest / folder}")
