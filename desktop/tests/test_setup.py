# SPDX-License-Identifier: GPL-2.0-or-later
"""Setup orchestration checks; run with Python's stdlib unittest on any CI host."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("desktop_setup", Path(__file__).resolve().parents[1] / "setup.py")
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


class SetupTests(unittest.TestCase):
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
