"""Read-only relocation for unchanged external FileIndex paths in imported workspaces.

The workspace descriptor belongs beside the imported ``project`` directory. Original
Windows/POSIX path syntax is parsed independently of the current host. Mapping changes
neither SQLite cells nor journal/history/signatures, and never reads resource contents.
"""
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat

from .store import FORMAT_VERSION, ProjectError, ProjectStore, _expected_revision, _id, _text

_SHA = re.compile(r"[a-f0-9]{64}\Z")
_RESOURCE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}\Z")


def _syntax(value, location=None):
    if type(value) is not str or not value or len(value) > 32768 or "\0" in value:
        raise ProjectError("Workspace source path is invalid")
    if location == "external:windows" or location is None and PureWindowsPath(value).is_absolute():
        result = PureWindowsPath(value)
        flavor = "windows"
    else:
        result = PurePosixPath(value)
        flavor = "posix"
    if not result.is_absolute() or ".." in result.parts:
        raise ProjectError("Workspace source roots must be absolute without parent traversal")
    return flavor, result


def resolve_workspace_path(project_root, location, path):
    """Return a safely relocated local path, or None when no portable mapping exists.

    An existing malformed descriptor always raises. Absence of a descriptor preserves
    the ordinary FileIndex platform checks. Only metadata is read; the resource is not
    opened and original host paths are never probed by this resolver.
    """
    if location not in {"external:posix", "external:windows"}:
        raise ProjectError("Workspace relocation only accepts external FileIndex paths")
    project_root = Path(project_root).absolute()
    destination = project_root.parent
    descriptor = destination / "workspace.json"
    try:
        descriptor.lstat()
    except FileNotFoundError:
        return None
    from .workspace_bundle import (FORMAT, MAX_MANIFEST_BYTES, MAX_FILES, _decode, _name,
                                   _reader, _safe_ancestors, _sensitive_name, _state)
    with _reader(descriptor) as (stream, before):
        if before.st_size > MAX_MANIFEST_BYTES:
            raise ProjectError("Workspace descriptor exceeds 16 MiB")
        saved = _decode(stream.read(MAX_MANIFEST_BYTES + 1))
    if (type(saved) is not dict or set(saved) != {"format", "archive_sha256", "project", "state",
            "resources", "diagnostics", "complete"} or saved["format"] != FORMAT or
            type(saved["archive_sha256"]) is not str or not _SHA.fullmatch(saved["archive_sha256"]) or
            type(saved["complete"]) is not bool or type(saved["diagnostics"]) is not list or
            len(saved["diagnostics"]) > MAX_FILES or any(type(d) is not dict for d in saved["diagnostics"])):
        raise ProjectError("Workspace descriptor is invalid")
    _state(saved["state"])
    expected = saved["project"]
    if (project_root.name != "project" or type(expected) is not dict or not {
            "id", "name", "revision", "format_version", "source_root"} <= expected.keys() or
            expected.keys() - {"id", "name", "revision", "format_version", "source_root", "aliases"}):
        raise ProjectError("Workspace descriptor does not identify this project directory")
    _id(expected["id"]); _text(expected["name"], "Workspace project name")
    _expected_revision(expected["revision"])
    if type(expected["format_version"]) is not int or not 1 <= expected["format_version"] <= FORMAT_VERSION:
        raise ProjectError("Workspace descriptor project format is invalid")
    project_flavor, project_source = _syntax(expected["source_root"])
    project_aliases = expected.get("aliases", [])
    if type(project_aliases) is not list or len(project_aliases) > 128:
        raise ProjectError("Workspace project aliases must be a bounded array")
    project_origins = [(project_flavor, project_source), *[_syntax(alias) for alias in project_aliases]]
    if any(_sensitive_name(origin.parts[1:]) for _, origin in project_origins):
        raise ProjectError("Workspace project aliases cannot name host credential directories")
    _safe_ancestors(project_root)
    if ProjectStore(project_root).info()["id"] != expected["id"]:
        raise ProjectError("Workspace descriptor UUID does not match the opened project")
    resources = saved["resources"]
    if type(resources) is not list or len(resources) > 1024:
        raise ProjectError("Workspace descriptor resource mappings are invalid")
    mappings = [(flavor, origin, project_root, "directory") for flavor, origin in project_origins]
    identities, sources, targets = set(), {(flavor, origin): project_root for flavor, origin in project_origins}, set()
    for resource in resources:
        if (type(resource) is not dict or not {"id", "source", "path", "kind"} <= resource.keys() or
                resource.keys() - {"id", "source", "path", "kind", "aliases"} or
                type(resource["id"]) is not str or not _RESOURCE_ID.fullmatch(resource["id"]) or
                resource["id"].casefold() in identities or type(resource["kind"]) is not str or
                resource["kind"] not in {"file", "directory"}):
            raise ProjectError("Workspace descriptor resource mapping is invalid")
        flavor, source = _syntax(resource["source"])
        aliases = resource.get("aliases", [])
        if type(aliases) is not list or len(aliases) > 128:
            raise ProjectError("Workspace resource aliases must be a bounded array")
        origins = [(flavor, source), *[_syntax(alias) for alias in aliases]]
        parts = _name(resource["path"])
        if (len(parts) != 3 or parts[:2] != ["resources", resource["id"]] or _sensitive_name(parts[2:]) or
                any(_sensitive_name(origin.parts[1:]) for _, origin in origins) or resource["path"].casefold() in targets):
            raise ProjectError("Workspace descriptor resource mapping is ambiguous or excluded")
        target = destination.joinpath(*parts)
        _safe_ancestors(target)
        for origin_flavor, origin in origins:
            identity = origin_flavor, origin
            if identity in sources and sources[identity] != target:
                raise ProjectError("Workspace resource aliases map the same source to different targets")
            if identity not in sources:
                sources[identity] = target
                mappings.append((origin_flavor, origin, target, resource["kind"]))
        identities.add(resource["id"].casefold()); targets.add(resource["path"].casefold())
    flavor, original = _syntax(path, location)
    for source_flavor, source, target, kind in sorted(mappings, key=lambda entry: len(entry[1].parts), reverse=True):
        if flavor != source_flavor:
            continue
        try:
            suffix = original.relative_to(source)
        except ValueError:
            continue
        if kind == "file" and suffix.parts:
            raise ProjectError("Workspace file resource cannot contain child paths")
        if suffix.parts:
            _name("/".join(suffix.parts))
        candidate = target.joinpath(*suffix.parts)
        if not candidate.is_relative_to(destination):
            raise ProjectError("Workspace relocation would escape its package directory")
        _safe_ancestors(candidate)
        # Do not require that it still exists: FileIndex retains ordinary missing-file
        # diagnostics after a package resource is intentionally removed.
        try:
            info = candidate.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise ProjectError("Workspace resources cannot be symbolic links")
        except FileNotFoundError:
            pass
        return candidate
    return None
