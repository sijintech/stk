# STK Desktop engine

Our own C++ desktop UI engine on Blender's GHOST (windows, input, IME, GPU contexts), GPU module
(OpenGL / Vulkan / Metal) and BLF (FreeType text with CJK fallback), vendored from the pinned
Blender 5.2.1 release. Everything under `desktop/` is **GPL-2.0-or-later** (see `LICENSE`); the STK
Python packages stay MIT.

## Layout

| Path | Contents |
|---|---|
| `CMakeLists.txt` | Top level. `STK_DESKTOP_WITH_BLENDER` (default ON) builds the vendored engine; `engine/lib/*` and `tests/unit` are added when present, so the pure-CPU libraries also build with it OFF. |
| `cmake/sysroot/` | `fetch-sysroot.sh` (no-sudo user sysroot, pinned Ubuntu 26.04 packages) and `stk-sysroot.cmake` (prefix hints, auto-included on Linux). |
| `engine/third_party/blender/` | `vendor.py`, `manifest.json`, `UPSTREAM.json` (pin), `VENDORED.json` (per-file sha256), `shims/`, `patches/` (none needed), `src/` (vendored upstream files in upstream layout, including `release/datafiles/fonts` and `release/license`), and our `CMakeLists.txt`. |
| `spike/` | Phase 0 spike `stk-gpu-spike` and its golden image. |

## Build (Linux)

```sh
desktop/cmake/sysroot/fetch-sysroot.sh                     # once; fills ~/opt/stk-sysroot
cmake -S desktop -B ~/opt/stk-build/desktop -G Ninja       # sysroot is picked up automatically
ninja -C ~/opt/stk-build/desktop
ctest --test-dir ~/opt/stk-build/desktop --output-on-failure
```

Keep build trees out of git (`~/opt/stk-build/…` or `desktop/build*`). Use a different sysroot
with `-DSTK_SYSROOT=/path` or `STK_SYSROOT=/path`. Without a sysroot, CMake uses system packages.

The GPU tests (`ctest -L gpu`) render headless: Vulkan on Mesa lavapipe
(`-DSTK_SPIKE_VK_ICD=…` picks another ICD) and OpenGL 4.5 on Mesa llvmpipe through surfaceless EGL.
To run the spike by hand against sysroot-only libraries, `source ~/opt/stk-sysroot/env.sh` first.

Runtime environment:

- `STK_BLENDER_DATAFILES` overrides the fonts root (default: the vendored `src/release/datafiles`).
- Vulkan SPIR-V and pipeline caches go to `$XDG_CACHE_HOME/stk-desktop` (tests point it into the build tree).

macOS (Metal) and Windows (OpenGL + Vulkan) have CMake guards, but they are not built on this host.
They need `fmt`, `eigen`, `zstd`, `zlib` and `freetype` from a package manager, plus `epoxy` and the
Vulkan SDK (for shaderc) on Windows.

## Re-vendoring

```sh
python3 desktop/engine/third_party/blender/vendor.py --download   # fetch + verify sha256, extract, check closure
python3 desktop/engine/third_party/blender/vendor.py --check      # src/ matches VENDORED.json
```

`vendor.py` extracts the `manifest.json` whitelist, pulls the header closure from the allowed header
pools (blenlib, makesdna, blenkernel and editors headers only), and fails on any quoted `#include` that
is not resolved by a vendored file, a shim or a declared external header. It evaluates preprocessor
branches: disabled features are pruned and platform branches are all checked. The upstream archive
is cached in `~/opt/stk-src/`.
