#!/usr/bin/env python3
"""Launch a real STK window and fail if its recorded input checks fail."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from suan.blender_client.scene import demo_scene


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    state = output / "runtime"
    state.mkdir(exist_ok=True, mode=0o700)
    (state / "commands").mkdir(exist_ok=True, mode=0o700)
    (state / "scene.json").write_text(json.dumps(demo_scene(), ensure_ascii=False), encoding="utf-8")
    snapshot = {"status": "离线演示 / 原生界面验证", "selection": {}, "devices": [],
                "actions": [], "artifacts": [], "sessions": [], "session_id": "test-session",
                "messages": [{"role": "assistant", "content": "这是原生工作台测试。中文输入、三维交互和分区调整正在验收。"}],
                "logs": "STK Blender 原生编辑器\n此模型为演示曲面，非计算结果。"}
    (state / "state.json").write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    report_path = output / "report.json"
    report_path.write_text(json.dumps({"status": "launching"}), encoding="utf-8")
    env = {**os.environ, "STK_BLENDER_STATE_DIR": str(state), "STK_TEST_OUTPUT": str(output),
           "STK_TEST_STARTED_MONOTONIC": str(time.monotonic())}
    with (output / "blender.log").open("w") as log:
        result = subprocess.run([str(args.blender.resolve()), "--factory-startup", "--app-template", "STK",
                                 "--enable-event-simulate", "--window-geometry", "0", "0", "1440", "1000",
                                 "--python-exit-code", "2", "--python", str(Path(__file__).with_name("ui_smoke.py").resolve())],
                                env=env, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if result.returncode or report.get("status") != "passed":
        raise SystemExit(f"Native UI verification failed; inspect {report_path} and blender.log")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
