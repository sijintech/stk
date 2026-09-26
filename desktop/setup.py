#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Prepare a local desktop development build and launch its main window (macOS/Windows)."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys

# Official vcpkg 2026.07.29: keep the bootstrap tool and port recipes on the same revision.
VCPKG_COMMIT = "9e593bb18ea69cc5095e012465dcd675a822ed0d"
VCPKG_URL = "https://github.com/microsoft/vcpkg.git"
REPO = Path(__file__).resolve().parent.parent


class SetupError(RuntimeError):
    pass


class Runner:
    def __init__(self, dry_run: bool, work: Path):
        self.dry_run = dry_run
        self.work = work
        self.env = os.environ.copy()

    def mkdir(self, path: Path):
        if not self.dry_run:
            path.mkdir(parents=True, exist_ok=True)

    def run(self, args, *, cwd=REPO, capture=False):
        args = [str(a) for a in args]
        print("+ " + (subprocess.list2cmdline(args) if os.name == "nt" else shlex.join(args)), flush=True)
        if self.dry_run:
            return ""
        # Argument lists throughout; no shell expansion of user paths or application arguments.
        with (self.work / "setup.log").open("a", encoding="utf-8") as log:
            log.write("\n+ " + repr(args) + "\n")
            log.flush()
            with subprocess.Popen(args, cwd=cwd, env=self.env, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace") as proc:
                output = []
                try:
                    for line in proc.stdout:
                        log.write(line)
                        log.flush()
                        if capture:
                            output.append(line)
                        else:
                            print(line, end="", flush=True)
                    code = proc.wait()
                except KeyboardInterrupt:
                    proc.terminate()
                    raise
        if code:
            if capture:
                print("".join(output), end="", flush=True)
            raise SetupError(f"Command failed ({code}). See {self.work / 'setup.log'}")
        return "".join(output)


def target(system: str, machine: str):
    if system == "Windows":
        if machine.lower() not in ("amd64", "x86_64", "x64"):
            raise SetupError("Windows builds currently need x64 Windows and x64 Python.")
        return "windows", "x64", "x64-windows", "opengl"
    if system == "Darwin":
        if machine.lower() in ("arm64", "aarch64"):
            return "macos", "arm64", "arm64-osx", "metal"
        if machine.lower() in ("x86_64", "amd64", "x64"):
            return "macos", "x64", "x64-osx", "metal"
    raise SetupError("This quick setup supports macOS and x64 Windows. Linux: see desktop/README.md.")


def prerequisites(runner: Runner, system: str):
    if runner.dry_run:
        return
    if not shutil.which("git"):
        raise SetupError("Install Git, reopen your terminal and run setup again.")
    if system == "macos":
        if not shutil.which("xcodebuild"):
            raise SetupError("Install Xcode 16 or newer, select it with xcode-select, and finish its first launch.")
        version = runner.run(["xcodebuild", "-version"], capture=True)
        match = re.search(r"Xcode (\d+)", version)
        if not match or int(match[1]) < 16:
            raise SetupError("Select a full Xcode 16+ installation (Command Line Tools alone are insufficient).")
        runner.run(["xcrun", "--find", "clang++"], capture=True)
    else:
        vswhere = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / \
            "Microsoft Visual Studio/Installer/vswhere.exe"
        if not vswhere.is_file():
            raise SetupError("Install Visual Studio 2022 / Build Tools with Desktop development with C++ and a Windows SDK.")
        found = runner.run([vswhere, "-version", "[17.0,18.0)", "-products", "*", "-requires",
                            "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"], capture=True)
        if not found.strip():
            raise SetupError("Visual Studio 2022 C++ tools were not found. Add the Desktop development with C++ workload.")


def setup(args, *, repo=REPO, system=None, machine=None, runner_factory=Runner):
    system_name = system or platform.system()
    machine_name = machine or platform.machine()
    if args.platform:
        if not args.dry_run:
            raise SetupError("--platform is for --dry-run only; real builds use the current host.")
        system_name = "Darwin" if args.platform == "macos" else "Windows"
        machine_name = args.arch or ("arm64" if args.platform == "macos" else "AMD64")
    elif args.arch:
        raise SetupError("--arch requires --dry-run --platform.")
    kind, arch, triplet, backend = target(system_name, machine_name)
    work = Path(args.work_dir).expanduser().resolve() if args.work_dir else repo / "desktop" / f"build-dev-{kind}-{arch}"
    build = work / "build"
    venv = work / "venv"
    scripts = venv / ("Scripts" if kind == "windows" else "bin")
    python = scripts / ("python.exe" if kind == "windows" else "python")
    cmake = scripts / ("cmake.exe" if kind == "windows" else "cmake")
    exe = build / "bin" / "Release" / "stk-desktop.exe" if kind == "windows" else build / "bin/stk-desktop"
    runner = runner_factory(args.dry_run, work)
    runner.mkdir(work)
    # Keep vcpkg DLLs/tools, the bridge and its worker in the same prepared environment.
    vcpkg = work / f"vcpkg-{VCPKG_COMMIT[:12]}"
    binary_cache = work / "vcpkg-cache"
    runner.env["VCPKG_ROOT"] = str(vcpkg)
    runner.env["VCPKG_DEFAULT_BINARY_CACHE"] = str(binary_cache)
    runner.env["VCPKG_DISABLE_METRICS"] = "1"
    runner.env.pop("VCPKG_OVERLAY_TRIPLETS", None)
    paths = [str(scripts)]
    if kind == "windows":
        paths.append(str(vcpkg / "installed" / triplet / "bin"))
    runner.env["PATH"] = os.pathsep.join(paths + [runner.env.get("PATH", "")])

    if not args.launch_only:
        prerequisites(runner, kind)
        if not python.is_file():
            runner.run([sys.executable, "-m", "venv", venv], cwd=repo)
        # No global Python/tool install and no legacy Qt extras.
        runner.run([python, "-m", "pip", "install", "--disable-pip-version-check", "-e",
                    f"{repo}[science,visualization,control]", "cmake>=3.24,<4", "ninja>=1.11,<2"], cwd=repo)
        runner.run([python, "-c", "import numpy, vtk, suan.desktop_bridge; print('STK Python bridge dependencies ready')"], cwd=repo)
        runner.mkdir(binary_cache)
        if not (vcpkg / ".git").is_dir():
            if not runner.dry_run and vcpkg.exists() and any(vcpkg.iterdir()):
                raise SetupError(f"Refusing to replace an unrelated directory: {vcpkg}")
            runner.run(["git", "init", vcpkg], cwd=repo)
            runner.run(["git", "-C", vcpkg, "fetch", "--depth", "1", VCPKG_URL, VCPKG_COMMIT], cwd=repo)
            runner.run(["git", "-C", vcpkg, "checkout", "--detach", "FETCH_HEAD"], cwd=repo)
        revision = runner.run(["git", "-C", vcpkg, "rev-parse", "HEAD"], capture=True)
        if not runner.dry_run and revision.strip() != VCPKG_COMMIT:
            raise SetupError(f"Unexpected vcpkg revision in {vcpkg}; use a new --work-dir.")
        tool = vcpkg / ("vcpkg.exe" if kind == "windows" else "vcpkg")
        if not tool.is_file():
            # The Windows command is constant; the dynamic checkout path is passed as cwd,
            # avoiding cmd.exe expansion of spaces, percent signs or shell metacharacters.
            runner.run(["cmd.exe", "/d", "/c", "bootstrap-vcpkg.bat -disableMetrics"] if kind == "windows"
                       else ["bash", "bootstrap-vcpkg.sh", "-disableMetrics"], cwd=vcpkg)
        packages = ["freetype[core,brotli,zlib]", "fmt", "eigen3", "zstd", "zlib"]
        config = [cmake, "-S", repo / "desktop", "-B", build,
                  f"-DCMAKE_TOOLCHAIN_FILE={vcpkg / 'scripts/buildsystems/vcpkg.cmake'}",
                  f"-DVCPKG_TARGET_TRIPLET={triplet}", "-DCMAKE_BUILD_TYPE=Release",
                  "-DSTK_DESKTOP_BUILD_SPIKE=OFF", "-DSTK_UI_BUILD_GALLERY=OFF",
                  f"-DSTK_BRIDGE_TEST_PYTHON={python}", f"-DSTK_APP_TEST_PYTHON={python}"]
        if kind == "macos":
            overlay = work / "triplets"
            runner.mkdir(overlay)
            if not runner.dry_run:
                (overlay / f"{triplet}.cmake").write_text(
                    f"set(VCPKG_TARGET_ARCHITECTURE {arch})\n"
                    "set(VCPKG_CRT_LINKAGE dynamic)\nset(VCPKG_LIBRARY_LINKAGE static)\n"
                    "set(VCPKG_CMAKE_SYSTEM_NAME Darwin)\n"
                    f"set(VCPKG_OSX_ARCHITECTURES {'arm64' if arch == 'arm64' else 'x86_64'})\n"
                    "set(VCPKG_OSX_DEPLOYMENT_TARGET 13.3)\n", encoding="utf-8")
            runner.env["VCPKG_OVERLAY_TRIPLETS"] = str(overlay)
            config += ["-G", "Ninja", f"-DCMAKE_OSX_ARCHITECTURES={'arm64' if arch == 'arm64' else 'x86_64'}",
                       "-DCMAKE_OSX_DEPLOYMENT_TARGET=13.3", "-DSTK_GPU_METAL=ON", "-DSTK_GPU_VULKAN=OFF"]
        else:
            packages += ["libepoxy", "pthreads"]
            config += ["-G", "Visual Studio 17 2022", "-A", "x64", "-DSTK_GPU_VULKAN=OFF"]
        runner.run([tool, "install", "--triplet", triplet, *packages], cwd=work)
        runner.run(config, cwd=repo)
        runner.run([cmake, "--build", build, "--config", "Release", "--parallel", str(args.jobs),
                    "--target", "stk-desktop"], cwd=repo)

    if not runner.dry_run and (not exe.is_file() or not python.is_file()):
        raise SetupError("The application or its Python environment is missing. Run setup without --launch-only first.")
    print(f"\nDesktop: {exe}\nPython:  {python}\nLog:     {work / 'setup.log'}", flush=True)
    if args.no_launch:
        return
    launch = [exe, "--python", python, "--gpu-backend", backend]
    if args.demo:
        launch += ["--open", repo / "desktop/tests/viewer/fixtures/muferro_domains.stkp"]
    app_args = args.app_args[1:] if args.app_args[:1] == ["--"] else args.app_args
    runner.run(launch + app_args, cwd=repo)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work-dir", help="Dependency, venv and build cache directory (default: desktop/build-dev-PLATFORM-ARCH)")
    p.add_argument("--jobs", type=int, default=min(os.cpu_count() or 2, 8), help="Parallel compiler jobs (default: at most 8)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--no-launch", action="store_true", help="Prepare and compile without opening a window")
    mode.add_argument("--launch-only", action="store_true", help="Open the previously built application without installing or compiling")
    p.add_argument("--demo", action="store_true", help="Open the included domain payload for a quick GPU check")
    p.add_argument("--dry-run", action="store_true", help="Print commands without installing, compiling or writing files")
    p.add_argument("--platform", choices=("macos", "windows"), help="Preview another platform with --dry-run")
    p.add_argument("--arch", choices=("arm64", "x64"), help="Architecture for --dry-run --platform")
    p.add_argument("app_args", nargs=argparse.REMAINDER, help="Arguments after -- are passed to stk-desktop")
    return p


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    if args.jobs < 1:
        p.error("--jobs must be positive")
    if not (3, 10) <= sys.version_info[:2] < (3, 15):
        p.error("Use Python 3.10–3.14 (Python 3.12 recommended).")
    try:
        setup(args)
    except (SetupError, OSError) as exc:
        print(f"Setup failed: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nSetup interrupted. Re-run the same command to reuse the cache.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
