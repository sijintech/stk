#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Child failures must remain visible after an apparent successful smoke report."""

import subprocess
import signal
import sys
import unittest
from pathlib import Path


class CommandExitTests(unittest.TestCase):
    def run_child(self, source, timeout=5):
        # An outer process captures the real child's inherited stdout together with
        # the runner's diagnostics, including failures during process shutdown.
        driver = (
            "import os, sys; from run_with_display import run_command; "
            f"sys.exit(run_command(sys.argv[1:], dict(os.environ), {timeout!r}))"
        )
        return subprocess.run(
            [sys.executable, "-c", driver, sys.executable, "-c", source],
            cwd=Path(__file__).resolve().parent,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10,
        )

    def test_success_preserves_output_and_does_not_invent_pass(self):
        result = self.run_child("print('finished')")
        self.assertEqual(result.returncode, 0)
        self.assertIn("finished", result.stdout)
        self.assertIn("command exit status: 0", result.stdout)
        self.assertNotIn("PASS", result.stdout)
        self.assertNotIn("FAIL", result.stdout)

    def test_pass_before_nonzero_exit_is_still_an_explicit_failure(self):
        result = self.run_child("import sys; print('PASS', flush=True); sys.exit(3)")
        self.assertEqual(result.returncode, 3)
        self.assertIn("PASS", result.stdout)
        self.assertIn("FAIL: command exited with status 3", result.stdout)

    def test_pass_before_signal_is_still_an_explicit_failure(self):
        result = self.run_child(
            "import os, signal; print('PASS', flush=True); "
            "os.kill(os.getpid(), signal.SIGTERM)"
        )
        self.assertEqual(result.returncode, 256 - int(signal.SIGTERM))
        self.assertIn("PASS", result.stdout)
        self.assertIn("FAIL: command terminated by signal 15 (SIGTERM)", result.stdout)

    def test_skip_keeps_its_distinct_status(self):
        result = self.run_child("import sys; print('SKIP: no display'); sys.exit(77)")
        self.assertEqual(result.returncode, 77)
        self.assertIn("command exit status: 77", result.stdout)
        self.assertNotIn("FAIL", result.stdout)

    def test_unnamed_realtime_signal_is_an_explicit_failure(self):
        number = int(signal.SIGRTMIN) + 1
        result = self.run_child(
            f"import os; print('PASS', flush=True); os.kill(os.getpid(), {number})"
        )
        self.assertEqual(result.returncode, 256 - number)
        self.assertIn(f"FAIL: command terminated by signal {number} (unnamed)", result.stdout)

    def test_timeout_is_an_explicit_failure(self):
        result = self.run_child("import time; time.sleep(10)", 0.5)
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL: command timed out after 0.5 s", result.stdout)


if __name__ == "__main__":
    unittest.main()
