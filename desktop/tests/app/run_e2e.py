#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""End-to-end golden of the desktop viewer (WP10 / WP12).

    run_e2e.py --desktop stk-desktop --compare stk-viewer-image-compare --python PY --repo DIR
               --backend vulkan|opengl --workdir DIR --golden e2e.png --vtk vtk_reference.png [--update]

1. Writes a fake muFerro run (tests/mupro_fake.write_domain_run, 16 x 12 x 10, 2 steps) with PY.
2. Runs `stk-desktop --headless --preset muferro-domains --run <run> --export out.png --size 800x600`
   (the real Python bridge evaluates the preset locally; stk_viewer_gpu renders the payload).
3. Compares out.png with the committed golden (SSIM >= 0.98) and with the offscreen VTK reference
   of the same result (domain mask IoU >= 0.9).

Prints "E2E PASS" or "E2E FAIL"; exit 77 when PY cannot evaluate graphs (no numpy / VTK).
--update (or STK_UPDATE_GOLDENS=1) rewrites the golden from this run.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    ap = argparse.ArgumentParser()
    for name in ("desktop", "compare", "python", "repo", "backend", "workdir", "golden", "vtk"):
        ap.add_argument(f"--{name}", required=True)
    ap.add_argument("--update", action="store_true")
    args = ap.parse_args()
    fixture = Path(args.repo) / "desktop" / "tests" / "bridge" / "bridge_fixture.py"
    env = dict(os.environ, PYTHONPATH=args.repo)
    check = subprocess.run([args.python, str(fixture), "check", "graph"], env=env, capture_output=True, text=True)
    if check.returncode != 0:
        print(f"SKIP: {args.python} cannot evaluate graphs: {check.stdout.strip()} {check.stderr.strip()}")
        return 77
    work = Path(args.workdir)
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    run = work / "run"
    subprocess.run([args.python, str(fixture), "write-run", str(run)], env=env, check=True)
    out = work / "out.png"
    cmd = [args.desktop, "--headless", "--gpu-backend", args.backend, "--preset", "muferro-domains", "--run", str(run),
           "--export", str(out), "--size", "800x600", "--state-dir", str(work / "bridge"), "--python", args.python]
    print("$", " ".join(cmd), flush=True)
    denv = dict(os.environ, STK_GRAPH_CACHE=str(work / "graph-cache"), MPLCONFIGDIR=str(work / "mpl"),
                STK_PROFILES_FILE=str(work / "profiles" / "connections.json"), STK_STATE_DIR=str(work / "no-runtime"))
    for key in ("STK_DESKTOP_BRIDGE_DIR", "STK_RUNTIME_URL", "STK_RUNTIME_TOKEN"):
        denv.pop(key, None)
    result = subprocess.run(cmd, env=denv, capture_output=True, text=True, timeout=900)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr[-4000:])
    if result.returncode != 0 or not out.is_file():
        print(f"E2E FAIL: stk-desktop exited {result.returncode}")
        return 1
    if args.update or os.environ.get("STK_UPDATE_GOLDENS") == "1":
        Path(args.golden).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(out, args.golden)
        print(f"updated {args.golden}")
    ok = True
    golden = subprocess.run([args.compare, str(out), args.golden, "--ssim-min", "0.98"], capture_output=True, text=True)
    print("golden:", golden.stdout.strip())
    ok &= golden.returncode == 0
    vtk = subprocess.run([args.compare, str(out), args.vtk, "--iou-min", "0.9"], capture_output=True, text=True)
    print("VTK reference:", vtk.stdout.strip())
    ok &= vtk.returncode == 0
    # Sequence export: one PNG per step and the stk.series/1 manifest.
    seq = work / "seq" / "domains.png"
    seq.parent.mkdir(parents=True, exist_ok=True)
    cmd = [args.desktop, "--headless", "--gpu-backend", args.backend, "--preset", "muferro-domains", "--run", str(run),
           "--export", str(seq), "--size", "320x240", "--sequence", "--lang", "en", "--state-dir", str(work / "bridge"),
           "--python", args.python]
    result = subprocess.run(cmd, env=denv, capture_output=True, text=True, timeout=900)
    sys.stdout.write(result.stdout)
    manifest = seq.parent / "domains.series.json"
    frames = []
    if result.returncode == 0 and manifest.is_file():
        import json
        doc = json.loads(manifest.read_text(encoding="utf-8"))
        frames = [f["outputs"]["image"] for f in doc.get("frames", [])] if doc.get("schema") == "stk.series/1" else []
    present = [name for name in frames if (seq.parent / name).is_file()]
    print(f"sequence: {len(present)} / {len(frames)} frames ({', '.join(present)})")
    ok &= result.returncode == 0 and len(frames) == 3 and len(present) == 3
    print("E2E PASS" if ok else "E2E FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
