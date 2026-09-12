# SPDX-FileCopyrightText: 2026 STK Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Real-window smoke and fixed-scene redraw measurement, with simulated input.

Use --enable-event-simulate --python this_file and STK_TEST_OUTPUT. Inspect
report.json: a Blender process exit alone is not evidence of a passing test.
This tests committed Unicode text, NOT a platform IME's composition window.
"""
import json
import os
from pathlib import Path
import time
import traceback
import struct
import zlib
import hashlib
import sys

import bpy
import gpu

root = Path(os.environ["SYNORDER_BLENDER_STATE_DIR"])
output = Path(os.environ["STK_TEST_OUTPUT"])
output.mkdir(parents=True, exist_ok=True)
report = {"status": "running", "ime_composition_tested": False}
stage = 0
frame = None
benchmarking = False
pending_events = []
initial_commands = {p.name for p in (root / "commands").glob("*.json")}
captures = {}
draw_count = 0
idle_start = None


def observe():
    global frame, draw_count
    draw_count += 1
    if benchmarking:
        return
    if "first_display_seconds" not in report and os.environ.get("STK_TEST_STARTED_MONOTONIC"):
        report["first_display_seconds"] = time.monotonic()-float(os.environ["STK_TEST_STARTED_MONOTONIC"])
    region = bpy.context.region
    pixels = gpu.state.active_framebuffer_get().read_color(0,0,region.width,region.height,4,0,"UBYTE")
    pixels.dimensions = region.width*region.height*4
    frame = (region.width,region.height,bytes(pixels))


draw_handle = bpy.types.SpaceSynOrder.draw_handler_add(observe, (), "WINDOW", "POST_PIXEL")


def event(window, kind, value="PRESS", **kwargs):
    pending_events.append((window, dict(type=kind, value=value, **kwargs)))


def pump():
    # Give Blender its normal event/draw cycle between input transitions.
    # Enqueuing an entire gesture at once bypasses hover/focus redraws.
    if pending_events:
        window, kwargs = pending_events.pop(0)
        window.event_simulate(**kwargs)
        return .08
    return step()


def capture(name):
    # Mesa/Xvfb may return an empty front buffer even for upstream editors.
    # Capture the native editor's rendered RGBA buffer without color conversion.
    assert frame is not None, "Native editor did not draw"
    w,h,data = frame
    captures[name] = data
    report.setdefault("frame_sha256", {})[name] = hashlib.sha256(data).hexdigest()
    def chunk(kind, payload):
        return struct.pack("!I",len(payload))+kind+payload+struct.pack("!I",zlib.crc32(kind+payload))
    rows=b"".join(b"\0"+data[y*w*4:(y+1)*w*4] for y in reversed(range(h)))
    png=b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack("!2I5B",w,h,8,6,0,0,0))+chunk(b"IDAT",zlib.compress(rows))+chunk(b"IEND",b"")
    (output / (name + ".png")).write_bytes(png)


def step():
    global stage, benchmarking, idle_start
    try:
        window = bpy.context.window_manager.windows[0]
        areas = [a for a in window.screen.areas if a.type == "SYNORDER"]
        assert len(areas) == 1, "Expected one STK area"
        area = areas[0]
        w, h = area.width, area.height
        report.update(resolution=[window.width, window.height], editor_size=[w, h],
                      renderer=gpu.platform.renderer_get(), vendor=gpu.platform.vendor_get(),
                      graphics_version=gpu.platform.version_get(), blender_version=bpy.app.version_string)
        scale = bpy.context.preferences.system.ui_scale
        row = max(22,int(24*scale))
        report.update(ui_scale=scale, capture_source="native_editor_framebuffer")
        x, y = int(area.x + w*.47), int(area.y + h*.65)
        if stage == 0:
            scene = json.loads((root / "scene.json").read_text(encoding="utf-8"))
            report.update(vertices=len(scene["mesh"]["positions"]), triangles=len(scene["mesh"]["indices"])//3)
            capture("baseline")
            start = time.perf_counter()
            benchmarking = True
            with bpy.context.temp_override(window=window, area=area):
                bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=30)
            benchmarking = False
            elapsed = time.perf_counter()-start
            report.update(redraw_iterations=30, redraw_seconds=elapsed, forced_redraws_per_second=30/elapsed)
            event(window,"MOUSEMOVE","NOTHING",x=x,y=y)
            event(window,"MIDDLEMOUSE",x=x,y=y)
            event(window,"MOUSEMOVE","NOTHING",x=x+85,y=y+40)
            event(window,"MIDDLEMOUSE","RELEASE",x=x+85,y=y+40)
        elif stage == 1:
            capture("rotated")
            changed = sum(a != b for a,b in zip(captures["baseline"], captures["rotated"]))
            assert changed > 30000, "Mouse drag did not rotate the native scientific model"
            report["rotation_changed_channels"] = changed
            split_x = int(area.x+w*.23)
            event(window,"LEFTMOUSE",x=split_x,y=y)
            event(window,"MOUSEMOVE","NOTHING",x=split_x+45,y=y)
            event(window,"LEFTMOUSE","RELEASE",x=split_x+45,y=y)
        elif stage == 2:
            capture("resized")
            changed = sum(a != b for a,b in zip(captures["rotated"], captures["resized"]))
            assert changed > 30000, "Splitter drag did not change the native layout"
            report["resize_changed_channels"] = changed
            tx, ty = int(area.x+w*.72+95), int(area.y+16+2*row+(row-3)/2)
            event(window,"MOUSEMOVE","NOTHING",x=tx,y=ty)
            event(window,"LEFTMOUSE",x=tx,y=ty)
            event(window,"LEFTMOUSE","RELEASE",x=tx,y=ty)
            for char in "中文测试":
                event(window,"A",unicode=char,x=tx,y=ty)
                event(window,"A","RELEASE",x=tx,y=ty)
            event(window,"RET",x=tx,y=ty)
            event(window,"RET","RELEASE",x=tx,y=ty)
        elif stage == 3:
            capture("chinese-input")
            tx, ty = int(area.x+w*.72+95), int(area.y+16+row+(row-3)/2)
            event(window,"MOUSEMOVE","NOTHING",x=tx,y=ty)
            event(window,"LEFTMOUSE",x=tx,y=ty)
            event(window,"LEFTMOUSE","RELEASE",x=tx,y=ty)
        elif stage == 4:
            commands = [json.loads(p.read_text(encoding="utf-8")) for p in (root/"commands").glob("*.json")
                        if p.name not in initial_commands]
            assert any(c["kind"]=="message.send" and c["payload"]["fields"]["message"]=="中文测试" for c in commands), "Unicode did not pass through native text control and command queue"
            report.update(unicode_commit_and_submit=True, gpu_memory_measured=False)
            idle_start = (time.monotonic(), draw_count)
        else:
            report.update(status="passed", idle_sample_seconds=time.monotonic()-idle_start[0],
                          idle_editor_redraws=draw_count-idle_start[1])
            if sys.platform.startswith("linux"):
                import resource
                report["process_peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            (output/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2), encoding="utf-8")
            bpy.ops.wm.quit_blender()
            return None
        stage += 1
        return 1.2 if stage == 5 else .6
    except Exception:
        report.update(status="failed", error=traceback.format_exc(), stage=stage)
        (output/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2), encoding="utf-8")
        bpy.ops.wm.quit_blender()
        return None


bpy.app.timers.register(pump, first_interval=3)
