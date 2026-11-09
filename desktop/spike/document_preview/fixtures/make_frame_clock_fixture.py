#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Generate and verify the public synthetic frame-clock MP4 for the opt-in Cocoa diagnostic.

``frame-clock-preview.mp4`` keeps the geometry, rate, duration, codecs, encoder flags and
keyframe layout of ``frozen-preview.mp4``: 320x180, 10 fps, 6 s, H.264 Baseline level 3.0
yuv420p, I-frames at frames 0 and 30, and a generated 440 Hz AAC tone. The only added
encoder flag is ``-force_key_frames 3``, which keeps that layout. Frames 0-29 are red and frames 30-59 are blue, so the existing
central red/blue OS-pixel predicate (15-85 % width, 20-65 % height) is unchanged.

Every frame also carries its own ordinal in a luma-only black/white marker in the top-left
band (x 0-200, y 0-32 source pixels), above that central sample region. It stays clear of
the macOS WebKit inline controls seen in earlier own-window captures (bottom bar, and a
top-right volume button in the small HTML layout). The marker has 2 rows x 8 columns of
25x16 source-pixel cells:

* row 0: guard white, ID bits b5..b0 (MSB first), even parity of b5..b0;
* row 1: the exact complement of row 0 in every column (guard black).

Decoders sample only the central half of each cell and require every column to be a
complementary pair. A misread, occluded, blended or shifted cell is ambiguous, never a
different ID. Ordinals 60-63 are invalid. ``reports_native_window.cc`` holds the same layout.

All picture data is computed here; there is no source recording, network or licensed data.
FFmpeg/ffprobe are fixture-generation and verification tools, not product dependencies.
Scratch frames, probes and the verification record go only to ``--evidence-dir``, which
must be outside this repository. Usage::

    make_frame_clock_fixture.py generate --output OUT.mp4 --evidence-dir DIR
    make_frame_clock_fixture.py verify --input frame-clock-preview.mp4 --evidence-dir DIR

``verify`` checks ffprobe stream facts, keyframes, all 60 decoded frame IDs and PTS in order, the
red/blue halves, and the same decoding after bilinear scaling to sizes seen on macOS.
Byte identity of a regenerated file depends on the FFmpeg/libx264 build; the pinned
fixture SHA-256 below and in the C++ diagnostic is the authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

WIDTH, HEIGHT, RATE, FRAMES = 320, 180, 10, 60
CELL_W, CELL_H, COLUMNS = 25, 16, 8
ID_BITS = 6
RED, BLUE = (255, 0, 0), (0, 0, 255)
WHITE, BLACK = (255, 255, 255), (0, 0, 0)
FIXTURE_NAME = "frame-clock-preview.mp4"
# frozen-preview.mp4 has I-frames at 0 and at the red/blue cut (frame 30). The per-frame marker
# hides that scene cut from libx264, so the 3 s keyframe is forced to keep the same GOP layout.
KEYFRAMES = [0, FRAMES // 2]
PINNED_SHA256 = "c2bbcb873b7628c22b512051443adde6ff2e6c8688c6d84f0307d6bab2a34eef"
PINNED_SIZE = 44339
# Picture sizes at which the marker must still decode: the macOS CI standalone MP4
# (about 281x158) and HTML video (207x116) client pixels, their 2x Retina forms and 1x.
SCALED_SIZES = ((320, 180), (207, 116), (281, 158), (414, 233), (562, 316), (640, 360))
REPO = Path(__file__).resolve().parents[4]


def marker_columns(frame: int) -> list[int]:
    """Row-0 values for the eight columns (1 white, 0 black); row 1 is the complement."""
    bits = [(frame >> (ID_BITS - 1 - i)) & 1 for i in range(ID_BITS)]
    return [1, *bits, sum(bits) & 1]


def frame_rgb(frame: int) -> bytes:
    background = RED if frame < FRAMES // 2 else BLUE
    row_bytes = bytes(background) * WIDTH
    pixels = bytearray(row_bytes * HEIGHT)
    columns = marker_columns(frame)
    for row in range(2):
        for column, value in enumerate(columns):
            color = bytes(WHITE if (value if row == 0 else 1 - value) else BLACK)
            for y in range(row * CELL_H, (row + 1) * CELL_H):
                start = (y * WIDTH + column * CELL_W) * 3
                pixels[start:start + CELL_W * 3] = color * CELL_W
    return bytes(pixels)


def classify(pixel: tuple[int, int, int]) -> int | None:
    """Mirror of the C++ cell pixel classifier."""
    low, high = min(pixel), max(pixel)
    if low >= 170 and high - low <= 60:
        return 1
    if high <= 80 and high - low <= 50:
        return 0
    return None


def decode(rgb: bytes, width: int, height: int) -> tuple[int | None, str]:
    """Mirror of the C++ marker decoder for a picture that fills the image."""
    def pixel(x: int, y: int) -> tuple[int, int, int]:
        offset = (y * width + x) * 3
        return rgb[offset], rgb[offset + 1], rgb[offset + 2]

    values = []
    for row in range(2):
        for column in range(COLUMNS):
            left = (column * CELL_W + CELL_W * 0.25) / WIDTH * width
            right = (column * CELL_W + CELL_W * 0.75) / WIDTH * width
            top = (row * CELL_H + CELL_H * 0.25) / HEIGHT * height
            bottom = (row * CELL_H + CELL_H * 0.75) / HEIGHT * height
            counts = [0, 0, 0]
            for y in range(height):
                if not top <= y + 0.5 < bottom:
                    continue
                for x in range(width):
                    if left <= x + 0.5 < right:
                        kind = classify(pixel(x, y))
                        counts[2 if kind is None else kind] += 1
            total = sum(counts)
            if total < 4:
                return None, "cell_too_small"
            if counts[1] >= 0.85 * total:
                values.append(1)
            elif counts[0] >= 0.85 * total:
                values.append(0)
            else:
                return None, "ambiguous_cell"
    top_row, bottom_row = values[:COLUMNS], values[COLUMNS:]
    if any(a == b for a, b in zip(top_row, bottom_row)):
        return None, "complement_mismatch"
    if top_row[0] != 1:
        return None, "guard_mismatch"
    bits = top_row[1:1 + ID_BITS]
    if sum(bits) & 1 != top_row[-1]:
        return None, "parity_mismatch"
    ordinal = 0
    for bit in bits:
        ordinal = ordinal * 2 + bit
    if ordinal >= FRAMES:
        return None, "out_of_range"
    return ordinal, "ok"


def central_color(rgb: bytes, width: int, height: int) -> str:
    """Same region and thresholds as the existing C++ media_capture red/blue predicate."""
    x0, x1 = math.ceil(width * 0.15), math.floor(width * 0.85)
    y0, y1 = math.ceil(height * 0.20), math.floor(height * 0.65)
    red = blue = total = 0
    for y in range(y0, y1, 2):
        for x in range(x0, x1, 2):
            r, g, b = rgb[(y * width + x) * 3:(y * width + x) * 3 + 3]
            total += 1
            red += r >= 120 and r >= g * 2 + 30 and r >= b * 2 + 30
            blue += b >= 120 and b >= r * 2 + 30 and b >= g * 2 + 30
    if red >= 0.80 * total and blue <= 0.05 * total:
        return "red"
    if blue >= 0.80 * total and red <= 0.05 * total:
        return "blue"
    return "neither"


def tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise SystemExit(f"{name} is required to generate or verify the fixture")
    return path


def outside_repo(path: Path) -> Path:
    resolved = path.resolve()
    if resolved == REPO or REPO in resolved.parents:
        raise SystemExit("--evidence-dir must be outside the repository; never write scratch output into it")
    return resolved


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=True, timeout=120, **kwargs)


def generate(output: Path, evidence: Path) -> dict:
    ffmpeg = tool("ffmpeg")
    if output.exists():
        raise SystemExit(f"Refusing to overwrite {output}")
    command = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-n",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{WIDTH}x{HEIGHT}", "-r", str(RATE), "-i", "-",
               "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=6",
               "-map", "0:v", "-map", "1:a",
               "-c:v", "libx264", "-profile:v", "baseline", "-level:v", "3.0", "-pix_fmt", "yuv420p",
               "-force_key_frames", "3",
               "-threads", "1", "-c:a", "aac", "-b:a", "48k", "-movflags", "+faststart",
               "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
               "-metadata", "creation_time=2000-01-01T00:00:00Z", str(output)]
    frames = b"".join(frame_rgb(i) for i in range(FRAMES))
    run(command, input=frames)
    version = run([ffmpeg, "-hide_banner", "-version"], capture_output=True, text=True).stdout.splitlines()[0]
    record = {"command": [Path(command[0]).name, *command[1:-1], output.name], "ffmpeg": version,
              "raw_input_sha256": hashlib.sha256(frames).hexdigest(), "raw_input_frames": FRAMES}
    (evidence / "generate.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def verify(path: Path, evidence: Path, pinned: bool) -> dict:
    ffmpeg, ffprobe = tool("ffmpeg"), tool("ffprobe")
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    failures: list[str] = []
    if pinned and (digest != PINNED_SHA256 or len(data) != PINNED_SIZE):
        failures.append(f"pinned identity mismatch: {digest} {len(data)}")
    probe = json.loads(run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                           capture_output=True, text=True).stdout)
    (evidence / "ffprobe-streams.json").write_text(json.dumps(probe, indent=2) + "\n")
    streams = {s["codec_type"]: s for s in probe["streams"]}
    video, audio = streams.get("video", {}), streams.get("audio", {})
    expect = {"video codec h264": video.get("codec_name") == "h264",
              "video Baseline profile": "Baseline" in video.get("profile", ""),
              "video level 3.0": video.get("level") == 30,
              "video 320x180": (video.get("width"), video.get("height")) == (WIDTH, HEIGHT),
              "video yuv420p": video.get("pix_fmt") == "yuv420p",
              "video 10 fps": video.get("r_frame_rate") == "10/1" and video.get("avg_frame_rate") == "10/1",
              "video 60 frames": video.get("nb_frames") == str(FRAMES),
              "video no B-frames": video.get("has_b_frames") == 0,
              "audio aac": audio.get("codec_name") == "aac",
              "two streams": len(probe["streams"]) == 2,
              "duration 6 s": abs(float(probe["format"]["duration"]) - 6.0) < 0.10}
    failures += [name for name, ok in expect.items() if not ok]
    frames = json.loads(run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_frames",
                             "-show_entries", "frame=pts_time,key_frame,pict_type", "-of", "json", str(path)],
                            capture_output=True, text=True).stdout)["frames"]
    pts = [float(f["pts_time"]) for f in frames]
    if len(pts) != FRAMES or any(abs(t - i / RATE) > 1e-6 for i, t in enumerate(pts)):
        failures.append("decoded PTS are not exactly n/10 for n=0..59")
    keyframes = [i for i, f in enumerate(frames) if f.get("key_frame") == 1]
    if keyframes != KEYFRAMES:
        failures.append(f"keyframes {keyframes} differ from frozen-preview.mp4 layout {KEYFRAMES}")
    sizes = {}
    for width, height in SCALED_SIZES:
        raw = run([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(path), "-an",
                   "-vf", f"scale={width}:{height}:flags=bilinear", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                  capture_output=True).stdout
        size = width * height * 3
        if len(raw) != size * FRAMES:
            failures.append(f"{width}x{height}: decoded {len(raw) // size} frames")
            continue
        (evidence / f"decoded-{width}x{height}.rgb").write_bytes(raw)
        ids, reasons, colors = [], [], []
        for index in range(FRAMES):
            frame = raw[index * size:(index + 1) * size]
            ordinal, reason = decode(frame, width, height)
            ids.append(ordinal)
            reasons.append(reason)
            colors.append(central_color(frame, width, height))
        ok_ids = ids == list(range(FRAMES))
        ok_colors = colors == ["red"] * (FRAMES // 2) + ["blue"] * (FRAMES // 2)
        if not ok_ids:
            failures.append(f"{width}x{height}: decoded IDs {ids} reasons {sorted(set(reasons))}")
        if not ok_colors:
            failures.append(f"{width}x{height}: central colors {colors}")
        sizes[f"{width}x{height}"] = {"ids_match_0_to_59": ok_ids, "central_red_then_blue": ok_colors}
    version = run([ffmpeg, "-hide_banner", "-version"], capture_output=True, text=True).stdout.splitlines()[0]
    record = {"file": path.name, "size": len(data), "sha256": digest, "pinned_checked": pinned,
              "ffmpeg": version, "stream_checks": expect,
              "frames": [{"index": i, "pts_time": t, "key_frame": f.get("key_frame"), "pict_type": f.get("pict_type")}
                         for i, (t, f) in enumerate(zip(pts, frames))],
              "scaled_decoding": sizes, "failures": failures, "passed": not failures}
    (evidence / "verify.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = parser.add_subparsers(dest="action", required=True)
    make = sub.add_parser("generate")
    make.add_argument("--output", type=Path, required=True)
    make.add_argument("--evidence-dir", type=Path, required=True)
    check = sub.add_parser("verify")
    check.add_argument("--input", type=Path, required=True)
    check.add_argument("--evidence-dir", type=Path, required=True)
    check.add_argument("--unpinned", action="store_true", help="skip the pinned SHA-256/size check")
    args = parser.parse_args()
    evidence = outside_repo(args.evidence_dir)
    evidence.mkdir(parents=True, exist_ok=True)
    if args.action == "generate":
        generate(args.output, evidence)
        record = verify(args.output, evidence, pinned=False)
    else:
        record = verify(args.input, evidence, pinned=not args.unpinned)
    print(json.dumps({"sha256": record["sha256"], "size": record["size"], "passed": record["passed"],
                      "failures": record["failures"]}))
    return 0 if record["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
