#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Require both native-process success and its evidence marker, using only stdlib.

    check_native_evidence.py --success-marker TEXT --timeout 570 -- PROGRAM ARG...

Do not set CTest PASS_REGULAR_EXPRESSION on this wrapper: that property ignores
ordinary nonzero exit codes. Output is captured together and forwarded after the
child exits. A temporary regular file avoids an inherited pipe keeping timeout
cleanup blocked. Timeout cleanup kills and reaps the direct child only; this is
not a process-tree sandbox or a claim about already detached browser processes.
"""
from __future__ import annotations

import argparse
import math
import os
import re
import subprocess
import sys
import tempfile


MAX_LOG_BYTES = 64 * 1024 * 1024
FAILURE = re.compile(r"FAIL:|leaked|Error:\s*Not freed memory|guarded STK allocations remain", re.IGNORECASE)
FINAL_MEMORY = re.compile(r"guardedalloc:\s*final blocks=(\d+)\s+bytes=(\d+)")


def timeout_seconds(value):
    try:
        seconds = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("timeout must be a positive finite number") from None
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("timeout must be a positive finite number")
    return seconds


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--success-marker", required=True)
    parser.add_argument("--timeout", type=timeout_seconds, default=570)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a native command is required after --")
    if not args.success_marker.strip() or any(c in args.success_marker for c in "\r\n\x00"):
        parser.error("success marker must be nonempty text on one line")

    environment = os.environ.copy()
    environment["STK_TOKEN_PLAN_API_KEY"] = ""
    environment.pop("STK_TOKEN_PLAN_MODEL", None)
    problems = []
    process = None
    try:
        with tempfile.TemporaryFile() as captured:
            try:
                process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                           stdout=captured, stderr=subprocess.STDOUT, env=environment)
                process.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                problems.append(f"native command timed out after {args.timeout:g} seconds")
            except KeyboardInterrupt:
                problems.append("native evidence gate was interrupted")
            except OSError as error:
                problems.append(f"cannot launch or wait for native command ({type(error).__name__})")
            finally:
                if process is not None and process.poll() is None:
                    try:
                        process.kill()
                        process.wait(timeout=5)
                    except (OSError, subprocess.TimeoutExpired) as error:
                        problems.append(f"cannot reap native command ({type(error).__name__})")

            captured.seek(0)
            output = captured.read(MAX_LOG_BYTES + 1)
        if len(output) > MAX_LOG_BYTES:
            problems.append("native output exceeds the 64 MiB evidence-log budget")
            output = output[:MAX_LOG_BYTES]
        sys.stdout.buffer.write(output)
        if output and not output.endswith(b"\n"):
            sys.stdout.buffer.write(b"\n")
        sys.stdout.buffer.flush()
    except (OSError, KeyboardInterrupt) as error:
        print(f"FAIL: native evidence output unavailable ({type(error).__name__})", file=sys.stderr)
        return 1

    if process is not None and process.returncode != 0:
        problems.append(f"native command returned {process.returncode}; required 0")
    text = output.decode("utf-8", errors="replace")
    if args.success_marker not in text:
        problems.append("native success marker is missing")
    if FAILURE.search(text):
        problems.append("native output contains a failure or leak diagnostic")
    if any(int(blocks) != 0 or int(size) != 0 for blocks, size in FINAL_MEMORY.findall(text)):
        problems.append("native final guarded allocation count is nonzero")
    for problem in problems:
        print(f"FAIL: evidence gate: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
