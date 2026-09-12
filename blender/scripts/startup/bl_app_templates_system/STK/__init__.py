# SPDX-FileCopyrightText: 2026 STK Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bootstrap the compiled STK editor; all workbench drawing lives in C++.

The external suan-blender launcher owns the bridge process. This module imports
only Blender and the standard library, not the solver/VTK environment.
"""
import json
import os
from pathlib import Path
import tempfile
import uuid

import bpy
from bpy.app.handlers import persistent

_last_state = None


def state_root():
    path = os.environ.get("STK_BLENDER_STATE_DIR")
    if not path:
        raise RuntimeError("Start this workbench with suan-blender so a bridge is available")
    root = Path(path)
    (root / "commands").mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


class STK_OT_dispatch(bpy.types.Operator):
    bl_idname = "stk.dispatch"
    bl_label = "STK Operation"
    bl_description = "Queue an immutable operation for the independent control bridge"
    # Deliberately no UNDO/REGISTER: commands and secrets must not enter .blend.
    body: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    def execute(self, context):
        try:
            command = json.loads(self.body)
            if set(command) - {"kind", "payload", "node_id"} or not isinstance(command.get("payload"), dict):
                raise ValueError("Invalid workbench command")
            command["id"] = uuid.uuid4().hex
            root = state_root() / "commands"
            data = json.dumps(command, ensure_ascii=False, allow_nan=False).encode()
            fd, temporary = tempfile.mkstemp(prefix=".command-", dir=root)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, root / (command["id"] + ".json"))
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return {"FINISHED"}
        except (OSError, ValueError, TypeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


@persistent
def configure(_=None):
    if not hasattr(bpy.types, "SpaceSTK"):
        raise RuntimeError("This template requires the STK source build, with SPACE_STK compiled in")
    for window in bpy.context.window_manager.windows:
        # Keep the upstream screen implementation; each screen starts with one
        # dedicated STK area. The C++ editor supplies its own five resizable panes.
        areas = [a for a in window.screen.areas if a.type not in {"TOPBAR", "STATUSBAR"}]
        if areas:
            largest = max(areas, key=lambda a: a.width * a.height)
            largest.type = "STK"
            if not bpy.app.background and len(areas) > 1:
                with bpy.context.temp_override(window=window, area=largest):
                    bpy.ops.screen.screen_full_area(use_hide_panels=True)
    bpy.context.preferences.view.show_splash = False
    if not bpy.app.timers.is_registered(poll):
        bpy.app.timers.register(poll, first_interval=.25, persistent=True)


def poll():
    global _last_state
    try:
        root = state_root()
        stamps = tuple((root / name).stat().st_mtime_ns if (root / name).exists() else 0
                       for name in ("state.json", "scene.json"))
        if stamps != _last_state:
            _last_state = stamps
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == "STK":
                        area.tag_redraw()
    except OSError:
        pass
    return .25


def register():
    bpy.utils.register_class(STK_OT_dispatch)
    bpy.app.handlers.load_post.append(configure)


def unregister():
    if configure in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(configure)
    if bpy.app.timers.is_registered(poll):
        bpy.app.timers.unregister(poll)
    bpy.utils.unregister_class(STK_OT_dispatch)
