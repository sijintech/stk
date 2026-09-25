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
| `engine/third_party/blender/` | `vendor.py`, `manifest.json`, `UPSTREAM.json` (pin), `VENDORED.json` (per-file sha256), `shims/`, `patches/` (none needed), `src/` (vendored upstream files in upstream layout, including `release/datafiles/fonts` and `release/license`), and our `CMakeLists.txt`. |
| `engine/lib/stk_core`, `stk_io`, `stk_viewer_model` | CPU-only libraries (no GHOST/GPU headers): UTF-8, paths, logging, payload/JSON/schema models, PNG I/O, viewer maths. |
| `engine/lib/stk_gfx` | GPU bootstrap: process runtime (guardedalloc leak detection), backend selection, main GPU context, font stack, UI scale, offscreen render to PNG. |
| `engine/lib/stk_wm` | GHOST glue: window manager, windows, on-demand event loop, events (keys, mouse, wheel, IME preedit, drag and drop), DPI, clipboard, cursors; `WindowManager::post` / `executor()` (thread-safe work for the main loop, wakes an idle wait). Screen model (`screen.hh`): a tree of areas with draggable splitters and minimum sizes, split / join / maximize, docked regions (header, toolbar, sidebar, main) and global bars; one `stk_ui` context per window (a block per region, overlays on top, IME placement, wake-up timers); `ui_bridge.hh` (event adapter, clipboard, `UiRegion`); `layout_store.hh` (versioned layout JSON); `csd.hh` (GNOME client-side decorations). |
| `engine/lib/stk_bridge` | Client of the Python bridge (`python -m suan.desktop_bridge --stdio`, `docs/specs/stk-desktop-bridge-v1.md`): spawn (posix_spawn + process group; CreateProcessW + job object), strict NDJSON framing, futures with timeout / cancel, typed wrappers, RAII subscriptions, restart with replay, stderr ring for the "Bridge log". CPU only. |
| `engine/lib/stk_viewer_gpu` | Payload-v2 viewer on the GPU module: lit LUT-coloured triangles, slices, instanced glyphs, lines, points and sphere impostors, ray-marched volumes; overlays through BLF (scalar bar, legend, orientation sphere, triad, text); GPU id-pass picking refined in float64; tiled PNG export x1-x8; GPU budget, LOD and timestep prefetch. |
| `engine/lib/stk_app` | Application shell (`shell.hh`: top bar with File / View / Language / UI scale menus, status bar, default layout, layout files, shortcuts), `AppStore`, editor registry and `EditorArea` (tabs, header, toolbar / sidebar, area menu), the WP3 placeholder editors (Jobs, Viewer, Properties, Logs, Probe, Transfers, Bridge log). |
| `engine/lib/stk_ui` | Blender-style UI toolkit. `stk_ui_core` (no GPU/GHOST headers): blocks rebuilt per frame, layouts in UI units, widgets bound by getter/setter closures, Blender dark theme, CJK line breaking, text editing with IME preedit, i18n catalogs, JSON Schema forms, draw lists. `stk_ui_gpu`: painter on the GPU module's widget shader + BLF. Also adds `tests/ui` and `tools/widget_gallery`. |
| `app/` | `stk-desktop` (GUI and `--headless` export of the application screen; `--sample` renders the WP1 sample frame). `app/i18n/`: `zh_CN.json` (default) / `en.json` message catalogs and `check_i18n.py` (fails on missing keys). |
| `tests/ui` | stk_ui tests (label `ui`): events, text/IME, numbers, forms against the catalog and presets, layout goldens (en/zh at 1x/1.5x/2x; `STK_UPDATE_GOLDENS=1` rewrites them), i18n checker. |
| `tools/stk_render/` | `stk-render --payload <dir\|manifest.json\|.stkp> --export out.png [--size WxH] [--scale N] [--camera preset] [--pick x,y] [--bench N]`: headless payload renderer. |
| `tools/widget_gallery/` | `widget_gallery`: every widget rendered headless (`--headless --export out.png --lang zh\|en --scale S`, label `gpu` goldens) or in a window for the manual IME matrix. |
| `tests/unit` | gtest suites of the CPU libraries (label `unit`). |
| `tests/wm` | Engine tests: headless goldens and CJK crispness (label `gpu`), CLI and leak self-test (`wm`), live windows on Xvfb / weston (`window`); WP3: `stk_wm_tests` (gtest, no GPU: layout maths, screen tree, routing, persistence, layout goldens), application-screen PNG goldens, `stk-app-smoke`. |
| `tests/bridge` | stk_bridge tests (label `bridge`): protocol units, `ChildProcess`, the client against a scripted fake bridge and against the real Python bridge, and `WindowManager::post` under Xvfb / weston. |
| `tests/viewer` | stk_viewer_gpu tests: render goldens on Vulkan and GL, exact categorical colours, tiled vs single-pass export, picking accuracy at `render_origin` ~1e6, VTK offscreen cross-check (mask IoU), budget/LOD/prefetch, 1M-triangle perf smoke (`STK_VIEWER_PERF_BUDGET_MS`). Fixtures: `fixtures/make_fixtures.py [--vtk]`. |
| `spike/` | Phase 0 spike `stk-gpu-spike` and its golden image. |

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

Executables land in `<build>/bin`, with the fonts staged in `<build>/bin/datafiles/fonts` (the
same relative layout as an install: `<prefix>/bin` + `<prefix>/share/stk-desktop/datafiles`).

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
a bottom strip with the tabs Logs / Probe / Transfers / Bridge log; the editors are placeholders
until WP9 / WP10.

- Areas: drag a splitter to resize (minimum sizes hold, the other areas keep their size),
  double-click it to join the two areas beside it (the larger stays). The area menu (header button
  or right-click on the header) splits, joins, maximizes, closes, toggles toolbar / sidebar and
  adds / closes tabs; the editor-type dropdown switches the editor. Ctrl+Space maximizes the area
  under the pointer and restores it; T / N toggle the toolbar / sidebar (N-panel, resizable by its
  edge); Ctrl+PageUp / PageDown switch tabs. Files dropped on an area go to its editor
  (`Editor::on_drop`: Jobs and Transfers queue placeholder uploads, the Viewer reports `.stkp`).
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

To run binaries by hand against sysroot-only libraries, `source ~/opt/stk-sysroot/env.sh` first.

## Tests

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
- `ctest -L bridge`: `stk-bridge-tests` (gtest) and `stk-wm-post-check` (also `window`). The client
  runs against `stk-bridge-fake` (framing, oversized / invalid UTF-8 / non-strict lines, out-of-order
  responses, interleaved events, timeouts, cancellation, retries after a death, `kill -9` in the
  middle of log and event subscriptions, crash loops, a busy state directory, shutdown grace) and
  against the real bridge with `--strict` plus client-side schema validation (hello, colormaps,
  presets, local `graph.evaluate` of a fake muFerro run decoded with `stk::io`, logs from a loopback
  Runtime, and the acceptance case: `kill -9` of the bridge mid-subscription resumes from the last
  offset with no gap or duplicate). The Python is `STK_BRIDGE_TEST_PYTHON` (environment or CMake
  cache), else `python3`; parts it cannot run (no numpy/VTK, no Runtime) are skipped with the reason.
  Runtimes bind 127.0.0.1 only and are stopped afterwards; every test checks that no bridge process
  or helper of it is left.

## CI

`.github/workflows/desktop.yml` (GitHub-hosted runners, read-only token, actions pinned by SHA):

- **Linux**: `ubuntu-24.04` runner with an `ubuntu:26.04` job container (pinned by digest) so the
  packages match the sysroot; vendoring and Phase 0 go-criteria checks, full build, all tests
  including live windows.
- **macOS**: `macos-14` arm64, Xcode 16, dependencies from vcpkg (Homebrew's FreeType has no brotli,
  which the WOFF2 fonts need); full build, `unit` + `wm` tests, and the headless Metal goldens as a
  non-blocking smoke step.
- **Windows**: `windows-2022`, MSVC (Visual Studio generator), vcpkg dependencies (libepoxy,
  pthreads4w, …), OpenGL + Win32 GHOST, Vulkan off; builds every target, runs nothing.

macOS and Windows are not built on the development host; their CMake paths follow upstream's
`intern/ghost`, `source/blender/gpu`, `source/blender/blenlib` and `build_files/cmake/platform`
files (OBJCXX enabled at the top level, deployment target 13.3 for `std::format`, frameworks,
`comctl32`/`dxgi`, pthreads4w, `WIN32_LEAN_AND_MEAN`, `winstuff_registration.cc`). The first CI runs
are the real check.

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
