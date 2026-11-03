#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Assemble an explicit, source-complete Linux helper installation.

Build-time input paths are explicit and trusted; no dependency resolution or
download is performed. The lock and all input bytes must come from the release
builder's separately verified provenance. Its self-hashes are not signatures.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while data := stream.read(1024 * 1024):
            h.update(data)
    return h.hexdigest()


def run(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs).stdout


def source(item):
    path = Path(item["path"])
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise ValueError("Package input must be an explicit ordinary file")
    if not re.fullmatch("[0-9a-f]{64}", item["sha256"]) or digest(path) != item["sha256"]:
        raise ValueError("Package input hash mismatch")
    return path


def name(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+~-]{0,159}", value):
        raise ValueError("Invalid package input name")
    return value


def copy_checked(origin, target, expected):
    shutil.copyfile(origin, target)
    if digest(target) != expected:
        raise ValueError("Package input changed while copying")


def assemble(build, prefix, lock_path):
    if platform.system() != "Linux" or not build.is_absolute() or not prefix.is_absolute():
        raise ValueError("Only explicit Linux build and installation paths are supported")
    lock = json.loads(lock_path.read_text())
    if type(lock) is not dict or set(lock) != {"format", "platform", "architecture", "libraries",
                                              "components", "build_files", "host_requirements"}:
        raise ValueError("Invalid package lock")
    if lock["format"] != "stk.peer-helper-package-lock/1" or lock["platform"] != "linux":
        raise ValueError("Invalid package lock")
    machine = {"x86_64": "x86_64", "aarch64": "aarch64"}.get(platform.machine().lower())
    if lock["architecture"] != machine:
        raise ValueError("Package architecture mismatch")
    # mkdir refuses an existing prefix. Failed partial output stays visible and
    # has no manifest; it cannot be mistaken for a completed installation.
    prefix.mkdir(mode=0o755)
    run(["cmake", "--install", str(build), "--prefix", str(prefix), "--component", "PeerHelper"])
    exe = prefix / "bin/stk-peer-transport"
    if not exe.is_file() or not exe.stat().st_mode & stat.S_IXUSR:
        raise ValueError("Installed helper is missing")
    files = []
    components = []
    assigned = {"bin/stk-peer-transport": ("executable", "stk-peer-helper")}
    for library in lock["libraries"]:
        origin = source(library)
        soname = name(library["soname"])
        target = prefix / "lib" / soname
        target.parent.mkdir(exist_ok=True)
        if target.exists():
            raise ValueError("Ambiguous library SONAME")
        copy_checked(origin, target, library["sha256"])
        # CMake's ELF editor removes build/sysroot RUNPATH without changing the
        # immutable original library used by existing regression evidence.
        script = prefix / "remove-rpath.cmake"
        script.write_text('file(RPATH_REMOVE FILE "${LIBRARY}")\n')
        try:
            run(["cmake", f"-DLIBRARY={target}", "-P", str(script)])
        finally:
            script.unlink()
        assigned[target.relative_to(prefix).as_posix()] = ("library", library["component"])
    for component in lock["components"]:
        identity = name(component["id"])
        if (not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,63}", identity)
                or not component["notices"] or not component["sources"]
                or any(c["id"] == identity for c in components)):
            raise ValueError("Invalid component declaration")
        entry = {key: component[key] for key in ("id", "version", "license")}
        for key, role, directory in (("notices", "notice", "licenses"), ("sources", "source", "sources")):
            entry[key] = []
            for item in component[key]:
                target = prefix / directory / identity / name(item["name"])
                target.parent.mkdir(parents=True, exist_ok=True)
                origin = source(item)
                # CMake installs the helper MIT text; require identical bytes.
                if target.exists():
                    if digest(target) != item["sha256"]:
                        raise ValueError("Conflicting installed notice")
                else:
                    copy_checked(origin, target, item["sha256"])
                relative = target.relative_to(prefix).as_posix()
                if relative in assigned:
                    raise ValueError("Duplicate package input")
                assigned[relative] = (role, identity)
                entry[key].append(relative)
        components.append(entry)
    for item in lock["build_files"]:
        target = prefix / "build" / name(item["name"])
        target.parent.mkdir(exist_ok=True)
        if target.exists():
            raise ValueError("Duplicate build input")
        copy_checked(source(item), target, item["sha256"])
        assigned[target.relative_to(prefix).as_posix()] = ("build", "stk-peer-helper")
    actual = {p.relative_to(prefix).as_posix() for p in prefix.rglob("*") if p.is_file()}
    if actual != set(assigned):
        raise ValueError("Unaccounted installed files")
    dynamic = run(["readelf", "-d", str(exe)])
    if "(RUNPATH)" in dynamic or "Library rpath: [$ORIGIN/../lib]" not in dynamic:
        raise ValueError("Helper must have only its relative installation RPATH")
    for relative, (role, component) in sorted(assigned.items()):
        path = prefix / relative
        files.append({"path": relative, "bytes": path.stat().st_size,
                      "sha256": digest(path), "role": role, "component": component})
    manifest = {"format": "stk.peer-helper-installation/1", "abi": "stk.peer-helper-ipc/1",
                "protocol": "stk.peer/1", "platform": "linux", "architecture": machine,
                "executable": "bin/stk-peer-transport", "files": files,
                "components": components, "host_requirements": lock["host_requirements"]}
    target = prefix / "helper-manifest.json"
    with target.open("x", encoding="utf-8") as out:
        json.dump(manifest, out, ensure_ascii=False, sort_keys=True, indent=2)
        out.write("\n")
    return {"files": len(files), "components": len(components),
            "manifest_sha256": digest(target)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = assemble(args.build, args.prefix, args.lock)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        parser.exit(1, "Helper package assembly failed; partial prefix preserved\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
