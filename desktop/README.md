# STK Desktop engine

Our own C++ desktop UI engine on Blender's GHOST (windows, input, IME, GPU contexts), GPU module
(OpenGL / Vulkan / Metal) and BLF (FreeType text with CJK fallback), vendored from the pinned
Blender 5.2.1 release. Everything under `desktop/` is **GPL-2.0-or-later** (see `LICENSE`); the STK
Python packages stay MIT.

## Layout

| Path | Contents |
|---|---|
| `CMakeLists.txt` | Top level. `STK_DESKTOP_WITH_BLENDER` (default ON) builds the vendored engine; `engine/lib/*` and `tests/unit` are added when present, so the pure-CPU libraries also build with it OFF. `app/` and `tests/wm` need the engine. |
| `cmake/sysroot/` | `fetch-sysroot.sh` (no-sudo user sysroot, pinned Ubuntu 26.04 packages; `--with-test-servers` adds Xvfb and weston) and `stk-sysroot.cmake` (prefix hints, auto-included on Linux when the sysroot exists). |
| `engine/third_party/blender/` | `vendor.py`, `manifest.json`, `UPSTREAM.json` (pin), `VENDORED.json` (per-file sha256), `shims/`, `patches/` (one: `0001` skips `SetMaxIdBound` with shaderc < 2024.1, for the Ubuntu 24.04 package build), `src/` (vendored upstream files in upstream layout, including `release/datafiles/fonts` and `release/license`), and our `CMakeLists.txt`. |
| `engine/lib/stk_core`, `stk_io`, `stk_viewer_model` | CPU-only libraries (no GHOST/GPU headers): UTF-8, paths, logging, payload/JSON/schema models, PNG I/O, viewer maths. |
| `engine/lib/stk_gfx` | GPU bootstrap: process runtime (guardedalloc leak detection), backend selection, main GPU context, font stack, UI scale, offscreen render to PNG. |
| `engine/lib/stk_wm` | GHOST glue: window manager, windows, on-demand event loop, events (keys, mouse, wheel, IME preedit, drag and drop), DPI, clipboard, cursors; `WindowManager::post` / `executor()` (thread-safe work for the main loop, wakes an idle wait). Screen model (`screen.hh`): a tree of areas with draggable splitters and minimum sizes, split / join / maximize, docked regions (header, toolbar, sidebar, main) and global bars; one `stk_ui` context per window (a block per region, overlays on top, IME placement, wake-up timers); `ui_bridge.hh` (event adapter, clipboard, `UiRegion`); `layout_store.hh` (versioned layout JSON); `csd.hh` (GNOME client-side decorations). |
| `engine/lib/stk_bridge` | Client of the Python bridge (`python -m suan.desktop_bridge --stdio`, `docs/specs/stk-desktop-bridge-v1.md`): spawn (posix_spawn + process group; CreateProcessW + job object), strict NDJSON framing, futures with timeout / cancel, typed wrappers, RAII subscriptions, restart with replay, stderr ring for the "Bridge log". CPU only. |
| `engine/lib/stk_viewer_gpu` | Payload-v2 viewer on the GPU module: lit LUT-coloured triangles, slices, instanced glyphs, lines, points and sphere impostors, ray-marched volumes; overlays through BLF (scalar bar, legend, orientation sphere, triad, text); GPU id-pass picking refined in float64; tiled PNG export x1-x8; GPU budget, LOD and timestep prefetch. |
| `engine/lib/stk_app` | Application shell (`shell.hh`: top bar with File / View / Language / UI scale menus, status bar, default layout, layout files, shortcuts), `AppStore`, editor registry and `EditorArea` (tabs, header, toolbar / sidebar, area menu); the WP9 editors Jobs, Transfers, Logs and Bridge log (`jobs_state.hh`: `JobsState`, the model and controller behind them, `AppStore::jobs()`; `jobs_spec.hh`: the submit form with the Runtime `TaskSpec` rules; `src/editors/jobs_*.cc`); the WP10 Viewer, Properties and Probe editors (`src/editors/viewer_*.cc`) on `ViewerState` (`viewer_state.hh`: the shown result, shared by them) and `viewer_export.hh` (PNG / sequence export). |
| `engine/lib/stk_platform` | File dialogs (`file_dialog.hh`: native through `zenity` / `kdialog` on Linux, none yet on macOS / Windows, where editors fall back to an in-app path field; `split_path_list` parses what is typed or pasted there) and `open_with_system` (xdg-open / open in its own session). CPU only. |
| `engine/lib/stk_ui` | Blender-style UI toolkit. `stk_ui_core` (no GPU/GHOST headers): blocks rebuilt per frame, layouts in UI units, widgets bound by getter/setter closures, Blender dark theme, CJK line breaking, text editing with IME preedit, i18n catalogs, JSON Schema forms, draw lists. `stk_ui_gpu`: painter on the GPU module's widget shader + BLF. Also adds `tests/ui` and `tools/widget_gallery`. |
| `app/` | `stk-desktop` (GUI and `--headless` export of the application screen; `--sample` renders the WP1 sample frame). `app/i18n/`: `zh_CN.json` (default) / `en.json` message catalogs and `check_i18n.py` (fails on missing keys). |
| `tests/ui` | stk_ui tests (label `ui`): events, text/IME, numbers, forms against the catalog and presets, layout goldens (en/zh at 1x/1.5x/2x; `STK_UPDATE_GOLDENS=1` rewrites them), i18n checker. |
| `tools/stk_render/` | `stk-render --payload <dir\|manifest.json\|.stkp> --export out.png [--size WxH] [--scale N] [--camera preset] [--pick x,y] [--bench N]`: headless payload renderer. |
| `tools/widget_gallery/` | `widget_gallery`: every widget rendered headless (`--headless --export out.png --lang zh\|en --scale S`, label `gpu` goldens) or in a window for the manual IME matrix. |
| `tests/unit` | gtest suites of the CPU libraries (label `unit`). |
| `tests/wm` | Engine tests: headless goldens and CJK crispness (label `gpu`), CLI and leak self-test (`wm`), live windows on Xvfb / weston (`window`); WP3: `stk_wm_tests` (gtest, no GPU: layout maths, screen tree, routing, persistence, layout goldens), application-screen PNG goldens, `stk-app-smoke`. |
| `tests/bridge` | stk_bridge tests (label `bridge`): protocol units, `ChildProcess`, the client against a scripted fake bridge and against the real Python bridge, and `WindowManager::post` under Xvfb / weston. |
| `tests/app` | Application editor tests, one `<name>.cmake` per work package: WP9 `jobs.cmake` (label `jobs`: `stk-jobs-tests` with the form rules, `JobsState` against `stk-bridge-fake --jobs`, UI with synthesized events and IME, layout goldens en / zh and the real Python bridge with a loopback Runtime; `stk-jobs-render` GPU goldens; `stk-jobs-live` live windows); WP10 `viewer.cmake` (label `app`: ViewerState against the fake bridge, Properties form goldens for all 7 presets, the real-bridge + GPU integration test, the headless e2e golden, live windows). |
| `docs/parity-jobs.md`, `docs/parity-viewer.md` | Parity checklists with status: the legacy PyQt Tasks tab (Jobs) and SimViz / the web viewer (Viewer). |
| `tests/viewer` | stk_viewer_gpu tests: render goldens on Vulkan and GL, exact categorical colours, tiled vs single-pass export, picking accuracy at `render_origin` ~1e6, VTK offscreen cross-check (mask IoU), budget/LOD/prefetch, 1M-triangle perf smoke (`STK_VIEWER_PERF_BUDGET_MS`). Fixtures: `fixtures/make_fixtures.py [--vtk]`. |
| `spike/` | Phase 0 spike `stk-gpu-spike` and its golden image. |
| `packaging/` | WP12: `packaging.cmake` (install layout, CPack, the `package_install*` tests), `bundle_linux_libs.py` (non-system shared libraries of a Linux install, from `ldd`), `check_install.py` (smoke test of an install / unpacked package), `THIRD-PARTY-NOTICES.md`, `macos/Info.plist.in`, `icons/` (after `web/public/icon.svg`). See "Packaging". |
| `tests/check_required_tests.py` | CI: fails when tests matching the given patterns were skipped or did not run (`ctest --output-junit`). |

## Build (Linux)

```sh
desktop/cmake/sysroot/fetch-sysroot.sh                     # once; fills ~/opt/stk-sysroot
cmake -S desktop -B ~/opt/stk-build/desktop -G Ninja       # sysroot is picked up automatically
ninja -C ~/opt/stk-build/desktop
ctest --test-dir ~/opt/stk-build/desktop --output-on-failure
```

Keep build trees out of git (`~/opt/stk-build/…` or `desktop/build*`). Use a different sysroot
with `-DSTK_SYSROOT=/path` or `STK_SYSROOT=/path`. Without a sysroot (CI), CMake uses system packages;
`.github/workflows/desktop.yml` lists them for Ubuntu 26.04.

Executables land in `<build>/bin`, with the fonts staged in `<build>/bin/datafiles/fonts` and the
catalogs in `<build>/bin/i18n` (found relative to the executable, as in an install; see "Packaging").

User documentation (Chinese, then English): [`docs/desktop.md`](../docs/desktop.md).

## Running

```sh
stk-desktop                                   # window titled "STK" (Wayland, else X11)
stk-desktop --lang en --layout my-layout.json # English, a given layout (not written back)
stk-desktop --headless --size 1280x800 --lang zh --export screen.png
stk-desktop --headless --sample --size 960x600 --scale 2 --export frame.png   # WP1 sample frame
stk-desktop --version | --help
```

- `--gpu-backend auto|opengl|vulkan|metal` or `STK_GPU_BACKEND` picks the backend (default: OpenGL on
  Linux and Windows, Metal on macOS; `auto` falls back to the other compiled backends).
- UI scale = the window's native DPI factor (`max(DPI hint, 96) / 96` × native pixel size) × the user
  scale (`--scale`, or Ctrl +/-/0 in the window). Text is rasterized at the target size.
- Fonts: `--datafiles DIR` or `STK_BLENDER_DATAFILES`, else next to the executable
  (`datafiles/`, `../share/stk-desktop/datafiles/`, `../Resources/datafiles/`), else the vendored
  source tree (development builds).
- Vulkan SPIR-V and pipeline caches go to `$XDG_CACHE_HOME/stk-desktop` (tests point it into the
  build tree).
- Message catalogs: `--i18n DIR` or `STK_I18N_DIR`, else next to the executable (`i18n/`,
  `../share/stk-desktop/i18n/`), else the source tree. Default language zh (`--lang zh|en`).

### Screen (WP3)

The window shows a top bar (menus File / View / Language / UI scale, title), a tree of areas and a
status bar (bridge state, connection, hints). The default layout is Jobs | Viewer | Properties over
a bottom strip with the tabs Logs / Probe / Transfers / Bridge log (WP9: Jobs, Logs, Transfers and
Bridge log; WP10: Viewer, Properties and Probe; see below).

- Areas: drag a splitter to resize (minimum sizes hold, the other areas keep their size),
  double-click it to join the two areas beside it (the larger stays). The area menu (header button
  or right-click on the header) splits, joins, maximizes, closes, toggles toolbar / sidebar and
  adds / closes tabs; the editor-type dropdown switches the editor. Ctrl+Space maximizes the area
  under the pointer and restores it; T / N toggle the toolbar / sidebar (N-panel, resizable by its
  edge); Ctrl+PageUp / PageDown switch tabs. Files dropped on an area go to its editor
  (`Editor::on_drop`: Jobs and Transfers upload them, the Viewer opens payloads and result / run
  folders).
  Internal drag and drop between widgets is deferred.
- UI: one `stk_ui` context per window. Each visible region builds its blocks in window coordinates
  every (on-demand) frame; popups, tooltips, modals and toasts are overlay blocks above all areas.
  Painting goes region by region (GPU content via `Region::draw`, then its UI blocks), overlays last.
  Events go to the UI first (widgets, popups, text editing, IME), then to the region and area under
  the pointer (keys: under the pointer, else the last clicked region), then to application
  shortcuts. The IME candidate window follows the edited text field. Redraws are on demand, with
  per-region redraw tags (`Region::redraw_tagged`, for cached GPU content) and a wake-up timer for
  tooltips and toasts.
- Layout persistence: saved when the window closes (and File > Save layout, Ctrl+S) to
  `$XDG_CONFIG_HOME/stk/desktop/layout.json` (`~/Library/Application Support/stk/desktop/`,
  `%APPDATA%\stk\desktop\`): format `stk.desktop.layout`, `version` 1, window size / position /
  maximized, language, UI scale and the screen tree (splits with factors, areas with id, editor
  type, region sizes and visibility, and editor state such as tabs). A missing file gives the default
  layout; a corrupt, invalid or newer-version file is moved to `layout.json.corrupt`, logged, and the
  default layout is used. `--layout FILE` loads a file without writing it back; `--no-save-layout`
  disables saving; `--save-layout FILE` writes the (headless: rendered) layout.
- Bridge: the GUI starts the Python bridge (stk_bridge; `--no-bridge` disables it, `--python PATH`
  or `STK_PYTHON` picks the interpreter; development builds add the source tree to its
  `PYTHONPATH`). `stk::app::BridgeStatus` mirrors the client into the status bar and the Bridge log
  editor: state changes arrive through `WindowManager::executor()` on the main loop, the stderr ring
  is copied by a main-loop timer.
- Client-side decorations: GNOME on Wayland draws no title bars. Blender 5.2's GHOST no longer uses
  libdecor (the sysroot's libdecor is unused): it has its own CSD (`WITH_GHOST_CSD`, compiled in),
  enabled when `XDG_CURRENT_DESKTOP` contains GNOME. GHOST moves, resizes, maximizes, minimizes and
  closes the window on the elements the application reports through a layout callback; stk_wm
  installs it (`csd.hh`), and the top bar doubles as the title bar: drag zone right of the menus,
  resize borders at the window edges, and the buttons of the GNOME button layout (`gsettings
  button-layout`, e.g. close only) drawn at the right. GHOST asks for the layout on compositor
  configures after the first one (GNOME activates, resizes or changes the state of the window
  soon after mapping); a UI scale change reaches the decorations at the next configure.
- Closing a window runs its close listeners (`Window::add_close_listener`) before its screen and GPU
  context go away; the shell uses one to forget that screen, so store changes that arrive later
  (bridge callbacks, the Jobs and Viewer states) never reach a destroyed screen.
- Other threads hand work to the main loop with `WindowManager::post` (or the `executor()` it gives
  to background services such as stk_bridge). The wake-up per back-end: X11 polls an eventfd (a
  self-pipe off Linux) together with the X connection, bounded by GHOST's next timer, then lets GHOST
  drain its events; Win32 posts `WM_NULL` to the main thread, which ends GHOST's message wait;
  Wayland and Cocoa (whose GHOST back-ends do not block usefully) wait on a condition variable for at
  most their 5 ms poll interval, which a post ends at once. `STK_WM_WAIT=poll` forces the polling
  mode (diagnostics).
- The bridge's interpreter: the app setting, else `STK_PYTHON`, else a bundled one, else
  `python3` / `python` on PATH. `STK_BRIDGE_VALIDATE=1` makes the client validate every message both
  ways against the built-in copy of `desktop-bridge-1.schema.json`.

### Jobs (WP9)

The Jobs editor replaces the legacy PyQt Tasks tab (`docs/parity-jobs.md` lists every item). All
state is in `JobsState` (`AppStore::jobs()`, main thread; bridge callbacks arrive through the
client's executor and are dropped once the connection, workspace or task changed):

- Connection: this computer (local Runtime, always listed, with its status and Start, which sets it
  up first when needed), Runtime profiles (shared
  with `suan connect`; Add… with token or token file, Remove… warns that the profile goes from
  `suan connect` too) and paired hubs (Pair… with a one-time code; node, templates and review
  policy); health in the editor and the status bar.
- Workspace: list, New…, input files (double-click downloads and opens one), uploads of files or
  folders (native dialog, else a path field; drag and drop onto Jobs or Transfers; a folder's
  contents at the workspace root by default), progress, hub uploads waiting for the
  `workspace.import` review.
- New task: name (IME), program, arguments (Python `shlex` rules), backend, resources (CPUs or
  MPI ranks / threads per rank, nodes, memory, time limit, GPUs, queue, account), expected outputs,
  environment, retry policy; validated with the Runtime `TaskSpec` rules before sending; one
  idempotency key per submission, reused by automatic and manual retries; through a hub a
  template, or a custom command that waits for review.
- Tasks: the `watch` snapshots (state, not deltas) in a sortable table with state colours; Cancel
  (confirmed); Open in Viewer (`AppStore::request_open_result`).
- Task detail: Logs (stdout + stderr or each alone, follow-tail), Monitor (monitoring-events
  summary), Results (artifacts; Download verifies the sha256 again on disk and opens the file,
  Save as… picks the destination; PNGs are decoded with stk_io and shown as a GPU texture), Info.
- Hub review: actions in review; Inspect (full request) before Approve; the hub's `review_policy`
  refusal is explained; after a bridge restart the action is read again before approving.
- Transfers: every journaled transfer with progress, resume and cancel. Logs: the application log.
  Bridge log: the bridge's stderr, its state and a Restart after it failed.
- Closing the app never stops jobs: detaching drops subscriptions; the bridge gets EOF (no cancel).

### Viewer, Properties and Probe (WP10)

All three show `AppStore::viewer()` (`stk/app/viewer_state.hh`), the result on screen:

- **Opening**: File > Open payload / result (a path field), drag and drop on
  the Viewer, `--open PATH` at start, and the Jobs editor's "Open in viewer" (`take_open_result`). A
  `.stkp` / payload folder is shown as is; a result folder of `suan graph run` (`result.json`, or
  `series.json` whose steps drive the scrubber) is read from disk; a run folder (e.g. muFerro) is
  evaluated in the bridge (`graph.evaluate`, local mode, `local_bindings`); a task through a Runtime
  task binding (local mode) or a hub (hub mode). Only the preset's payload outputs are requested.
- **Viewer** (`draws_gpu`: `stk_viewer_gpu` under a transparent main block): Blender navigation by default
  (middle drag orbit, Shift pan, Ctrl zoom, wheel; the left button uses the toolbar tool orbit / pan /
  zoom / pick, shown as the glyphs ↻ ✚ ± ⊙ with the name in the tooltip), ParaView optional; a click picks (GPU id pass + float64) and the Probe editor shows it;
  numpad 1 / 3 / 7 / 0 / 9, Home, Space (play), ← / →. Sidebar: layers (visibility, opacity), camera
  (7 presets, reset, numeric camera in physical coordinates), time steps (scrubber, play / pause, fps,
  loop, prefetch, latest), display (overlays, lighting, navigation). Payload warnings and stats sit at
  the bottom of the view. Picking and exports run outside the frame (`WindowManager::post`).
- **Properties**: preset picker (`graph.presets`), the parameter form generated from JSON Schema
  (`stk_ui` `preset_schema` / `build_form`, `x-stk-group` panels) in a data-stage box and a
  client-stage box; colormap parameters use the colormap dropdown fed by `colormaps.list`. Edits are
  debounced (data 0.35 s, client 0.06 s) and a newer evaluation cancels the running one
  (`graph.cancel`); `graph.progress` drives the progress bar; the summary names the evaluated nodes
  (`result.evaluated`). Results are cached per parameters and step; the steps next to the shown one
  are evaluated in the background and uploaded to the GPU ahead, so a cached step switches without a
  bridge call and keeps the camera.
- **Probe**: layer, element and physical position (`format_label`) of the last pick, the original value
  from the bridge `probe` (trilinear sample of the source field), and a typed position to query.
- Hub evaluation reads the policy of the result's source connection, independently of the connection
  selected in Jobs. Its desktop auto-run byte cap applies to both requested and prefetched steps;
  switching sources or cancelling also cancels a pending policy lookup.
- Local graph evaluation uses a reusable Python worker process and a serial lane, leaving bridge
  requests responsive while retaining the node cache. Cancellation first cooperates with the evaluator;
  after 0.5 seconds, unresponsive work is terminated with its worker and render subprocesses. A worker
  crash fails that request; the next evaluation starts a fresh worker with the existing disk cache.
- **Export dialog**: size, magnification ×1–×8 (tiled), transparent background, overlays, and "all time
  steps" (`<stem>.%08d.png` + an `stk.series/1` manifest `<stem>.series.json`).
- **Headless** (the WP12 e2e golden): `stk-desktop --headless --preset muferro-domains --run DIR
  --export out.png [--size WxH] [--camera iso|+x|…] [--param NAME=JSON] [--magnification N]
  [--transparent] [--no-overlays] [--sequence] [--state-dir DIR] [--python PY]` evaluates through the
  real bridge and renders the Viewer's image (not the screen).
- Parity with SimViz and the web viewer: `docs/parity-viewer.md`.

To run binaries by hand against sysroot-only libraries, `source ~/opt/stk-sysroot/env.sh` first.

## Tests

- `ctest -L unit`: viewer helpers include candidate-only picking, screen-space line hits with
  perspective and clipping, shared scalar/range resolution, and area-weighted smooth normals.
  `tests/unit/fixtures/make_viewer_helpers.py` regenerates Python scalar and independent NumPy
  normal references. The normal references follow the web viewer's area weighting; the Python
  offscreen renderer still uses VTK's normal filter and may differ for unequal face areas or winding.
- `ctest -L gpu`: headless exports of the sample frame at 1×, 1.5× and 2× for each backend (Vulkan on
  Mesa lavapipe, `-DSTK_TEST_VK_ICD=…` picks another ICD; OpenGL 4.5 on llvmpipe through surfaceless
  EGL; Metal on macOS). `stk-wm-image-check` compares with `tests/wm/golden/` (at most 1% of the
  pixels may differ by more than 40), checks the theme colors, and checks that "中文" glyph heights
  scale linearly and that edges stay as sharp as at 1× (clearly sharper than an upscaled 1× bitmap).
  Refresh goldens with `stk-wm-image-check --golden-dir desktop/tests/wm/golden --update-golden 1=… 1.5=… 2=…`.
- `ctest -L gpu` (WP3): `stk-desktop --headless` exports of the default screen (en at 1× 1280×800,
  zh at 1.5× 1440×900) per backend, compared by `stk-png-diff` with `tests/wm/golden/app_default_*.png`
  (at most 2% of the pixels may differ by more than 48; refresh with `stk-png-diff OUT GOLDEN
  --update`), and layout files through the CLI (save, load, corrupt-file fallback).
- `ctest -L wm`: CLI, and a leak self-test proving that guardedalloc's fail-on-leak is armed (every
  engine binary aborts at exit when a block leaks). `stk_wm_tests` (no GPU, fake text measurer):
  size distribution with minimum sizes, split / join / resize / maximize, hit testing and event
  routing (splitter and region-edge drags, focus, pointer and UI capture across areas, keys, drops,
  deferred changes, IME caret, tooltip wake-ups), the shell (tabs, editor switching, area menu,
  language), persistence round trips and corrupt-file fallback, CSD geometry, and layout goldens of
  the default screen (areas, regions, splitters, UI blocks and widgets) for zh / en at 1×, 1.5×
  and 2× in `tests/wm/golden/layout_default_*.json` (`STK_UPDATE_GOLDENS=1` rewrites them).
- `ctest -L window`: `stk-wm-smoke` (first frame, window read-back, resize, user-scale DPI change,
  cursors, clipboard, timers, close, leak check), `stk-desktop --exit-after-frames 3` and
  `stk-app-smoke` (application screen: pixels, a splitter dragged with synthesized events, resize with
  minimum sizes, UI scale, close with the layout saved and reloaded; plus a GNOME CSD run on weston's
  desktop shell with `XDG_CURRENT_DESKTOP=GNOME`), each under a
  private Xvfb (`-nolisten tcp`, cookie auth, `-displayfd`) and a headless weston (pixman, own
  `XDG_RUNTIME_DIR` in the build tree), started by `tests/wm/run_with_display.py`. The runner refuses
  to continue if a server listens on TCP, stops the server afterwards, and skips (exit 77) when the
  servers are not installed. On this host they come from `fetch-sysroot.sh --with-test-servers`; the
  sysroot Xvfb is run from a copy whose compiled-in `/usr/bin` xkbcomp directory is redirected to the
  sysroot's xkbcomp.
- `ctest -L jobs` (WP9, `tests/app`): `stk-jobs-tests` (gtest, no GPU): the submit form against the
  `TaskSpec` rules and Python's `shlex`; `JobsState` against `stk-bridge-fake --jobs DIR` (a fake
  Runtime and hub kept in `DIR/model.json`, every request method logged in `DIR/methods.log`):
  connections and health, add / pair / remove, the local Runtime, uploads (pending until a
  workspace, blocking submits), idempotent submits with automatic and manual retry, watch, logs,
  monitoring events, verified downloads and PNG previews, cancel, the hub review flow, the
  `review_policy` refusal, re-inspection after a restart (also after `kill -9` of the bridge), hub
  import reviews, and closing without cancelling; the editor's UI driven with synthesized events
  (dialogs, the path-field fallback of the file dialog, Chinese through IME events, the Transfers
  editor) and layout goldens (`tests/app/golden/jobs_layout_*.json`, `STK_UPDATE_GOLDENS=1`); and
  the real Python bridge with a loopback Runtime (`tests/app/jobs_fixture.py`): add the profile,
  create a workspace, upload a folder, submit, see it listed, stream logs, download the PNG
  artifact with its sha256 verified and decode it, then close the app while a second task runs and
  check that it still finishes. `stk-jobs-render` (label `gpu`): the Jobs editor with a populated
  fake task list and a PNG preview, per backend, against `tests/app/golden/jobs_editor_*.png`.
  `stk-jobs-live` (label `window`): a live window on Xvfb and weston, Chinese typed into the task
  name through IME events, submitted to the fake bridge, then closed without cancelling.
- `ctest -L bridge`: `stk-bridge-tests` (gtest) and `stk-wm-post-check` (also `window`). The client
  runs against `stk-bridge-fake` (framing, oversized / invalid UTF-8 / non-strict lines, out-of-order
  responses, interleaved events, timeouts, cancellation, retries after a death, `kill -9` in the
  middle of log and event subscriptions, crash loops, a busy state directory, shutdown grace) and
  against the real bridge with `--strict` plus client-side schema validation (hello, colormaps,
  presets, local `graph.evaluate` of a fake muFerro run decoded with `stk::io`, logs from a loopback
  Runtime, and the acceptance case: `kill -9` of the bridge mid-subscription resumes from the last
  offset with no gap or duplicate). The Python is `STK_BRIDGE_TEST_PYTHON` (environment or CMake
  cache; the viewer tests take `STK_APP_TEST_PYTHON` first), else `python3`; parts it cannot run (no
  numpy/VTK, no Runtime) are skipped with the reason (CI requires them to run on Linux).
  Runtimes bind 127.0.0.1 only and are stopped afterwards; every test checks that no bridge process
  or helper of it is left.

- `ctest -L app` (WP10, `tests/app/viewer.cmake`): `stk_app_viewer_tests` (gtest, no GPU):
  `ViewerState` against `stk-bridge-fake` (whose graph methods serve the muferro-domains fixture:
  evaluated nodes after client- and data-stage edits, debounce, cancellation of superseded
  evaluations, `graph.progress`, prefetch and cached step switches with the camera kept, playback,
  probe, layer overrides, sequence export), result / series folders, drop and the open / export
  dialogs, and layout goldens of the Properties forms of all 7 presets in zh and en
  (`tests/app/golden/props_forms_*.json`, `STK_UPDATE_GOLDENS=1`). `app_viewer_python_<backend>`: the
  real bridge evaluates muferro-domains on a fake muFerro run; a client-stage change re-runs no data
  node and re-renders, a data-stage change re-runs them, a cached step switch stays under 300 ms, a GPU
  pick is probed. `app_viewer_e2e_<backend>` (`run_e2e.py`): the headless command against
  `tests/app/golden/e2e_muferro_domains.png` (SSIM ≥ 0.98) and the VTK reference (mask IoU ≥ 0.9),
  plus a sequence export. `app_viewer_window_{xvfb,weston}` (`stk-viewer-live`): open a run in the
  application window, orbit with a synthesized drag, pick, and the Probe editor shows the value;
  `app_viewer_gui_open_*`: `stk-desktop --open` draws a payload and quits without leaks.

## Packaging

`packaging/packaging.cmake` defines the install layout (the directories and `CMAKE_INSTALL_RPATH`
are set in the top-level `CMakeLists.txt`, before the targets exist):

| Linux / Windows prefix | macOS | Contents |
|---|---|---|
| `bin/` | `STK.app/Contents/MacOS/` | `stk-desktop`, `stk-render` |
| `lib/stk-desktop/` | (none) | bundled shared libraries (Linux, `STK_DESKTOP_BUNDLE_LIBS`) |
| `share/stk-desktop/datafiles/fonts` | `STK.app/Contents/Resources/datafiles/fonts` | Inter, Noto Sans CJK, DejaVu Sans Mono |
| `share/stk-desktop/i18n` | `STK.app/Contents/Resources/i18n` | `zh_CN.json`, `en.json` |
| `share/doc/stk-desktop/` | `STK.app/Contents/Resources/licenses/` | `LICENSE`, `THIRD-PARTY-NOTICES.md`, `blender/` (upstream COPYING, `license.md`, SPDX texts incl. OFL-1.1 and Bitstream Vera), `third-party/` (nlohmann/json, libspng, miniz; Linux: `BUNDLED.txt` and the Debian copyright file of each bundled library) |
| | `STK.app/Contents/Info.plist`, `Resources/stk-desktop.icns` | bundle id `ai.sijin.stk.desktop` (`STK_BUNDLE_ID`), minimum macOS = `CMAKE_OSX_DEPLOYMENT_TARGET` |

The executables find fonts and catalogs relative to themselves (`../share/stk-desktop/…`,
`../Resources/…`), so an install or unpacked package can live anywhere.

- `STK_DESKTOP_RELOCATABLE=ON` (package builds) forces `STK_GFX_SOURCE_DATAFILES_FALLBACK`,
  `STK_APP_SOURCE_I18N_FALLBACK` and `STK_DESKTOP_SOURCE_PYTHON_FALLBACK` off: nothing from the build
  host's source tree is compiled in, and the bridge's interpreter must have STK installed.
- `STK_DESKTOP_BUNDLE_LIBS=ON` (Linux): at install time `bundle_linux_libs.py` runs `ldd` on the
  installed executables and copies every library outside the system set (glibc, libstdc++, the GL /
  EGL / Vulkan loaders, X11 / xcb / Wayland / xkbcommon / D-Bus, zlib, zstd, bzip2, brotli, libpng,
  FreeType, …) into `lib/stk-desktop`, with its Debian copyright file; on Ubuntu 24.04 that is
  shaderc and libepoxy. The executables are linked with `--disable-new-dtags` so their RPATH
  `$ORIGIN/../lib/stk-desktop` also serves the dependencies of bundled libraries.
- The macOS vcpkg dependencies are static, so `STK.app` links only system libraries and frameworks;
  CI checks this with `otool -L`. No install RPATH is set on macOS.

```sh
# Linux tarball (CI builds it on Ubuntu 24.04: glibc >= 2.39)
cmake -S desktop -B build-pkg -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DSTK_DESKTOP_RELOCATABLE=ON -DSTK_DESKTOP_BUNDLE_LIBS=ON
cmake --build build-pkg --target stk-desktop stk-render
(cd build-pkg && cpack)                        # stk-desktop-<version>-linux-x86_64.tar.gz
# macOS app
cmake --install build-pkg --prefix stage --strip && codesign --force --sign - stage/STK.app
ditto -c -k --keepParent stage/STK.app stk-desktop-<version>-macos-arm64.zip
# smoke test of an install / unpacked package (see the script's docstring)
python3 desktop/packaging/check_install.py --prefix DIR --workdir /tmp/check --payload docs/specs/examples/payload-v2 \
  [--python VENV/bin/python --repo . --golden desktop/tests/app/golden/e2e_muferro_domains.png]
```

On Ubuntu 24.04, the build needs newer Vulkan headers (1.4) and wayland-protocols XML than the
distribution has; CI passes `-DVulkan_INCLUDE_DIR=` and `-DWAYLAND_PROTOCOLS_DIR=` of pinned
Vulkan-Headers 1.4.341 and wayland-protocols 1.47 (build-time only; the binaries use 24.04's
`libvulkan` and `libwayland`). The Python side is not bundled (D1); users install STK into a venv and
point the app at it (`--python`, `STK_PYTHON`, PATH). An AppImage, a Windows installer and a bundled
Python are follow-ups (M-D2).

`ctest -L package`: `package_install` installs the build into `<build>/install-check`, and
`package_install_check` runs `check_install.py` on it (layout, `ldd`, the installed `stk-desktop`
headless from an unrelated directory reporting fonts and catalogs from the prefix, `stk-render`).

## CI

`.github/workflows/desktop.yml` (GitHub-hosted runners, read-only token, actions pinned by SHA, no
secrets):

- **Linux**: `ubuntu-24.04` runner with an `ubuntu:26.04` job container (pinned by digest, `--init`
  so orphaned processes are reaped) so the packages match the sysroot; vendoring and Phase 0
  go-criteria checks, full build, all tests including live windows. A venv with
  `.[science,visualization,control,test]` is `STK_BRIDGE_TEST_PYTHON` / `STK_APP_TEST_PYTHON`, so the
  real-bridge tests (`PythonBridge.*`, `JobsPython.*`, `app_viewer_python_*`, the e2e golden
  `app_viewer_e2e_*`, `app_viewer_window_*`) run; `tests/check_required_tests.py` fails the job if any
  of them (or `package_install_check`) skipped. Rendered frames and the e2e PNGs are uploaded.
- **Linux package**: `ubuntu:24.04` container: Release, relocatable, bundled libraries, CPack TGZ
  (artifact `desktop-linux-package`). **Linux package smoke**: a fresh `ubuntu:24.04` container with only
  runtime libraries (no shaderc, no libepoxy) unpacks the tarball and runs `check_install.py` on OpenGL
  (llvmpipe) and Vulkan (lavapipe), including the e2e preset command against a venv with
  `pip install .[science,visualization,control]` and the golden.
- **macOS**: `macos-15` arm64, Xcode 16, dependencies from vcpkg built for macOS 13.3 (overlay
  triplet; Homebrew's FreeType has no brotli, which the WOFF2 fonts need), Python 3.12 venv as above;
  full build, `unit`, `wm`, `ui` and `bridge` tests, then every `gpu` test on the runner's "Apple
  Paravirtual device" (Metal goldens, UI gallery, viewer, `app_viewer_python_metal`,
  `app_viewer_e2e_metal`, `package_install_check`) and an `stk-render` smoke export. Then the
  relocatable `STK.app` (ad-hoc signed, `otool -L` system libraries only), zipped (artifact
  `desktop-macos-app`), unzipped into a fresh directory and run headless on Metal with the e2e preset
  command. macOS 14 runners have no Metal device.
- **Windows**: `windows-2022`, MSVC (Visual Studio generator), vcpkg dependencies (libepoxy,
  pthreads4w, …), OpenGL + Win32 GHOST, Vulkan off; builds every target and runs the `unit`, `wm`,
  `ui` and `bridge` tests (no GPU tests: the runner has no OpenGL 4.3 driver). Packaging is M-D2.

macOS and Windows are not built on the development host; their CMake paths follow upstream's
`intern/ghost`, `source/blender/gpu`, `source/blender/blenlib` and `build_files/cmake/platform`
files (OBJCXX enabled at the top level, deployment target 13.3 for `std::format`, frameworks,
`comctl32`/`dxgi`, pthreads4w, `WIN32_LEAN_AND_MEAN`, `winstuff_registration.cc`, the
`cmake/windows/stk-desktop.manifest` application manifest after upstream's `blender.exe.manifest`).

## Re-vendoring

```sh
python3 desktop/engine/third_party/blender/vendor.py --download   # fetch + verify sha256, extract, check closure
python3 desktop/engine/third_party/blender/vendor.py --check      # src/ matches VENDORED.json
```

`vendor.py` extracts the `manifest.json` whitelist, pulls the header closure from the allowed header
pools (blenlib, makesdna, blenkernel and editors headers only), and fails on any quoted `#include` that
is not resolved by a vendored file, a shim or a declared external header. It evaluates preprocessor
branches: disabled features are pruned and platform branches are all checked. The upstream archive
is cached in `~/opt/stk-src/` (`--archive PATH` uses a local copy).
