#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check the STK desktop message catalogs (Python standard library only).

Fails (exit status 1) when:
  * a catalog is not a flat JSON object of strings (keys starting with "_" are comments);
  * a key is missing from any catalog (every catalog must have the same key set);
  * a message is empty;
  * the {placeholders} of a key differ between catalogs;
  * a key used in the sources (tr("..."), tr_or("...", ...), format("...", ...), STK_TR("..."))
    is missing from the reference catalog.

Usage:
  check_i18n.py [--catalogs DIR] [--reference zh_CN] [--scan DIR ...] [--no-scan]

Defaults: catalogs next to this script; sources scanned under desktop/ (the parent of app/).
"""

import argparse
import json
import os
import re
import sys

KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_+\-]+)+$")
USE_RE = re.compile(r"\b(?:tr|tr_or|format|STK_TR)\(\s*\"([A-Za-z][A-Za-z0-9_.+\-]*)\"\s*[,)]")
PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
SOURCE_EXT = (".cc", ".cpp", ".cxx", ".hh", ".hpp", ".h", ".mm")
SKIP_DIRS = {"third_party", ".git", "build", "node_modules", "tests"}  # tests use made-up keys


def load_catalogs(directory):
    catalogs, errors = {}, []
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".json"):
            continue
        lang = name[: -len(".json")]
        path = os.path.join(directory, name)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as exc:
            errors.append(f"{name}: cannot parse: {exc}")
            continue
        if not isinstance(data, dict):
            errors.append(f"{name}: top level must be a JSON object")
            continue
        entries = {}
        for key, value in data.items():
            if key.startswith("_"):
                continue
            if not isinstance(value, str):
                errors.append(f"{name}: '{key}' is not a string")
                continue
            if not KEY_RE.match(key):
                errors.append(f"{name}: '{key}' is not a dotted id (e.g. 'ui.ok')")
            if not value.strip():
                errors.append(f"{name}: '{key}' is empty")
            entries[key] = value
        catalogs[lang] = entries
    return catalogs, errors


def check_catalogs(catalogs):
    errors = []
    all_keys = set()
    for entries in catalogs.values():
        all_keys |= set(entries)
    for lang, entries in sorted(catalogs.items()):
        for key in sorted(all_keys - set(entries)):
            others = [other for other, e in catalogs.items() if key in e]
            errors.append(f"{lang}.json: missing key '{key}' (present in {', '.join(sorted(others))})")
    for key in sorted(all_keys):
        sets = {lang: set(PLACEHOLDER_RE.findall(e[key])) for lang, e in catalogs.items() if key in e}
        if len({frozenset(s) for s in sets.values()}) > 1:
            detail = "; ".join(f"{lang}: {sorted(s)}" for lang, s in sorted(sets.items()))
            errors.append(f"placeholders differ for '{key}': {detail}")
    return errors


def used_keys(roots):
    found = {}
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith("build")]
            for name in filenames:
                if not name.endswith(SOURCE_EXT):
                    continue
                path = os.path.join(dirpath, name)
                try:
                    with open(path, encoding="utf-8", errors="replace") as f:
                        text = f.read()
                except OSError:
                    continue
                for m in USE_RE.finditer(text):
                    key = m.group(1)
                    line_start = text.rfind("\n", 0, m.start()) + 1
                    if text[line_start:m.start()].lstrip().startswith(("*", "//", "/*")):
                        continue  # documentation examples
                    if KEY_RE.match(key) and not key.endswith("."):
                        line = text.count("\n", 0, m.start()) + 1
                        found.setdefault(key, f"{os.path.relpath(path, root)}:{line}")
    return found


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--catalogs", default=here, help="directory with <lang>.json catalogs")
    ap.add_argument("--reference", default="zh_CN", help="catalog that must contain every used key")
    ap.add_argument("--scan", action="append", help="source directory to scan for used keys (repeatable)")
    ap.add_argument("--no-scan", action="store_true", help="only compare the catalogs")
    args = ap.parse_args(argv)

    catalogs, errors = load_catalogs(args.catalogs)
    if not catalogs:
        errors.append(f"no catalogs found in {args.catalogs}")
    errors += check_catalogs(catalogs)
    if not args.no_scan and catalogs:
        roots = args.scan or [os.path.dirname(os.path.dirname(here))]
        reference = catalogs.get(args.reference)
        if reference is None:
            errors.append(f"reference catalog '{args.reference}' not found")
        else:
            for key, where in sorted(used_keys(roots).items()):
                if key not in reference:
                    errors.append(f"{where}: key '{key}' is missing from {args.reference}.json")

    for e in errors:
        print(f"check_i18n: {e}", file=sys.stderr)
    counts = ", ".join(f"{lang}={len(e)}" for lang, e in sorted(catalogs.items()))
    print(f"check_i18n: {'FAIL' if errors else 'OK'} ({counts}; {len(errors)} problem(s))")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
