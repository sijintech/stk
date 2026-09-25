#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fails when tests that must run on this CI job were skipped, did not run or are missing.

    check_required_tests.py JUNIT.xml REGEX [REGEX ...]

JUNIT.xml is `ctest --output-junit`. Every REGEX (Python `re.fullmatch` on the test name) must match
at least one test, and every matching test must have run and passed: a GTEST_SKIP (ctest
SKIP_REGULAR_EXPRESSION), exit code 77 (SKIP_RETURN_CODE), "Not Run" or a failure all count. CI uses
it so that the Python-backed tests (real bridge, loopback Runtime, e2e golden) cannot silently skip
when the job's Python lacks STK's dependencies.
"""
import re
import sys
import xml.etree.ElementTree as ET


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    cases = {}
    for case in ET.parse(argv[1]).getroot().iter("testcase"):
        name = case.get("name", "")
        status = case.get("status", "")
        if case.find("skipped") is not None:
            status = "skipped"
        elif case.find("failure") is not None or case.find("error") is not None:
            status = "failed"
        cases[name] = status
    bad = []
    for pattern in argv[2:]:
        rx = re.compile(pattern)
        matched = {n: s for n, s in cases.items() if rx.fullmatch(n)}
        if not matched:
            bad.append(f"{pattern}: no such test")
        for name, status in sorted(matched.items()):
            ok = status == "run"
            print(f"{'ok ' if ok else 'BAD'} {name}: {status}")
            if not ok:
                bad.append(f"{name}: {status}")
    if bad:
        print("\nRequired tests did not run and pass:\n  " + "\n  ".join(bad))
        return 1
    print(f"\nall required tests ran ({sum(1 for p in argv[2:] for n in cases if re.fullmatch(p, n))} matched)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
