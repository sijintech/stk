# 生成并进入python虚拟环境
sudo apt install python3.8-venv
python3 -m venv .venv
source .venv/bin/activate

export TAURI_PRIVATE_KEY=$TAURI_PRIVATE_KEY
env
echo "TAURI_PRIVATE_KEY is $TAURI_PRIVATE_KEY"
export TAURI_KEY_PASSWORD="password"
# 安装需要的包
pip install -U pip
pip install trame pyinstaller trame_components trame_vuetify trame_vtk
# 打包生成可执行文件（web）
python -m PyInstaller \
    -F --clean --noconfirm \
    --distpath src-tauri \
    --name server \
    --hidden-import pkgutil \
    --collect-data trame_client \
    --collect-data trame_components \
    --collect-data trame_vuetify \
    --collect-data trame_vtk \
    server.py
# 打包生成桌面文件
sudo apt  install cargo
sudo cargo install tauri-cli
cd src-tauri
cargo tauri icon
sudo cargo tauri build
