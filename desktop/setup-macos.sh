#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
stk_script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
stk_setup_python="${STK_SETUP_PYTHON:-python3}"
if ! command -v "$stk_setup_python" >/dev/null 2>&1; then
  echo "Install Python 3.12, or set STK_SETUP_PYTHON to its executable path." >&2
  exit 1
fi
exec "$stk_setup_python" "$stk_script_dir/setup.py" "$@"
