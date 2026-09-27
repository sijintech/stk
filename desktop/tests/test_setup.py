# SPDX-License-Identifier: GPL-2.0-or-later
"""Setup orchestration checks; run with Python's stdlib unittest on any CI host."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("desktop_setup", Path(__file__).resolve().parents[1] / "setup.py")
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


class SetupTests(unittest.TestCase):
    def test_windows_sdk_requires_headers_libraries_and_resource_compiler(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Windows Kits"
            def install(version):
                for name in (f"Include/{version}/um/Windows.h", f"Include/{version}/ucrt/stdio.h",
                             f"Lib/{version}/um/x64/kernel32.lib", f"Lib/{version}/ucrt/x64/ucrt.lib",
                             f"bin/{version}/x64/rc.exe"):
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.touch()
            install("10.0.9999.0")
            install("10.0.26100.0")
            self.assertEqual(setup.windows_sdk([root]), (root, "10.0.26100.0"))
            (root / "bin/10.0.26100.0/x64/rc.exe").unlink()
            self.assertEqual(setup.windows_sdk([root]), (root, "10.0.9999.0"))
            (root / "Lib/10.0.9999.0/ucrt/x64/ucrt.lib").unlink()
            with self.assertRaisesRegex(setup.SetupError, "Windows SDK"):
                setup.windows_sdk([root])

    def test_windows_prerequisites_select_one_vs2022_instance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vswhere = root / "Microsoft Visual Studio/Installer/vswhere.exe"
            vswhere.parent.mkdir(parents=True)
            vswhere.touch()
            runner = setup.Runner(False, root)
            instance = str(root / "Visual Studio 2022")
            with patch.dict(os.environ, {"ProgramFiles(x86)": str(root)}), \
                    patch.object(shutil, "which", return_value="git"), \
                    patch.object(runner, "run", return_value=instance + "\n") as run, \
                    patch.object(setup, "windows_sdk_roots", return_value=[root]), \
                    patch.object(setup, "windows_sdk", return_value=(root, "10.0.26100.0")), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(setup.prerequisites(runner, "windows"), instance)
                self.assertIn("-latest", run.call_args.args[0])
                self.assertIn("-utf8", run.call_args.args[0])
                self.assertEqual(runner.env["VCPKG_VISUAL_STUDIO_PATH"], instance)
                run.return_value = ""
                with self.assertRaisesRegex(setup.SetupError, r"C\+\+ tools were not found"):
                    setup.prerequisites(runner, "windows")

    def test_check_only_never_installs_builds_or_launches(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = setup.parser().parse_args(["--check", "--work-dir", tmp])
            with patch.object(setup, "prerequisites") as check, \
                    patch.object(subprocess, "Popen", side_effect=AssertionError("unexpected command")), \
                    contextlib.redirect_stdout(io.StringIO()) as out:
                setup.setup(args, system="Windows", machine="AMD64")
            check.assert_called_once()
            self.assertIn("Prerequisites ready", out.getvalue())
            self.assertFalse((Path(tmp) / "venv").exists())
            with patch.object(setup, "prerequisites", side_effect=setup.SetupError("missing SDK")), \
                    contextlib.redirect_stdout(io.StringIO()) as out:
                with self.assertRaisesRegex(setup.SetupError, "missing SDK"):
                    setup.setup(args, system="Windows", machine="AMD64")
            self.assertNotIn("Prerequisites ready", out.getvalue())

    def test_32bit_python_fails_before_preparing_windows_build(self):
        with patch.object(sys, "maxsize", 2**31 - 1), \
                patch.object(setup.Runner, "mkdir", side_effect=AssertionError("unexpected write")), \
                self.assertRaisesRegex(setup.SetupError, "32-bit interpreter"):
            setup.setup(setup.parser().parse_args([]), system="Windows", machine="AMD64")

    def test_windows_configuration_uses_checked_visual_studio(self):
        calls = []
        class RecordingRunner(setup.Runner):
            def run(self, args, **kwargs):
                calls.append([str(a) for a in args])
                return ""
        with patch.object(setup, "prerequisites", return_value="C:/Visual Studio/2022"), \
                contextlib.redirect_stdout(io.StringIO()):
            setup.setup(setup.parser().parse_args(["--dry-run", "--platform", "windows"]),
                        runner_factory=RecordingRunner)
        config = next(c for c in calls if "-G" in c)
        self.assertIn("-DCMAKE_GENERATOR_INSTANCE=C:/Visual Studio/2022", config)

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell integration")
    def test_windows_wrapper_forwards_paths_and_exit_codes(self):
        script = Path(__file__).resolve().parents[1] / "setup-windows.ps1"
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "Chinese-测试 & spaces"
            for explicit in (False, True):
                env = os.environ.copy()
                env.pop("STK_SETUP_PYTHON", None)
                if explicit:
                    env["STK_SETUP_PYTHON"] = sys.executable
                result = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                                         "-File", str(script), "--dry-run", "--work-dir", str(work),
                                         "--demo", "--", "--lang", "en"], env=env,
                                        capture_output=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(b"--gpu-backend opengl", result.stdout)
                self.assertIn(b"--lang en", result.stdout)
                self.assertFalse(work.exists())
            result = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                                     "-File", str(script), "--jobs", "0"], env=env,
                                    capture_output=True, timeout=60)
            self.assertNotEqual(result.returncode, 0)

    def test_native_architectures_and_unsupported_hosts(self):
        self.assertEqual(setup.target("Darwin", "arm64"), ("macos", "arm64", "arm64-osx", "metal"))
        self.assertEqual(setup.target("Darwin", "x86_64")[2], "x64-osx")
        self.assertEqual(setup.target("Windows", "AMD64")[2:], ("x64-windows", "opengl"))
        for host, arch in (("Linux", "x86_64"), ("Windows", "ARM64"), ("Darwin", "i386")):
            with self.assertRaises(setup.SetupError):
                setup.target(host, arch)

    def test_dry_runs_are_side_effect_free(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "build with spaces & symbols"
            for host, arch in (("macos", "arm64"), ("macos", "x64"), ("windows", "x64")):
                args = setup.parser().parse_args(["--dry-run", "--platform", host, "--arch", arch,
                                                  "--work-dir", str(work), "--demo", "--", "--lang", "en"])
                with patch.object(subprocess, "Popen", side_effect=AssertionError("dry-run executed a command")), \
                        contextlib.redirect_stdout(io.StringIO()) as out:
                    setup.setup(args)
                text = out.getvalue()
                self.assertIn(setup.VCPKG_COMMIT, text)
                self.assertIn("--target stk-desktop", text)
                self.assertIn("--lang en", text)
                self.assertIn("muferro_domains.stkp", text)
                self.assertIn("--python", text)
                self.assertFalse(work.exists())

    def test_platform_override_cannot_execute_on_other_host(self):
        with self.assertRaisesRegex(setup.SetupError, "dry-run only"):
            setup.setup(setup.parser().parse_args(["--platform", "windows"]))

    def test_launch_only_does_not_bootstrap_or_compile(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            setup.setup(setup.parser().parse_args(["--dry-run", "--platform", "windows", "--launch-only"]))
        self.assertNotIn("pip install", out.getvalue())
        self.assertNotIn("git init", out.getvalue())
        self.assertNotIn("cmake.exe", out.getvalue())
        self.assertIn("stk-desktop.exe", out.getvalue())

    def test_no_launch_does_not_execute_app(self):
        calls = []

        class RecordingRunner(setup.Runner):
            def run(self, args, **kwargs):
                calls.append([str(a) for a in args])
                return ""

        args = setup.parser().parse_args(["--dry-run", "--platform", "macos", "--no-launch"])
        with contextlib.redirect_stdout(io.StringIO()):
            setup.setup(args, runner_factory=RecordingRunner)
        self.assertFalse(any(Path(c[0]).name == "stk-desktop" for c in calls))
        self.assertEqual(calls[-1][-2:], ["--target", "stk-desktop"])
        self.assertTrue(any("-DCMAKE_OSX_DEPLOYMENT_TARGET=13.3" in c for c in calls))
        self.assertTrue(any("freetype[core,brotli,zlib]" in c for c in calls))

    def test_runner_preserves_literal_arguments_and_reports_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = setup.Runner(False, Path(tmp))
            self.assertEqual(runner.env["PYTHONUTF8"], "1")
            self.assertEqual(runner.env["PYTHONIOENCODING"], "utf-8")
            literal = 'a path with spaces & percent% and "quotes"'
            with contextlib.redirect_stdout(io.StringIO()):
                result = runner.run([sys.executable, "-c", "import sys; print(sys.argv[1])", literal], capture=True)
                self.assertEqual(result.strip(), literal)
                with self.assertRaisesRegex(setup.SetupError, r"Command failed \(7\)"):
                    runner.run([sys.executable, "-c", "raise SystemExit(7)"])
            self.assertTrue((Path(tmp) / "setup.log").is_file())

    def test_build_failure_does_not_launch(self):
        calls = []

        class FailingRunner(setup.Runner):
            def run(self, args, **kwargs):
                calls.append([str(a) for a in args])
                if "--build" in args:
                    raise setup.SetupError("build failed")
                return ""

        args = setup.parser().parse_args(["--dry-run", "--platform", "windows"])
        with self.assertRaisesRegex(setup.SetupError, "build failed"):
            setup.setup(args, runner_factory=FailingRunner)
        self.assertFalse(any(Path(c[0]).name == "stk-desktop.exe" for c in calls))

    def test_missing_launch_outputs_fail_without_installing(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = setup.parser().parse_args(["--work-dir", tmp, "--launch-only"])
            with patch.object(subprocess, "Popen", side_effect=AssertionError("unexpected install")), \
                    self.assertRaisesRegex(setup.SetupError, "without --launch-only"):
                setup.setup(args, system="Darwin", machine="arm64")


if __name__ == "__main__":
    unittest.main()
