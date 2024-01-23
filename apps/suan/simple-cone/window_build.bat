@echo off
REM Setup virtual environment
python -m venv .venv
call .venv\Scripts\activate

REM Upgrade pip
REM pip install -U pip
python.exe -m pip install -U pip

REM Install dependencies
pip install trame pyinstaller trame_components trame_vuetify  trame_vtk

REM Build executable
python -m PyInstaller ^
    -F --clean --noconfirm ^
    --distpath src-tauri\server ^
    --name server ^
    --hidden-import pkgutil ^
    --collect-data trame_components ^
    --collect-data trame_vtk ^
    --collect-data trame_vuetify ^
    --collect-data trame_client ^
    server.py

REM Change to output directory
cd src-tauri

REM Set app icon
cargo tauri icon 

REM Build the app
cargo tauri build 

