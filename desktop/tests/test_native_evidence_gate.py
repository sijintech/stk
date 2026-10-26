#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Portable CPU checks of the actual evidence CLI and real child exit statuses."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


GATE = Path(__file__).with_name("check_native_evidence.py")
MARKER = "PASS: native evidence public fixture"


class NativeEvidenceGateTests(unittest.TestCase):
    def invoke(self, command, *, timeout=5, environment=None):
        env = os.environ.copy()
        env["STK_TOKEN_PLAN_API_KEY"] = ""
        env.pop("STK_TOKEN_PLAN_MODEL", None)
        if environment:
            env.update(environment)
        return subprocess.run([sys.executable, str(GATE), "--success-marker", MARKER,
                               "--timeout", str(timeout), "--", *command],
                              env=env, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=15)

    def python(self, source, **kwargs):
        return self.invoke([sys.executable, "-c", source], **kwargs)

    def test_zero_with_success_marker_passes(self):
        result = self.python(f"print({MARKER!r})")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(MARKER, result.stdout)

    def test_nonzero_with_same_success_marker_fails(self):
        result = self.python(f"import sys; print({MARKER!r}); sys.exit(7)")
        self.assertEqual(result.returncode, 1)
        self.assertIn(MARKER, result.stdout)
        self.assertIn("returned 7; required 0", result.stderr)

    def test_zero_without_marker_fails(self):
        result = self.python("print('ordinary log')")
        self.assertEqual(result.returncode, 1)
        self.assertIn("success marker is missing", result.stderr)

    def test_failure_diagnostics_cannot_be_overridden_by_success(self):
        for diagnostic in ("FAIL: incomplete evidence", "64 bytes leaked",
                           "Error: Not freed memory blocks: 1",
                           "guarded STK allocations remain after engine static destruction"):
            with self.subTest(diagnostic=diagnostic):
                result = self.python(f"import sys; print({MARKER!r}); print({diagnostic!r}, file=sys.stderr)")
                self.assertEqual(result.returncode, 1)
                self.assertIn("failure or leak diagnostic", result.stderr)

    def test_guarded_final_counts_are_checked_without_rejecting_pre_static_counts(self):
        for blocks, size, expected in ((0, 0, 0), (1, 0, 1), (0, 64, 1)):
            with self.subTest(blocks=blocks, size=size):
                result = self.python(f"print('guardedalloc: 1 live block(s) before engine static destruction; final gate pending'); "
                                     f"print('guardedalloc: final blocks={blocks} bytes={size} after engine static destruction'); "
                                     f"print({MARKER!r})")
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)

    def test_marker_on_stderr_is_captured(self):
        result = self.python(f"import sys; print({MARKER!r}, file=sys.stderr)")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(MARKER, result.stdout)

    def test_timeout_after_success_marker_still_fails(self):
        started = time.monotonic()
        result = self.python(f"import time; print({MARKER!r}, flush=True); time.sleep(60)", timeout=1)
        self.assertEqual(result.returncode, 1)
        self.assertIn(MARKER, result.stdout)
        self.assertIn("timed out", result.stderr)
        self.assertLess(time.monotonic() - started, 10)

    def test_exception_after_success_marker_still_fails(self):
        result = self.python(f"print({MARKER!r}, flush=True); raise RuntimeError('public fixture failure')")
        self.assertEqual(result.returncode, 1)
        self.assertIn("RuntimeError", result.stdout)
        self.assertIn("required 0", result.stderr)

    def test_signal_after_success_marker_still_fails(self):
        result = self.python(f"import os, signal; print({MARKER!r}, flush=True); os.kill(os.getpid(), signal.SIGTERM)")
        self.assertEqual(result.returncode, 1)
        self.assertIn("required 0", result.stderr)

    def test_missing_executable_is_a_failure(self):
        with tempfile.TemporaryDirectory() as root:
            result = self.invoke([str(Path(root) / "missing native executable")])
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot launch", result.stderr)

    def test_child_environment_is_scrubbed_without_printing_values(self):
        # Low-entropy public fixtures only; no real environment value is read into output.
        result = self.python("import os; assert os.environ['STK_TOKEN_PLAN_API_KEY'] == ''; "
                             "assert 'STK_TOKEN_PLAN_MODEL' not in os.environ; "
                             f"print({MARKER!r})",
                             environment={"STK_TOKEN_PLAN_API_KEY": "abcdefghijklmnopqrstu",
                                          "STK_TOKEN_PLAN_MODEL": "public-fixture-model"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("abcdefghijklmnopqrstu", result.stdout + result.stderr)
        self.assertNotIn("public-fixture-model", result.stdout + result.stderr)

    def test_spaced_script_path_and_arguments_remain_separate(self):
        with tempfile.TemporaryDirectory(prefix="native gate public fixture ") as root:
            script = Path(root) / "native child with spaces.py"
            script.write_text("import sys\nassert sys.argv[1:] == ['argument with spaces', '$literal;value']\n"
                              f"print({MARKER!r})\n", encoding="utf-8")
            result = self.invoke([sys.executable, str(script), "argument with spaces", "$literal;value"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
