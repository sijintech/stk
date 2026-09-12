# SPDX-FileCopyrightText: 2026 STK Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run with the STK binary: --background --app-template STK --python this_file."""
import json
import os
from pathlib import Path

import bpy

assert hasattr(bpy.types, "SpaceSTK"), "Native editor was not linked"
assert hasattr(bpy.types, "STK_OT_dispatch"), "STK template did not register its command bridge"
areas = [a for w in bpy.context.window_manager.windows for a in w.screen.areas if a.type == "STK"]
assert areas, "STK template did not activate the native editor"
root = Path(os.environ["STK_BLENDER_STATE_DIR"])
body = {"kind": "select", "payload": {"node_id": "a" * 32}}
assert bpy.ops.stk.dispatch(body=json.dumps(body)) == {"FINISHED"}
commands = [json.loads(p.read_text(encoding="utf-8")) for p in (root / "commands").glob("*.json")]
assert any(c["kind"] == "select" and c["payload"] == body["payload"] for c in commands)
assert all(len(c["id"]) == 32 for c in commands)
bpy.ops.wm.save_as_mainfile(filepath=str(root / "smoke.blend"))
bpy.ops.wm.open_mainfile(filepath=str(root / "smoke.blend"))
assert any(a.type == "STK" for w in bpy.context.window_manager.windows for a in w.screen.areas)
print("STK_NATIVE_SMOKE_PASSED: editor registration, queue, save/load")
