#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Smoke test of an installed / unpacked STK Desktop (a prefix, a tarball tree or a dir with STK.app).

    check_install.py --prefix DIR --workdir DIR [--backend opengl|vulkan|metal]
                     [--payload DIR] [--python PY --repo REPO [--golden PNG]]

1. Layout: the executables, fonts, catalogs and licence texts are where packaging.cmake puts them
   (bin/ + share/, or STK.app/Contents/{MacOS,Resources}); on Linux `ldd` finds every library.
2. `stk-desktop --headless --verbose --export screen.png` from an unrelated working directory, with
   STK_BLENDER_DATAFILES / STK_I18N_DIR unset: the fonts and catalogs it reports must be the ones in
   the prefix (found relative to the executable).
3. With --payload: `stk-render --payload DIR --export render.png`.
4. With --python and --repo: writes the fake muFerro run (tests/mupro_fake.py, test data only) and
   runs the e2e preset command `stk-desktop --headless --preset muferro-domains --run RUN --export
   e2e.png --python PY`: the Python bridge must come from PY's environment (`pip install` of the
   repository), not from a source tree. With --golden, e2e.png is compared with it (numpy + Pillow
   from the running interpreter: at most 2 % of the pixels may differ by more than 48).

Prints "INSTALL PASS" or "INSTALL FAIL: ..." and exits 0 / 1.
"""
import argparse
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys


def layout(prefix):
    """Paths of the installed pieces for the platform's layout."""
    app = prefix / "STK.app"
    if app.is_dir():
        res = app / "Contents" / "Resources"
        return {"bin": app / "Contents" / "MacOS", "data": res, "doc": res / "licenses",
                "extra": [app / "Contents" / "Info.plist", res / "stk-desktop.icns"]}
    exe = ".exe" if os.name == "nt" else ""
    return {"bin": prefix / "bin", "data": prefix / "share" / "stk-desktop", "doc": prefix / "share" / "doc" / "stk-desktop",
            "extra": [], "exe": exe}


def within(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def run(cmd, cwd, env, timeout=900):
    print("$", " ".join(str(c) for c in cmd), flush=True)
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    sys.stdout.write(r.stdout)
    sys.stdout.write(r.stderr[-4000:])
    return r


def compare(out, golden):
    import numpy as np
    from PIL import Image
    a = np.asarray(Image.open(out).convert("RGBA"), dtype=np.int16)
    b = np.asarray(Image.open(golden).convert("RGBA"), dtype=np.int16)
    if a.shape != b.shape:
        return f"size {a.shape[1]}x{a.shape[0]} != golden {b.shape[1]}x{b.shape[0]}"
    frac = float((np.abs(a - b).max(axis=2) > 48).mean())
    print(f"golden: {frac * 100:.3f} % of the pixels differ by more than 48")
    return None if frac <= 0.02 else f"{frac * 100:.2f} % of the pixels differ from {golden}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--backend", default="")
    ap.add_argument("--payload")
    ap.add_argument("--python")
    ap.add_argument("--repo")
    ap.add_argument("--golden")
    args = ap.parse_args()
    # The programs run from the work directory: make every given path absolute first.
    for name in ("payload", "repo", "golden"):
        if getattr(args, name):
            setattr(args, name, str(Path(getattr(args, name)).resolve()))
    prefix = Path(args.prefix).resolve()
    work = Path(args.workdir).resolve()
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    lay = layout(prefix)
    exe = lay.get("exe", "")
    desktop, render = lay["bin"] / f"stk-desktop{exe}", lay["bin"] / f"stk-render{exe}"
    errors = []

    required = [desktop, render, lay["data"] / "datafiles" / "fonts" / "Inter.woff2",
                lay["data"] / "datafiles" / "fonts" / "Noto Sans CJK Regular.woff2",
                lay["data"] / "datafiles" / "fonts" / "DejaVuSansMono.woff2",
                lay["data"] / "i18n" / "zh_CN.json", lay["data"] / "i18n" / "en.json",
                lay["doc"] / "LICENSE", lay["doc"] / "THIRD-PARTY-NOTICES.md",
                lay["doc"] / "blender" / "license.md", lay["doc"] / "blender" / "spdx" / "OFL-1.1.txt",
                lay["doc"] / "third-party" / "nlohmann_json-LICENSE.MIT", lay["doc"] / "third-party" / "libspng-LICENSE",
                lay["doc"] / "third-party" / "miniz-LICENSE"] + lay["extra"]
    errors += [f"missing {p.relative_to(prefix)}" for p in required if not p.exists()]
    if platform.system() == "Linux" and desktop.exists():
        for binary in (desktop, render):
            r = subprocess.run(["ldd", str(binary)], capture_output=True, text=True)
            missing = [line.strip() for line in r.stdout.splitlines() if "not found" in line]
            errors += [f"{binary.name}: {m}" for m in missing]
            bundled = [line.split("=>")[1].split("(")[0].strip() for line in r.stdout.splitlines()
                       if "=>" in line and within(line.split("=>")[1].split("(")[0].strip() or "/", prefix)]
            print(f"{binary.name}: bundled libraries used: {', '.join(Path(b).name for b in bundled) or 'none'}")
    if errors:
        print("INSTALL FAIL: " + "; ".join(errors))
        return 1

    env = dict(os.environ)
    for key in ("STK_BLENDER_DATAFILES", "STK_I18N_DIR", "PYTHONPATH", "STK_DESKTOP_BRIDGE_DIR", "STK_RUNTIME_URL",
                "STK_RUNTIME_TOKEN"):
        env.pop(key, None)
    env["XDG_CONFIG_HOME"] = str(work / "config")
    env["XDG_CACHE_HOME"] = str(work / "cache")
    backend = ["--gpu-backend", args.backend] if args.backend else []

    # 2. The application screen, from an unrelated working directory.
    r = run([desktop, "--headless", "--verbose", "--lang", "en", "--size", "960x600", *backend,
             "--export", work / "screen.png"], cwd=work, env=env, timeout=300)
    report = dict(line.split(": ", 1) for line in r.stdout.splitlines() if line.startswith(("fonts: ", "i18n: ")))
    if r.returncode != 0 or not (work / "screen.png").is_file():
        errors.append(f"stk-desktop --headless exited {r.returncode}")
    for key, root in (("fonts", lay["data"] / "datafiles"), ("i18n", lay["data"] / "i18n")):
        if key not in report or not within(report[key], root):
            errors.append(f"{key} not taken from the prefix: {report.get(key, '(not reported)')}")

    # 3. stk-render.
    if args.payload:
        r = run([render, "--payload", args.payload, *backend, "--export", work / "render.png"], cwd=work, env=env, timeout=300)
        if r.returncode != 0 or not (work / "render.png").is_file():
            errors.append(f"stk-render exited {r.returncode}")

    # 4. The e2e preset command through the Python bridge of --python.
    if args.python and args.repo:
        run_dir = work / "run"
        fixture_env = dict(env, PYTHONPATH=str(Path(args.repo) / "tests"))
        r = run([args.python, "-c", "import sys; from pathlib import Path; from mupro_fake import write_domain_run; "
                 "write_domain_run(Path(sys.argv[1]), grid=(16, 12, 10), steps=2, interval=1)",
                 run_dir], cwd=work, env=fixture_env, timeout=300)
        if r.returncode != 0:
            errors.append("cannot write the fake muFerro run")
        else:
            out = work / "e2e.png"
            denv = dict(env, STK_GRAPH_CACHE=str(work / "graph-cache"), MPLCONFIGDIR=str(work / "mpl"),
                        STK_PROFILES_FILE=str(work / "profiles" / "connections.json"), STK_STATE_DIR=str(work / "no-runtime"))
            r = run([desktop, "--headless", *backend, "--preset", "muferro-domains", "--run", run_dir, "--export", out,
                     "--size", "800x600", "--state-dir", work / "bridge", "--python", args.python], cwd=work, env=denv)
            if r.returncode != 0 or not out.is_file():
                errors.append(f"e2e preset export exited {r.returncode}")
            elif args.golden:
                problem = compare(out, args.golden)
                if problem:
                    errors.append(problem)
    if errors:
        print("INSTALL FAIL: " + "; ".join(errors))
        return 1
    print("INSTALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
