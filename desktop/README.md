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
| `engine/lib/stk_wm` | GHOST glue: window manager, windows, on-demand event loop, events (keys, mouse, wheel, IME preedit, drag and drop), DPI, clipboard, cursors; screen / area / region layout; `WindowManager::post` / `executor()` (thread-safe work for the main loop, wakes an idle wait). |
| `engine/lib/stk_bridge` | Client of the Python bridge (`python -m suan.desktop_bridge --stdio`, `docs/specs/stk-desktop-bridge-v1.md`): spawn (posix_spawn + process group; CreateProcessW + job object), strict NDJSON framing, futures with timeout / cancel, typed wrappers, RAII subscriptions, restart with replay, stderr ring for the "Bridge log". CPU only. |
| `engine/lib/stk_ui` | Blender-style UI toolkit. `stk_ui_core` (no GPU/GHOST headers): blocks rebuilt per frame, layouts in UI units, widgets bound by getter/setter closures, Blender dark theme, CJK line breaking, text editing with IME preedit, i18n catalogs, JSON Schema forms, draw lists. `stk_ui_gpu`: painter on the GPU module's widget shader + BLF. Also adds `tests/ui` and `tools/widget_gallery`. |
| `app/` | `stk-desktop` (GUI and `--headless` export) and the WP1 sample screen. `app/i18n/`: `zh_CN.json` (default) / `en.json` message catalogs and `check_i18n.py` (fails on missing keys). |
| `tests/ui` | stk_ui tests (label `ui`): events, text/IME, numbers, forms against the catalog and presets, layout goldens (en/zh at 1x/1.5x/2x; `STK_UPDATE_GOLDENS=1` rewrites them), i18n checker. |
| `tools/widget_gallery/` | `widget_gallery`: every widget rendered headless (`--headless --export out.png --lang zh\|en --scale S`, label `gpu` goldens) or in a window for the manual IME matrix. |
| `tests/unit` | gtest suites of the CPU libraries (label `unit`). |
| `tests/wm` | Engine tests: headless goldens and CJK crispness (label `gpu`), CLI and leak self-test (`wm`), live windows on Xvfb / weston (`window`). |
| `tests/bridge` | stk_bridge tests (label `bridge`): protocol units, `ChildProcess`, the client against a scripted fake bridge and against the real Python bridge, and `WindowManager::post` under Xvfb / weston. |
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
stk-desktop --headless --size 960x600 --scale 2 --export frame.png
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
- The sample window echoes typed text, IME preedit (inline on Wayland text-input-v3, macOS and
  Windows; commit-only on X11/XIM), Ctrl+V/Ctrl+C clipboard text and dropped file paths in its
  status line, as a manual IME / clipboard / drag-and-drop test bed.
- Known WP1 gaps: GNOME on Wayland uses client-side decorations, which the app does not draw yet
  (no title bar; WP3).
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
- `ctest -L wm`: CLI, and a leak self-test proving that guardedalloc's fail-on-leak is armed (every
  engine binary aborts at exit when a block leaks).
- `ctest -L window`: `stk-wm-smoke` (first frame, window read-back, resize, user-scale DPI change,
  cursors, clipboard, timers, close, leak check) and `stk-desktop --exit-after-frames 3`, each under a
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
