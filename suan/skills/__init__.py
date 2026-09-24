"""Agent skills shipped with STK (``SKILL.md`` folders inside the package).

Each skill is a directory ``suan/skills/<name>/`` with a ``SKILL.md`` whose
YAML-style frontmatter declares ``name`` and ``description``, plus optional
``reference/`` and ``examples/`` files. ``suan skills export --dest DIR`` copies
them for an LLM host; the export regenerates ``stk-visualize/reference/nodes.md``
from the installed node catalog, so it lists exactly the nodes this install
can evaluate. Standard library only.
"""
from importlib import resources
from pathlib import Path
import re
import shutil

__all__ = ["export_skills", "list_skills", "read_frontmatter", "skill_names", "skills_root"]

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
NODES_REFERENCE = ("stk-visualize", "reference/nodes.md")


def skills_root():
    return resources.files(__name__)


def skill_names():
    return sorted(entry.name for entry in skills_root().iterdir()
                  if entry.is_dir() and NAME_RE.match(entry.name) and entry.joinpath("SKILL.md").is_file())


def read_frontmatter(text):
    """``{key: value}`` of a ``---`` delimited frontmatter block (single-line ``key: value`` entries)."""
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.DOTALL)
    if not match:
        return {}
    data = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() and not line.startswith((" ", "\t")):
            data[key.strip()] = value.strip().strip('"')
    return data


def list_skills():
    """``[{"name", "description", "files"}]`` of the packaged skills."""
    found = []
    for name in skill_names():
        folder = skills_root().joinpath(name)
        meta = read_frontmatter(folder.joinpath("SKILL.md").read_text(encoding="utf-8"))
        found.append({"name": meta.get("name", name), "description": meta.get("description", ""),
                      "files": sorted(_files(folder))})
    return found


def _files(folder, prefix=""):
    for entry in folder.iterdir():
        if entry.name.startswith((".", "__")):
            continue
        relative = f"{prefix}{entry.name}"
        if entry.is_dir():
            yield from _files(entry, relative + "/")
        else:
            yield relative


def export_skills(dest, names=None, *, force=False, catalog=None):
    """Copy skills into ``dest/<name>/``; returns the written paths.

    Existing skill folders are replaced only with ``force``. ``catalog`` (an
    ``stk.catalog/1`` document, default: the installed registry) regenerates
    the node reference.
    """
    available = skill_names()
    names = list(names) if names else available
    unknown = [name for name in names if name not in available]
    if unknown:
        raise ValueError(f"Unknown skill(s): {', '.join(unknown)}; available: {', '.join(available)}")
    dest = Path(dest)
    existing = [name for name in names if (dest / name).exists()]
    if existing and not force:
        raise FileExistsError(f"{', '.join(str(dest / name) for name in existing)} already exist; use --force to replace")
    written = []
    for name in names:
        target = dest / name
        if target.exists():
            shutil.rmtree(target)
        source = skills_root().joinpath(name)
        for relative in sorted(_files(source)):
            path = target / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if (name, relative) == NODES_REFERENCE:
                from .reference import nodes_markdown
                if catalog is None:
                    from suan.graph.catalog import catalog_document
                    catalog = catalog_document()
                path.write_text(nodes_markdown(catalog), encoding="utf-8")
            else:
                entry = source
                for part in relative.split("/"):  # Traversable.joinpath takes one part on Python 3.10
                    entry = entry.joinpath(part)
                path.write_bytes(entry.read_bytes())
            written.append(path)
    return written
