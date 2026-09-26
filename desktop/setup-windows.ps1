# SPDX-License-Identifier: GPL-2.0-or-later
# Run with: powershell -ExecutionPolicy Bypass -File desktop/setup-windows.ps1
$ErrorActionPreference = 'Stop'
if ($env:STK_SETUP_PYTHON) {
    & $env:STK_SETUP_PYTHON (Join-Path $PSScriptRoot 'setup.py') @args
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 (Join-Path $PSScriptRoot 'setup.py') @args
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python (Join-Path $PSScriptRoot 'setup.py') @args
} else {
    Write-Error 'Install x64 Python 3.12, or set STK_SETUP_PYTHON to its executable path.'
    exit 1
}
exit $LASTEXITCODE
