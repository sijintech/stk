"""Render the browser acceptance run's real scientific result in Synorder Blender."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, "SYNORDER_BLENDER_STATE_DIR": str(args.state.resolve()),
        "STK_TEST_OUTPUT": str(args.output.resolve()), "STK_TEST_STARTED_MONOTONIC": str(time.monotonic())}
    environment.pop("PYTHONPATH", None)
    with (args.output / "blender.log").open("w") as log:
        result = subprocess.run([str(args.blender.resolve()), "--factory-startup", "--app-template", "SynOrder",
            "--enable-event-simulate", "--window-geometry", "0", "0", "1440", "1000", "--python-exit-code", "2",
            "--python", str(Path(__file__).with_name("native_smoke.py").resolve())],
            env=environment, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    report = json.loads((args.output / "report.json").read_text())
    if result.returncode or report.get("status") != "passed":
        raise SystemExit("Native UI check failed; inspect report.json and blender.log")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
