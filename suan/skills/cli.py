"""``suan skills``: list and export the agent skills shipped with STK."""
import json
from pathlib import Path

import click


@click.group("skills")
def skills():
    """Agent skills (SKILL.md) for LLM hosts and the versioned STK skill catalog."""


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


def _text(value):
    return value.get("en", "") if isinstance(value, dict) else str(value or "")


@skills.command("catalog")
@click.option("--query", default=None, help="Case-insensitive text filter (id, title, summary, preset).")
@click.option("--offset", default=0, show_default=True, type=int)
@click.option("--limit", default=50, show_default=True, type=int)
@click.option("--json", "as_json", is_flag=True, help="Print the page as JSON (the bridge's skills.list result).")
def catalog_command(query, offset, limit, as_json):
    """List the versioned skills (stk.skill/1) and their availability; nothing is evaluated."""
    from .catalog import SkillCatalogError, load_catalog
    try:
        page = load_catalog().page(offset=offset, limit=limit, query=query)
    except SkillCatalogError as exc:
        raise click.ClickException(str(exc)) from None
    if as_json:
        click.echo(json.dumps(page, ensure_ascii=False, indent=1))
        return
    for item in page["skills"]:
        click.echo(f"{item['ref']:<34} {item['availability']['status']:<11} {_text(item['title'])}")
    for problem in page["problems"]:
        click.echo(f"problem {problem['file']}: {problem['code']}: {problem['message']}", err=True)


@skills.command("show")
@click.argument("reference")
@click.option("--json", "as_json", is_flag=True, help="Print the resolved skill as JSON (skills.get).")
def show_command(reference, as_json):
    """Show one skill: ID (latest version) or ID@VERSION."""
    from .catalog import SkillCatalogError, load_catalog
    skill_id, sep, version = reference.partition("@")
    if sep and not version.isdigit():
        raise click.ClickException(f"Invalid version in {reference!r}; use ID@VERSION")
    try:
        skill = load_catalog().get(skill_id, int(version) if sep else None)
    except SkillCatalogError as exc:
        raise click.ClickException(str(exc)) from None
    if as_json:
        click.echo(json.dumps(skill, ensure_ascii=False, indent=1))
        return
    click.echo(f"{skill['ref']}  {_text(skill['title'])}")
    click.echo(f"sha256 {skill['content_sha256']}")
    click.echo(_text(skill["summary"]))
    click.echo(f"entry: {skill['entry']['kind']} {skill['entry'].get('preset', '')} via {skill['entry']['operation']}")
    if skill["guide"]:
        click.echo(f"guide: {skill['guide']['pack']} (suan skills export --name {skill['guide']['pack']})")
    click.echo("inputs: " + ", ".join(f"{i['name']} ({i['kind']})" for i in skill["inputs"]))
    click.echo("parameters: " + ", ".join(f"{p.get('name')}: {p.get('type')}" for p in skill["parameters"]))
    click.echo("outputs: " + ", ".join(f"{o['name']} ({o['type'] or '?'})" for o in skill["outputs"]))
    availability = skill["availability"]
    click.echo(f"availability: {availability['status']}" + (
        f" (unavailable outputs: {', '.join(availability['unavailable_outputs'])})"
        if availability["unavailable_outputs"] else ""))
    for issue in availability["issues"]:
        click.echo(f"  {issue['code']}: {issue['message']}")
    for item in skill["dependencies"]["runtime"]:
        click.echo(f"  not checked: {item['capability']} for {', '.join(item['outputs']) or 'all outputs'}")
