#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Populate a no-sudo user sysroot with the build dependencies of the STK
# desktop engine (GHOST + GPU + BLF). Packages are fetched with
# `apt-get download` and unpacked with `dpkg-deb -x`; nothing is installed
# system-wide. The script is idempotent: packages already unpacked (same
# version) are skipped.
#
# Usage: desktop/cmake/sysroot/fetch-sysroot.sh [--with-test-servers] [SYSROOT]
#        (default SYSROOT: ~/opt/stk-sysroot)
#
# --with-test-servers also unpacks Xvfb and weston (plus their runtime libraries) for the
# optional live-window tests (desktop/tests/wm/run_with_display.py). They are only ever
# started on private unix sockets (Xvfb -nolisten tcp; weston headless backend).
#
# The list is pinned for Ubuntu 26.04 (resolute) amd64. Runtime packages are
# listed next to their -dev package so that the `libfoo.so` link symlinks
# resolve inside the sysroot. Runtime libraries that are already installed
# system-wide are still unpacked (same version) for that reason.
set -euo pipefail

WITH_TEST_SERVERS=0
if [[ "${1:-}" == "--with-test-servers" ]]; then
  WITH_TEST_SERVERS=1
  shift
fi
SYSROOT="${1:-${STK_SYSROOT:-$HOME/opt/stk-sysroot}}"
DEBS="$SYSROOT/.debs"
STAMPS="$SYSROOT/.stamps"
mkdir -p "$DEBS" "$STAMPS"

PACKAGES=(
  # X11 (GHOST_SystemX11, GLX, XInput, XFixes, Xrender, XF86VidMode).
  "libx11-dev=2:1.8.13-1" "libx11-6=2:1.8.13-1" "x11proto-dev=2025.1-1"
  "libxcb1-dev=1.17.0-2ubuntu1" "libxcb1=1.17.0-2ubuntu1"
  "libxau-dev=1:1.0.11-1build2" "libxau6=1:1.0.11-1build2"
  "libxdmcp-dev=1:1.1.5-2" "libxdmcp6=1:1.1.5-2"
  "libxi-dev=2:1.8.2-2" "libxi6=2:1.8.2-2"
  "libxfixes-dev=1:6.0.0-2build2" "libxfixes3=1:6.0.0-2build2"
  "libxrender-dev=1:0.9.12-1build1" "libxrender1=1:0.9.12-1build1"
  "libxxf86vm-dev=1:1.1.4-2" "libxxf86vm1=1:1.1.4-2"
  "libxext-dev=2:1.3.4-1build3" "libxext6=2:1.3.4-1build3"
  # Keyboard + Wayland (client, cursor, egl, scanner, protocols, libdecor).
  "libxkbcommon-dev=1.13.1-1" "libxkbcommon0=1.13.1-1"
  "libwayland-dev=1.24.0-2" "libwayland-bin=1.24.0-2"
  "libwayland-client0=1.24.0-2" "libwayland-cursor0=1.24.0-2"
  "libwayland-egl1=1.24.0-2" "libwayland-server0=1.24.0-2"
  "wayland-protocols=1.47-1"
  "libdecor-0-dev=0.2.5-1" "libdecor-0-0=0.2.5-1"
  "libdbus-1-dev=1.16.2-2ubuntu4" "libdbus-1-3=1.16.2-2ubuntu4"
  # OpenGL / EGL (glvnd) + epoxy. libegl1 + libegl-mesa0 are runtime only
  # (not installed on the build host) for headless EGL on llvmpipe.
  "libepoxy-dev=1.5.10-2build1" "libepoxy0=1.5.10-2build1"
  "libegl-dev=1.7.0-3" "libegl1=1.7.0-3" "libegl-mesa0=26.0.8-1ubuntu0.3"
  "libgl-dev=1.7.0-3" "libgl1=1.7.0-3" "libglx-dev=1.7.0-3" "libglx0=1.7.0-3"
  "libgles-dev=1.7.0-3" "libgles1=1.7.0-3" "libgles2=1.7.0-3"
  "libopengl-dev=1.7.0-3" "libopengl0=1.7.0-3" "libglvnd0=1.7.0-3"
  # Fonts.
  "libfreetype-dev=2.14.2+dfsg-1ubuntu0.1" "libfreetype6=2.14.2+dfsg-1ubuntu0.1"
  "libbrotli-dev=1.2.0-3build1" "libbrotli1=1.2.0-3build1"
  "libpng-dev=1.6.57-1" "libpng16-16t64=1.6.57-1"
  "zlib1g-dev=1:1.3.dfsg+really1.3.1-1ubuntu3.1" "zlib1g=1:1.3.dfsg+really1.3.1-1ubuntu3.1"
  # blenlib fileops (gzip / zstd helpers).
  "libzstd-dev=1.5.7+dfsg-3" "libzstd1=1.5.7+dfsg-3"
  # blenlib matrix/solver math via intern/eigen (header-only).
  "libeigen3-dev=3.4.0-5"
  # fmt (used header-only via FMT_HEADER_ONLY).
  "libfmt-dev=10.1.1+ds1-4build1" "libfmt10=10.1.1+ds1-4build1"
  # Vulkan loader + headers, shaderc (runtime GLSL -> SPIR-V).
  "libvulkan-dev=1.4.341.0-1" "libvulkan1=1.4.341.0-1"
  "libshaderc-dev=2026.1-1" "libshaderc1=2026.1-1"
  "glslang-dev=16.2.0-2" "spirv-headers=1.6.1+1.4.341.0-1"
  # Unit tests (static libgtest.a / libgmock.a + CMake config).
  "libgtest-dev=1.17.0-1build1" "libgmock-dev=1.17.0-1build1"
)

if ((WITH_TEST_SERVERS)); then
  PACKAGES+=(
    # Xvfb (X11 live-window tests) + keymap compiler and data.
    "xvfb=2:21.1.22-1ubuntu1.2" "xserver-common=2:21.1.22-1ubuntu1.2"
    "libxfont2=1:2.0.6-2ubuntu0.2" "libfontenc1=1:1.1.8-1build2"
    "x11-xkb-utils=7.7+9build1" "libxkbfile1=1:1.1.0-1build5" "xkb-data=2.46-2"
    # weston headless (Wayland live-window tests).
    "weston=14.0.2-5" "libweston-14-0=14.0.2-5"
    "libinput10=1.31.1-1ubuntu1.2" "libmtdev1t64=1.1.7-1build1"
    "libwacom9=2.18.0-1" "libwacom-common=2.18.0-1"
  )
fi

need=()
for spec in "${PACKAGES[@]}"; do
  name="${spec%%=*}"
  ver="${spec#*=}"
  stamp="$STAMPS/$name"
  if [[ -f "$stamp" && "$(cat "$stamp")" == "$ver" ]]; then
    continue
  fi
  need+=("$spec")
done

if ((${#need[@]})); then
  echo "fetch-sysroot: downloading ${#need[@]} package(s) into $DEBS"
  (cd "$DEBS" && apt-get download "${need[@]}")
  for spec in "${need[@]}"; do
    name="${spec%%=*}"
    ver="${spec#*=}"
    # apt-get download escapes ':' in the epoch as %3a.
    deb=$(ls "$DEBS/${name}_"*"_"*.deb 2>/dev/null | while read -r f; do
      v=$(dpkg-deb -f "$f" Version)
      [[ "$v" == "$ver" ]] && echo "$f"
    done | head -n1)
    if [[ -z "$deb" ]]; then
      echo "fetch-sysroot: missing .deb for $spec" >&2
      exit 1
    fi
    dpkg-deb -x "$deb" "$SYSROOT"
    echo "$ver" >"$STAMPS/$name"
  done
fi

# Re-point absolute symlinks into the sysroot (dpkg-deb keeps them verbatim).
find "$SYSROOT/usr" -type l -lname '/*' -print0 | while IFS= read -r -d '' link; do
  target=$(readlink "$link")
  ln -sfn "$SYSROOT$target" "$link"
done

# Runtime environment helper for running binaries against sysroot-only
# runtime libraries (EGL / glvnd vendor for llvmpipe).
cat >"$SYSROOT/env.sh" <<EOF
# Source this file to run STK desktop binaries against the user sysroot.
export STK_SYSROOT="$SYSROOT"
export LD_LIBRARY_PATH="$SYSROOT/usr/lib/x86_64-linux-gnu\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"
export __EGL_VENDOR_LIBRARY_DIRS="$SYSROOT/usr/share/glvnd/egl_vendor.d"
EOF

echo "fetch-sysroot: sysroot ready at $SYSROOT (${#PACKAGES[@]} packages pinned)"
