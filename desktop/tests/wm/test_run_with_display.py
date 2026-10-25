#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Child failures must remain visible after an apparent successful smoke report."""

import subprocess
import signal
import sys
import json
import tempfile
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

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux process metadata and pidfds")
    def test_timeout_stops_other_groups_and_sessions_without_touching_an_unrelated_child(self):
        unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        identities = []
        try:
            with tempfile.TemporaryDirectory() as directory:
                leaf = "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)"
                branch = (
                    "import os,json,subprocess,sys,time; from pathlib import Path; "
                    f"p=subprocess.Popen([sys.executable,'-c',{leaf!r}],start_new_session=True); "
                    "Path(sys.argv[1]).write_text(json.dumps([os.getpid(),p.pid])); time.sleep(30)"
                )
                paths = [str(Path(directory) / str(index)) for index in range(2)]
                source = (
                    "import subprocess,sys,time; "
                    f"subprocess.Popen([sys.executable,'-c',{branch!r},{paths[0]!r}],start_new_session=True); "
                    f"subprocess.Popen([sys.executable,'-c',{branch!r},{paths[1]!r}],process_group=0); "
                    "time.sleep(30)"
                )
                result = self.run_child(source, timeout=2)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("FAIL: command timed out after 2 s", result.stdout)
                for path in paths:
                    identities.extend(json.loads(Path(path).read_text()))
                for pid in identities:
                    path = Path(f"/proc/{pid}/stat")
                    self.assertTrue(not path.exists() or path.read_text().rsplit(")", 1)[1].split()[0] == "Z",
                                    f"owned descendant {pid} is still running")
                self.assertIsNone(unrelated.poll())
        finally:
            unrelated.kill()
            unrelated.wait()


if __name__ == "__main__":
    unittest.main()
