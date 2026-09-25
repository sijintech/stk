#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Vendor the Blender GHOST + GPU + BLF subset used by the STK desktop engine.

Reads the pinned official source archive (``UPSTREAM.json``: URL + sha256),
extracts the whitelist from ``manifest.json`` into ``src/`` in upstream layout,
pulls in the transitive header closure from the allowed header pools, applies
``patches/*.patch`` and writes ``VENDORED.json`` with per-file sha256.

The include-closure checker fails on any quoted ``#include`` that is not
resolved by a vendored file, a shim (``shims/``), a build-generated file or an
explicitly declared external (system/sysroot) header. Preprocessor branches are
evaluated with a tri-state evaluator: macros listed as disabled features are
pruned, platform macros stay "unknown" so every platform's includes are
checked (macOS and Windows sources are vendored too).

The archive check mirrors ``blender/prepare.py`` (sha256 of the whole official
archive against the pin, no absolute or ``..`` member paths).

Usage:
  vendor.py [--archive PATH] [--download]   extract + check + write VENDORED.json
  vendor.py --check                         verify src/ against VENDORED.json
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

HERE = Path(__file__).resolve().parent
UPSTREAM = json.loads((HERE / "UPSTREAM.json").read_text())
MANIFEST = json.loads((HERE / "manifest.json").read_text())
SRC = HERE / "src"
SHIMS = HERE / "shims"
PATCHES = HERE / "patches"
DEFAULT_ARCHIVE = Path.home() / "opt" / "stk-src" / f"blender-{UPSTREAM['version']}.tar.xz"

CODE_SUFFIXES = {".c", ".cc", ".cpp", ".h", ".hh", ".hpp", ".inl", ".mm", ".m"}
INCLUDE_RE = re.compile(r'^\s*#\s*include\s*([<"])([^>"]+)[>"]')
DIRECTIVE_RE = re.compile(r"^\s*#\s*(if|ifdef|ifndef|elif|else|endif)\b(.*)$")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------------------
# Archive
# --------------------------------------------------------------------------------------

def ensure_archive(path: Path, download: bool) -> Path:
    if not path.exists():
        if not download:
            sys.exit(f"vendor.py: archive {path} missing (pass --download or --archive)")
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_suffix(path.suffix + ".part")
        print(f"vendor.py: downloading {UPSTREAM['source_archive']}")
        urllib.request.urlretrieve(UPSTREAM["source_archive"], part)
        part.rename(path)
    if sha256_file(path) != UPSTREAM["source_sha256"]:
        sys.exit("vendor.py: official source archive SHA256 differs from UPSTREAM.json")
    return path


def wanted_prefixes() -> list[str]:
    prefixes = [t["path"].rstrip("/") + "/" for t in MANIFEST["trees"]]
    prefixes += [p.rstrip("/") + "/" for p in MANIFEST["header_pools"]]
    prefixes += MANIFEST["files"]
    return prefixes


def read_archive(path: Path) -> dict[str, bytes]:
    """Return {upstream relative path: bytes} for members under the wanted prefixes."""
    prefixes = wanted_prefixes()
    files: dict[str, bytes] = {}
    with tarfile.open(path) as stream:
        for member in stream:
            if not member.isfile():
                continue
            parts = PurePosixPath(member.name).parts
            if len(parts) < 2 or PurePosixPath(member.name).is_absolute() or ".." in parts:
                raise SystemExit(f"vendor.py: unsafe archive path {member.name}")
            rel = PurePosixPath(*parts[1:]).as_posix()
            if any(rel == p or rel.startswith(p) for p in prefixes):
                files[rel] = stream.extractfile(member).read()
    return files


# --------------------------------------------------------------------------------------
# Preprocessor tri-state evaluation
# --------------------------------------------------------------------------------------

UNKNOWN = None
TOKEN_RE = re.compile(r"\s*(defined|\|\||&&|==|!=|<=|>=|<<|>>|[()!<>+\-*/%]|\d+[uUlL]*|0x[0-9a-fA-F]+|[A-Za-z_]\w*)")


class Expr:
    """Tiny recursive-descent evaluator for #if expressions with unknown values."""

    def __init__(self, text: str, macros_true: set, macros_false: set):
        text = re.sub(r"//.*", "", text)
        text = re.sub(r"/\*.*?\*/", "", text)
        self.tokens = []
        pos = 0
        text = text.strip()
        while pos < len(text):
            m = TOKEN_RE.match(text, pos)
            if not m:
                self.tokens = None  # Unparseable -> unknown.
                break
            self.tokens.append(m.group(1))
            pos = m.end()
            while pos < len(text) and text[pos].isspace():
                pos += 1
        self.i = 0
        self.t = macros_true
        self.f = macros_false

    def value(self):
        if self.tokens is None:
            return UNKNOWN
        try:
            v = self.or_()
        except (IndexError, ValueError):
            return UNKNOWN
        return v if self.i == len(self.tokens) else UNKNOWN

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def eat(self):
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def or_(self):
        v = self.and_()
        while self.peek() == "||":
            self.eat()
            r = self.and_()
            v = True if (v is True or r is True) else (False if (v is False and r is False) else UNKNOWN)
        return v

    def and_(self):
        v = self.cmp()
        while self.peek() == "&&":
            self.eat()
            r = self.cmp()
            v = False if (v is False or r is False) else (True if (v is True and r is True) else UNKNOWN)
        return v

    def cmp(self):
        v = self.unary()
        while self.peek() in ("==", "!=", "<", ">", "<=", ">=", "+", "-", "*", "/", "%", "<<", ">>"):
            self.eat()
            self.unary()
            v = UNKNOWN
        return v

    def unary(self):
        tok = self.eat()
        if tok == "!":
            v = self.unary()
            return UNKNOWN if v is UNKNOWN else (not v)
        if tok == "(":
            v = self.or_()
            if self.eat() != ")":
                raise ValueError
            return v
        if tok == "defined":
            paren = self.peek() == "("
            if paren:
                self.eat()
            name = self.eat()
            if paren and self.eat() != ")":
                raise ValueError
            return True if name in self.t else (False if name in self.f else UNKNOWN)
        if tok[0].isdigit():
            return int(re.sub(r"[uUlL]+$", "", tok), 0) != 0
        if tok in self.t:
            return True
        if tok in self.f:
            return False
        if self.peek() == "(":  # Function-like macro call: skip arguments.
            depth = 0
            while True:
                t = self.eat()
                depth += t == "("
                depth -= t == ")"
                if depth == 0:
                    break
        return UNKNOWN


def active_includes(text: str, macros_true: set, macros_false: set):
    """Yield (kind, name, line) for includes in branches that are not provably dead."""
    # Stack of (branch_live, any_branch_taken_definitely, parent_live).
    stack: list[list] = []
    live = True
    # Blank out block comments (keeping line numbers) so commented-out includes are ignored.
    text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    lines = text.splitlines()
    joined: list[tuple[int, str]] = []
    buf, start = "", 0
    for n, line in enumerate(lines, 1):
        if not buf:
            start = n
        if line.endswith("\\"):
            buf += line[:-1] + " "
            continue
        joined.append((start, buf + line))
        buf = ""
    for n, line in joined:
        d = DIRECTIVE_RE.match(line)
        if d:
            kind, rest = d.group(1), d.group(2).strip()
            if kind in ("if", "ifdef", "ifndef"):
                if kind == "if":
                    v = Expr(rest, macros_true, macros_false).value()
                else:
                    name = rest.split()[0] if rest.split() else ""
                    v = True if name in macros_true else (False if name in macros_false else UNKNOWN)
                    if kind == "ifndef" and v is not UNKNOWN:
                        v = not v
                stack.append([v, v is True, live])
                live = live and v is not False
            elif kind == "elif" and stack:
                top = stack[-1]
                v = Expr(rest, macros_true, macros_false).value()
                if top[1]:
                    v = False
                top[0] = v
                top[1] = top[1] or v is True
                live = top[2] and v is not False
            elif kind == "else" and stack:
                top = stack[-1]
                v = False if top[1] else (True if top[0] is False else UNKNOWN)
                top[0] = v
                live = top[2] and v is not False
            elif kind == "endif" and stack:
                live = stack.pop()[2]
            continue
        if not live:
            continue
        m = INCLUDE_RE.match(line)
        if m:
            yield ("quote" if m.group(1) == '"' else "angle", m.group(2).strip(), n)


# --------------------------------------------------------------------------------------
# Selection + closure
# --------------------------------------------------------------------------------------

def matches(rel: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(rel, p) for p in patterns)


def select(files: dict[str, bytes]) -> dict[str, str]:
    """Return {rel: reason} for the explicit whitelist (trees + files)."""
    chosen: dict[str, str] = {}
    for tree in MANIFEST["trees"]:
        root = tree["path"].rstrip("/") + "/"
        excl = [root + e for e in tree.get("exclude", [])]
        found = False
        for rel in files:
            if rel.startswith(root) and not matches(rel, excl):
                chosen[rel] = "tree"
                found = True
        if not found:
            sys.exit(f"vendor.py: manifest tree {root} matched nothing")
    for rel in MANIFEST["files"]:
        if rel not in files:
            sys.exit(f"vendor.py: manifest file {rel} not in archive")
        chosen[rel] = "file"
    return chosen


def closure(files: dict[str, bytes], chosen: dict[str, str]):
    """Pull the header closure from the pools; return (chosen, errors, system, shims_used)."""
    inc_dirs = MANIFEST["include_dirs"]
    pools = [p.rstrip("/") + "/" for p in MANIFEST["header_pools"]]
    generated = [re.compile(g) for g in MANIFEST["generated"]]
    externals = MANIFEST["external_quoted"]
    tru = set(MANIFEST["macros"]["true"])
    fal = set(MANIFEST["macros"]["false"])
    shim_names = {p.relative_to(SHIMS).as_posix() for p in SHIMS.rglob("*") if p.is_file()}
    errors: list[str] = []
    system: set[str] = set()
    shims_used: set[str] = set()
    work = [r for r in chosen if PurePosixPath(r).suffix in CODE_SUFFIXES]
    seen = set(work)

    def available(rel: str) -> bool:
        return rel in files and (rel in chosen or any(rel.startswith(p) for p in pools))

    def resolve(rel_from: str, name: str, kind: str):
        base = PurePosixPath(rel_from).parent
        candidates = []
        if kind == "quote":
            candidates.append(os.path.normpath((base / name).as_posix()))
        if name in shim_names:
            return "shim", name
        candidates += [os.path.normpath(f"{d}/{name}") for d in inc_dirs]
        for c in candidates:
            if available(c):
                return "upstream", c
        return None, None

    while work:
        rel = work.pop()
        text = files[rel].decode("utf-8", "replace")
        for kind, name, line in active_includes(text, tru, fal):
            what, target = resolve(rel, name, kind)
            if what == "shim":
                shims_used.add(target)
                continue
            if what == "upstream":
                if target not in chosen:
                    chosen[target] = "closure"
                if target not in seen:
                    seen.add(target)
                    work.append(target)
                continue
            if any(g.search(name) for g in generated):
                continue
            if kind == "angle" or name in externals or matches(name, externals):
                system.add(name)
                continue
            errors.append(f"{rel}:{line}: unresolved #include \"{name}\"")
    return chosen, errors, system, shims_used


def apply_patches(stage: Path) -> list[dict]:
    applied = []
    for patch in sorted(PATCHES.glob("*.patch")):
        proc = subprocess.run(["patch", "-p1", "--forward", "--batch", "-d", str(stage), "-i", str(patch)],
                              capture_output=True, text=True)
        if proc.returncode:
            sys.exit(f"vendor.py: patch {patch.name} failed:\n{proc.stdout}{proc.stderr}")
        applied.append({"file": patch.name, "sha256": sha256_file(patch)})
    return applied


def vendor(archive: Path) -> None:
    files = read_archive(archive)
    chosen = select(files)
    chosen, errors, system, shims_used = closure(files, chosen)
    if errors:
        print("\n".join(sorted(errors)), file=sys.stderr)
        sys.exit(f"vendor.py: include closure failed with {len(errors)} unresolved include(s)")

    stage = Path(tempfile.mkdtemp(prefix="stk-vendor-", dir=HERE))
    try:
        for rel in sorted(chosen):
            dst = stage / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(files[rel])
        patches = apply_patches(stage)
        for leftover in list(stage.rglob("*.orig")) + list(stage.rglob("*.rej")):
            leftover.unlink()
        if SRC.exists():
            shutil.rmtree(SRC)
        stage.rename(SRC)
    finally:
        if stage.exists():
            shutil.rmtree(stage)

    record = {
        "upstream": {k: UPSTREAM[k] for k in ("version", "tag", "commit", "source_archive", "source_sha256")},
        "patches": patches,
        "shims_used": sorted(shims_used),
        "system_includes": sorted(system),
        "counts": {
            "files": len(chosen),
            "by_reason": {r: sum(1 for v in chosen.values() if v == r) for r in ("tree", "file", "closure")},
        },
        "files": {rel: sha256_file(SRC / rel) for rel in sorted(chosen)},
    }
    (HERE / "VENDORED.json").write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n")
    print(f"vendor.py: vendored {len(chosen)} files ({record['counts']['by_reason']}), "
          f"{len(patches)} patch(es), {len(shims_used)} shim header(s) used, closure clean")


def check() -> None:
    record = json.loads((HERE / "VENDORED.json").read_text())
    present = {p.relative_to(SRC).as_posix() for p in SRC.rglob("*") if p.is_file()}
    expected = set(record["files"])
    bad = [f"missing {r}" for r in sorted(expected - present)]
    bad += [f"unexpected {r}" for r in sorted(present - expected)]
    bad += [f"modified {r}" for r in sorted(expected & present) if sha256_file(SRC / r) != record["files"][r]]
    if record["upstream"]["source_sha256"] != UPSTREAM["source_sha256"]:
        bad.append("VENDORED.json pin differs from UPSTREAM.json")
    if bad:
        print("\n".join(bad), file=sys.stderr)
        sys.exit(f"vendor.py --check: {len(bad)} problem(s)")
    print(f"vendor.py --check: {len(expected)} files match VENDORED.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--download", action="store_true", help="download the pinned archive if missing")
    parser.add_argument("--check", action="store_true", help="verify src/ against VENDORED.json")
    args = parser.parse_args()
    if args.check:
        check()
    else:
        vendor(ensure_archive(args.archive, args.download))


if __name__ == "__main__":
    main()
