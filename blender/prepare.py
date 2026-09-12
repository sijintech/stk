#!/usr/bin/env python3
"""Prepare a reproducible Blender fork without resetting anyone's working tree."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parent
UPSTREAM = json.loads((ROOT / "upstream.json").read_text())


def git(source, *args, check=True):
    return subprocess.run(["git", "-C", str(source), *args], check=check, capture_output=True, text=True)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hydrate_archive(source, archive):
    """Use the official checksummed archive for LFS data absent on the GitHub mirror."""
    archive = Path(archive)
    if digest(archive) != UPSTREAM["source_sha256"]:
        raise ValueError("Official source archive SHA256 differs from upstream.json")
    with tarfile.open(archive) as stream:
        for member in stream:
            if not member.isfile():
                continue
            relative = Path(*Path(member.name).parts[1:])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Unsafe archive path")
            target = source / relative
            if target.is_symlink() or source not in target.resolve().parents:
                raise ValueError("Archive target traverses a symlink outside the checkout")
            pointer = (target.is_file() and target.stat().st_size < 256 and
                       target.read_bytes().startswith(b"version https://git-lfs.github.com/spec/v1"))
            if not target.exists() or pointer:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(stream.extractfile(member).read())
                target.chmod(member.mode)


def prepare(source, clone=False, archive=None):
    source = Path(source).resolve()
    if not source.exists():
        if not clone:
            raise ValueError("Source directory does not exist; use --clone to download the pinned release")
        subprocess.run(["git", "clone", "--depth", "1", "--branch", UPSTREAM["tag"],
                        UPSTREAM["repository"], str(source)], check=True,
                       env={**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"})
    if git(source, "rev-parse", "HEAD").stdout.strip() != UPSTREAM["commit"]:
        raise ValueError("Blender HEAD differs from upstream.json; use a separate pinned checkout")
    if archive:
        hydrate_archive(source, archive)
    stamp_path = source / ".stk-overlay.json"
    stamp = json.loads(stamp_path.read_text()) if stamp_path.exists() else {}
    old_files = stamp.get("files", {})
    files = [p for tree in (ROOT / "source", ROOT / "scripts") for p in tree.rglob("*")
             if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    # Check *every* destination before applying anything. Never silently replace
    # user edits, even if a previously prepared overlay is being upgraded.
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        target = source / relative
        if target.exists() and digest(target) not in {digest(path), old_files.get(relative)}:
            raise ValueError(f"Local edit would be overwritten: {target}")
    patches = sorted((ROOT / "patches").glob("*.patch"))
    if len(patches) != 1:
        raise ValueError("Expected a single atomic upstream integration patch")
    patch = patches[0]
    check = git(source, "apply", "--check", str(patch), check=False)
    if check.returncode:
        reverse = git(source, "apply", "--reverse", "--check", str(patch), check=False)
        if reverse.returncode:
            raise ValueError("Upstream integration has conflicting edits:\n" + check.stderr)
    else:
        git(source, "apply", str(patch))
    for path in files:
        target = source / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or digest(path) != digest(target):
            shutil.copyfile(path, target)
    stamp_path.write_text(json.dumps({"upstream": UPSTREAM["commit"], "patch": digest(patch),
        "files": {p.relative_to(ROOT).as_posix(): digest(p) for p in files}}, indent=2) + "\n")
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--clone", action="store_true")
    parser.add_argument("--source-archive", type=Path, help="Official archive to hydrate Git LFS data")
    args = parser.parse_args()
    try:
        print("Prepared STK Blender source:", prepare(args.source_dir, args.clone, args.source_archive))
    except (ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
