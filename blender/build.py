#!/usr/bin/env python3
"""Prepare, configure and build STK. Upstream libraries must be installed first."""
import argparse
import os
from pathlib import Path
import subprocess
from prepare import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--build-dir", required=True, type=Path)
    parser.add_argument("--clone", action="store_true")
    parser.add_argument("--source-archive", type=Path)
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 2))
    parser.add_argument("--configure-only", action="store_true")
    parser.add_argument("--target", default="install")
    parser.add_argument("cmake_options", nargs="*")
    args = parser.parse_args()
    source = prepare(args.source_dir, args.clone, args.source_archive)
    preview = source / "release/datafiles/preview.blend"
    if not preview.exists() or preview.stat().st_size < 256:
        parser.error("Source assets are missing: pass the checksummed official --source-archive to hydrate Git LFS data")
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    options = ["-DWITH_CYCLES=OFF", "-DWITH_INPUT_IME=ON", "-DWITH_INTERNATIONAL=ON",
               "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"]
    subprocess.run(["cmake", "-S", str(source), "-B", str(args.build_dir),
                    *options, *args.cmake_options], check=True)
    if not args.configure_only:
        subprocess.run(["cmake", "--build", str(args.build_dir), "--target", args.target,
                        "--parallel", str(args.jobs)], check=True)


if __name__ == "__main__":
    main()
