# Public native document fixtures

## Frozen video

`frozen-preview.mp4` is a public synthetic six-second MP4: three seconds of red followed
by three seconds of blue at 320×180/10 fps, with a generated 440 Hz tone. It contains
H.264 Baseline level 3.0, yuv420p video and AAC audio; no source recording or private data.
SHA-256: `a54fb5baf8ca34545a8e31ea46c8801347db722cc9c876279186ab8c94f860d1` (41,558 bytes).
FFprobe independently reported both streams and six-second duration. CPU bridge tests use
the exact bytes to check frozen-source and player bindings; this does not prove browser playback.
FFmpeg is a fixture-generation tool, not a new product dependency.

Generation command:

```bash
ffmpeg -nostdin -hide_banner -loglevel error -n \
  -f lavfi -i 'color=c=red:s=320x180:r=10:d=3' \
  -f lavfi -i 'color=c=blue:s=320x180:r=10:d=3' \
  -f lavfi -i 'sine=frequency=440:sample_rate=48000:duration=6' \
  -filter_complex '[0:v][1:v]concat=n=2:v=1:a=0[video]' -map '[video]' -map 2:a \
  -c:v libx264 -profile:v baseline -level:v 3.0 -pix_fmt yuv420p -threads 1 \
  -c:a aac -b:a 48k -movflags +faststart -fflags +bitexact \
  -flags:v +bitexact -flags:a +bitexact -metadata creation_time=2000-01-01T00:00:00Z \
  frozen-preview.mp4
```

## Native PDF boundary regression

`macos-pdf-scaled-boundaries.png` is an unchanged public synthetic OS capture from
[Desktop run 40472799346](https://github.com/sijintech/stk/actions/runs/40472799346),
commit `3ac896235ca819c12a0d73304c5cd59436fe5ffb`, macOS PDF cycle 1, `visible-page1`.
SHA-256: `1a42957cd8293f70827485b6c00bc48bd12b13eafd3cc2856bb2843aab10c795`.

The 1024×653 client contains the native viewport `[631, 200, 385, 256]` in top-left
coordinates. PDF page 1 is visible, with 1–2 pixel mixtures at adjacent stripe
boundaries. The original contiguous-color predicate rejected those pixels.
The CPU replay checks page 1 inside this viewport, rejects page 2, and rejects both
markers outside it. Independent generated positive and negative cases exercise
other scales, both page orders and invalid transitions. Replay does not replace
new native lifecycle and OS capture acceptance on macOS or Windows.

## macOS media hide/reveal diagnostics

Reading guide for the `frozen-preview.mp4` media runs of
[Desktop run 42986687264](https://github.com/sijintech/stk/actions/runs/42986687264), commit
`d4064e5124f7a81e90f257f2580af35b49c555ae`, macOS artifact `13842866183`. Root's derived summary
is `root-delivery-20261113-169/platform-summary.json`; each test's `result.json` is the source.

| JUnit file | Tests | Result |
|---|---|---|
| `ctest-native-preview.xml` | `reports_native_{markdown,html,pdf,video,html-video}_metal`, `document_preview_native_metal` | 4/6, `video` and `html-video` fail while hidden |
| `ctest-native-quiet-hide.xml` | `reports_quiet_pre_seek_hide_{video,html-video}_metal` | 2/2 |
| `ctest-native-isolated-hide.xml` | `reports_isolated_quiet_pre_seek_hide_{video,html-video}_metal` | 0/2, both fail after reveal |
| `ctest-native-pause-during-suspension.xml` | `reports_pause_during_hidden_suspension_video_metal` | 1/1, with a transient Playing |

The Desktop workflow runs the six cases in `ctest-native-preview.xml` as the required native set.
The other rows report separately recorded controls.

### Reproduction

The CMake options and test names below were checked against `desktop/CMakeLists.txt`,
`desktop/engine/lib/stk_document/CMakeLists.txt`, `desktop/tests/app/reports_native.cmake` and
the artifact's ctest logs. The following commands select the media cases from a configured macOS build.

The `reports_native_{video,html-video}_*` tests need both `STK_DESKTOP_ENABLE_NATIVE_DOCUMENT_PREVIEW`
and `STK_DESKTOP_ENABLE_NATIVE_DOCUMENT_TEST_PROBES` set to `ON`. The probes option is rejected
without the preview option. These two tests are registered on macOS (`_metal`) and on Windows
(`_opengl`). The quiet, isolated and pause controls are registered on macOS only.
`STK_BRIDGE_TEST_PYTHON` sets the Python that runs the wrapper and the bridge.

```bash
cmake -S desktop -B build -DSTK_DESKTOP_ENABLE_NATIVE_DOCUMENT_PREVIEW=ON \
  -DSTK_DESKTOP_ENABLE_NATIVE_DOCUMENT_TEST_PROBES=ON -DSTK_BRIDGE_TEST_PYTHON="$VENV/bin/python"
cmake --build build --target stk-reports-native-window
env -u STK_TOKEN_PLAN_MODEL STK_TOKEN_PLAN_API_KEY= ctest --test-dir build --output-on-failure \
  -R '^reports_(native_(video|html-video)|(quiet|isolated_quiet)_pre_seek_hide_(video|html-video)|pause_during_hidden_suspension_video)_metal$' \
  --output-junit ctest-media.xml
```

Each test runs `desktop/tests/check_native_evidence.py --success-marker … --timeout 570|150 --
stk-reports-native-window --python … --gpu-backend metal --source video|html-video --media-fixture
…/frozen-preview.mp4 [--quiet-pre-seek-hide-control | --isolated-quiet-pre-seek-hide-control
[--pause-during-hidden-suspension]] --evidence-dir …`. The receipt is written to
`build/tests/app/reports-<scenario>-<source>/run-<id>/result.json`, in the format
`stk.reports-native-evidence/1`. The pause arm reuses the isolated control's success marker.
The MP4 pause arm records `scenario: pause-during-hidden-suspension`,
`matched_control: reports_isolated_quiet_pre_seek_hide_video_metal` and
`production_ui_acceptance: false`.

### Reading a receipt

The required `video` failure and both isolated failures share the error prefix "Paused media
advanced, resumed, ended or changed navigation during …". They are different failures. Tell them
apart by the phase at the end of the message and the fields below.

**Hidden position rollback (required `video` and `html-video`).** The failure is in
`last_hidden_media_observation`, cycle 1, phase `hidden-tab-pause`. The media stays `paused: true`,
but its `current_time` is earlier than before hiding. The run ends in the hidden phase with
`completed_cycles` 0. Its receipt has no `reshown_hold_native_observation`, and the summary's
`release_ack` is `null`.

| Source | `stage` / `failure_kind` | `current_time` before → when failed | Failing check | `failure_detected_seconds` |
|---|---|---|---|---|
| `video` | `hold` / `hold-predicate` | 0.336 → 0.234 | `hold_checks.abs_time_delta_le_0_10` | 0.071 |
| `html-video` | `paused-returned` / `hidden-predicate` | 0.216 → 0.102 | `hidden_checks.lower_time_ge_playing_minus_0_05` | 0.075 |

In this historical `html-video` receipt, `error` reads "Hidden pause must precede the color
transition and natural ending". Current builds report this lower-bound failure as
"Hidden media time moved backwards beyond the pause tolerance". `failure_detected_seconds`
uses the same clock as `checkpoints_seconds`, where `play_return` = 0.

**Reveal autoplay (isolated controls).** All `hidden_checks` pass in the hidden stage.
The receipts differ from the quiet arm in `scenario` and `control`. They also differ in
`quiet_hidden_observation.native_pause_before_dom_probe.pause_actuator`, which is `native` in the
quiet arm and `isolated_world` in the isolated and pause arms.
The ctest log prints several `STK_NATIVE_LAST_MEDIA_OBSERVATION` lines. The first is that
passing hidden stage (`success: true`). The failing record is the
last `reshown-no-autoresume` line, which also appears in `result.json` as
`reshown_hold_native_observation`. That phase holds for 0.50 s.

This run's `raw_playback_state` values were 3 while hidden, then 1, then 2. The Root handoff
names the states Suspended, Playing and Paused. The 3/1/2 mapping is
inferred from their order. The pause arm requires the last release state to be Paused or None
when the hold exits
(`desktop/tests/app/reports_native_window.cc`).

### Assertion timing

- `checkpoints_seconds` starts at `play_return`.
- `elapsed_seconds` in `hidden_media_native_pause_trace.events` and
  `reshown_hold_native_observation.native_trace.events` starts at the hide `dispatch`.
- `seconds_from_reveal` and `hold_*`/`last_dom_probe.*_seconds` start at `clock_origin:
  before-reveal-tab`. To convert a trace time to this clock, use
  `elapsed_seconds + native_dispatch_seconds`.

On the reveal clock, `show` occurs at about 2 ms for `video` and about 54–56 ms for `html-video`.
Use each test’s own reveal baseline when comparing timings.

| Test | `release-ack` | Native states after reveal | DOM samples / `last_dom_probe` | Hold outcome |
|---|---|---|---|---|
| quiet `video` | 11.5 ms | Playing 33.8 → Paused 75.2 ms | 19 samples, hold passed | `hold_exit_seconds` 0.550 |
| quiet `html-video` | 74.9 ms | Playing 106.0 → Paused 122.2 ms | 18 samples, hold passed | `hold_exit_seconds` 0.575 |
| isolated `video` | 11.0 ms | Playing 29.3 ms, final observed state Playing | `paused: false`, t 0.150 → 0.169 | `first_failed_predicate_seconds` 0.109 |
| isolated `html-video` | 62.3 ms | Playing 65.0 ms, final observed state Playing | `paused: false`, t 0.162 → 0.181 | `first_failed_predicate_seconds` 0.151 |
| pause arm `video` | 12.3 ms | Playing 33.0 → Paused 49.4 ms | 18 samples, hold passed | `hold_exit_seconds` 0.550 |

In the pause arm, the trace on the hide clock records `pause-during-suspension` at 72.9 ms and
`pause-during-suspension-ack` at 82.3 ms. Reveal follows at about 1.99 s. The passing quiet runs
also show transient native Playing. The isolated failures end with Playing as their latest recorded state.

The derived summary keeps only the last recorded `release_state`. To see a transient Playing,
read the summary's `relevant_events` or the receipt's `native_trace.events`. The pause arm passed for one MP4 sample. The two required tests still failed on this run.
