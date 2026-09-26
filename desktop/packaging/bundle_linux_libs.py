#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Copies the non-system shared libraries of installed executables next to them (Linux packages).

    bundle_linux_libs.py --prefix DIR --libdir lib/stk-desktop --docdir share/doc/stk-desktop
                         --exe bin/stk-desktop [--exe bin/stk-render ...] [--list]

Runs `ldd` on each executable (the full transitive closure) and copies every resolved library that
is not part of a desktop Linux system into <prefix>/<libdir>, named by its soname. The executables
carry DT_RPATH $ORIGIN/../lib/stk-desktop (packaging.cmake), which the dynamic loader also uses for
the dependencies of the bundled libraries.

"System" libraries stay out: glibc, the C++ runtime, the GPU driver stack (libGL/libEGL/libvulkan
loaders dispatch to the host's drivers), X11 / Wayland / xkbcommon / D-Bus (tied to the session),
and the ubiquitous compression, font and image libraries every desktop install has (zlib, zstd,
bzip2, brotli, libpng, FreeType). What remains on Ubuntu 24.04 is shaderc (Vulkan GLSL compiler)
and libepoxy.

For each bundled library the owning Debian package's copyright file is copied to
<docdir>/third-party/bundled/<package>.copyright, and BUNDLED.txt lists library, package, version.
Exit status 1 when a dependency is not found or a bundled library has no licence text.
"""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

SYSTEM = [re.compile(p) for p in (
    r"^linux-vdso\.so", r"^linux-gate\.so", r"^ld-linux.*\.so", r"^ld64\.so",
    r"^lib(c|m|dl|rt|pthread|resolv|util|anl|mvec|nsl|BrokenLocale)\.so",
    r"^libstdc\+\+\.so", r"^libgcc_s\.so", r"^libatomic\.so",
    r"^lib(GL|GLX|EGL|GLESv1_CM|GLESv2|OpenGL|GLdispatch)\.so", r"^libvulkan\.so", r"^libdrm", r"^libgbm\.so",
    r"^libX[a-zA-Z0-9]*\.so", r"^libxcb", r"^libxkbcommon", r"^libwayland-", r"^libdecor-", r"^libxshmfence",
    r"^libdbus-1\.so", r"^libsystemd\.so", r"^libcap\.so", r"^libgcrypt\.so", r"^libgpg-error\.so",
    r"^libffi\.so", r"^libexpat\.so", r"^libbsd\.so", r"^libmd\.so",
    r"^libz\.so", r"^libzstd\.so", r"^libbz2\.so", r"^liblzma\.so", r"^liblz4\.so",
    r"^libbrotli(common|dec|enc)\.so", r"^libpng16\.so", r"^libfreetype\.so",
    r"^libharfbuzz\.so", r"^libglib-2\.0\.so", r"^libgraphite2\.so", r"^libpcre2-8\.so",
)]

LDD_LINE = re.compile(r"^\s*(\S+)\s+=>\s+(\S+)\s+\(0x[0-9a-f]+\)\s*$")
LDD_NOT_FOUND = re.compile(r"^\s*(\S+)\s+=>\s+not found\s*$")


def is_system(soname):
    return any(p.search(soname) for p in SYSTEM)


def ldd(path):
    out = subprocess.run(["ldd", str(path)], capture_output=True, text=True, check=True).stdout
    found, missing = {}, []
    for line in out.splitlines():
        m = LDD_LINE.match(line)
        if m:
            found[m.group(1)] = m.group(2)
        elif LDD_NOT_FOUND.match(line):
            missing.append(LDD_NOT_FOUND.match(line).group(1))
    return found, missing


def debian_package(path, soname):
    """(package, version, copyright file) of the Debian package owning `path`: dpkg's database (the
    /usr-merged alias too), else, for a library extracted from .debs into a user sysroot (no dpkg
    database; desktop/cmake/sysroot), the Debian library package name guessed from the soname
    (libfoo.so.1 -> libfoo1, libfoo2.so.0 -> libfoo2-0) under <sysroot>/usr/share/doc."""
    pkg, ver = dpkg_owner(path)
    if pkg:
        return pkg, ver, Path("/usr/share/doc") / pkg / "copyright"
    text = str(path)
    if "/usr/lib/" in text:
        root = Path(text.split("/usr/lib/", 1)[0])
        base, _, sover = soname.partition(".so")
        sover = sover.lstrip(".").split(".")[0]
        guess = base + ("-" if base[-1:].isdigit() else "") + sover
        copyright_file = root / "usr" / "share" / "doc" / guess / "copyright"
        if copyright_file.is_file():
            return guess, None, copyright_file
    return None, None, None


def dpkg_owner(path):
    if not shutil.which("dpkg"):
        return None, None
    candidates = [str(path), str(Path(path).resolve())]
    for c in list(candidates):
        if c.startswith("/usr/lib/"):
            candidates.append(c[len("/usr"):])
        elif c.startswith("/lib/"):
            candidates.append("/usr" + c)
    for c in candidates:
        r = subprocess.run(["dpkg", "-S", c], capture_output=True, text=True)
        if r.returncode == 0 and ":" in r.stdout:
            pkg = r.stdout.split(":", 1)[0].strip()
            ver = subprocess.run(["dpkg-query", "-W", "-f=${Version}", pkg], capture_output=True, text=True).stdout.strip()
            return pkg, ver
    return None, None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--libdir", required=True)
    ap.add_argument("--docdir", required=True)
    ap.add_argument("--exe", action="append", required=True)
    ap.add_argument("--list", action="store_true", help="only print the libraries that would be bundled")
    args = ap.parse_args()

    prefix = Path(args.prefix)
    libdir = prefix / args.libdir
    bundled = {}
    problems = []
    for exe in args.exe:
        found, missing = ldd(prefix / exe)
        problems += [f"{exe}: {name} not found" for name in missing]
        for soname, path in found.items():
            if not is_system(soname):
                bundled[soname] = path
    if args.list:
        for soname, path in sorted(bundled.items()):
            print(f"{soname} => {path}")
        return 1 if problems else 0

    libdir.mkdir(parents=True, exist_ok=True)
    licdir = prefix / args.docdir / "third-party" / "bundled"
    rows = []
    for soname, path in sorted(bundled.items()):
        dest = libdir / soname
        if Path(path).resolve() != dest.resolve():
            shutil.copy2(Path(path).resolve(), dest)
        os.chmod(dest, 0o644)
        pkg, ver, copyright_file = debian_package(path, soname)
        if pkg:
            if copyright_file.is_file():
                licdir.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(copyright_file, licdir / f"{pkg}.copyright")
            else:
                problems.append(f"{soname}: {copyright_file} missing")
        else:
            problems.append(f"{soname}: owning package unknown (add its licence to {args.docdir}/third-party)")
        rows.append((soname, pkg or "?", ver or "?"))
        print(f"bundled {soname} ({pkg or '?'} {ver or ''}) from {path}")
    if rows:
        licdir.mkdir(parents=True, exist_ok=True)
        with open(licdir.parent / "BUNDLED.txt", "w", encoding="utf-8") as f:
            f.write("Shared libraries bundled in " + args.libdir + " (library, Debian package, version);\n"
                    "licence texts: bundled/<package>.copyright\n\n")
            for row in rows:
                f.write("\t".join(row) + "\n")
    for p in problems:
        print("error: " + p, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
