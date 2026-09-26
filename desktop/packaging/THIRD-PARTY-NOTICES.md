# STK Desktop: third-party notices

STK Desktop (`stk-desktop`, `stk-render`) is free software under the **GNU General Public License,
version 2 or later** (`LICENSE`). Copyright (c) 2026 Shanghai Sijin Information Technology LLC and
contributors. The source code is at <https://github.com/sijintech/stk> (`desktop/`).

The STK Python packages (`suan`, the Runtime, the desktop bridge) are separate programs under the MIT
licence and are not part of this package. The application starts them as a child process.

## Compiled into the executables

| Component | Version | Licence | Text |
|---|---|---|---|
| Blender: GHOST, GPU module, BLF, blenlib, guardedalloc and their vendored dependencies | 5.2.1 (`blender/UPSTREAM.json`) | GPL-2.0-or-later (the vendored files); their own dependencies under the licences listed in `blender/license.md` (e.g. Vulkan Memory Allocator MIT, xxHash BSD-2-Clause, wcwidth, xdnd, Apache-2.0 files) | `blender/COPYING`, `blender/license.md`, `blender/spdx/`, `blender/others/` |
| nlohmann/json | 3.12.0 | MIT | `third-party/nlohmann_json-LICENSE.MIT` |
| libspng | 0.7.4 | BSD-2-Clause | `third-party/libspng-LICENSE` |
| miniz | 3.0.2 | MIT | `third-party/miniz-LICENSE` |
| Eigen (headers) | system / vcpkg | MPL-2.0 | `blender/spdx/MPL-2.0.txt` |
| {fmt} | system / vcpkg | MIT | `blender/spdx/MIT.txt` |

As in Blender's own releases, the executables combine GPL-2.0-or-later code with Apache-2.0
components (shaderc on Linux, a few vendored Blender files). Apache-2.0 is compatible with GPL
version 3 only, so the executables as distributed are covered by GPL-3.0-or-later (the "or later"
option of the source files); every source file keeps its own notice.

## Fonts (`datafiles/fonts`)

| Font | Licence | Text |
|---|---|---|
| Inter | SIL Open Font License 1.1 | `blender/spdx/OFL-1.1.txt` |
| Noto Sans CJK | SIL Open Font License 1.1 | `blender/spdx/OFL-1.1.txt` |
| DejaVu Sans Mono | Bitstream Vera / Arev fonts licence (public domain changes) | `blender/spdx/Bitstream-Vera.txt`, `blender/others/Arev-Fonts.txt` |

## Shared libraries

- **Linux package:** `lib/stk-desktop/` holds the libraries a stock desktop Linux does not provide
  (shaderc, libepoxy, …). `third-party/BUNDLED.txt` lists each with its Debian package and version, and
  `third-party/bundled/<package>.copyright` has its licence. Everything else (glibc, libstdc++, the
  OpenGL / Vulkan loaders and drivers, X11, Wayland, FreeType, zlib, …) comes from the system.
- **macOS app:** the vcpkg dependencies (FreeType with Brotli, zlib, zstd, {fmt}, Eigen) are linked
  statically. FreeType is under the FreeType License (`blender/spdx/FTL.txt`), Brotli MIT, zlib Zlib
  (`blender/spdx/Zlib.txt`), zstd BSD-3-Clause (`blender/spdx/BSD-3-Clause.txt`).
