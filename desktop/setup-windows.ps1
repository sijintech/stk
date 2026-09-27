# SPDX-License-Identifier: GPL-2.0-or-later
# Run with: powershell -ExecutionPolicy Bypass -File desktop/setup-windows.ps1
$ErrorActionPreference = 'Stop'
$setupScript = Join-Path $PSScriptRoot 'setup.py'
if ($env:STK_SETUP_PYTHON) {
    & $env:STK_SETUP_PYTHON -X utf8 $setupScript @args
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    # Prefer the tested version over whichever interpreter py -3 selects.
    # Probe only the interpreter; never retry setup itself after a build failure.
    try {
        $ErrorActionPreference = 'Continue'
        & py -3.12 -c 'import sys; sys.exit(0 if sys.maxsize > 2**32 else 1)' 2>$null
        $prefer312 = $LASTEXITCODE -eq 0
    } finally {
        $ErrorActionPreference = 'Stop'
    }
    if ($prefer312) {
        & py -3.12 -X utf8 $setupScript @args
    } else {
        & py -3 -X utf8 $setupScript @args
    }
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python -X utf8 $setupScript @args
} else {
    Write-Error 'Install x64 Python 3.12, or set STK_SETUP_PYTHON to its executable path.'
    exit 1
}
exit $LASTEXITCODE
