# 生成并进入python虚拟环境
sudo apt install python3.8-venv
python3 -m venv .venv
source .venv/bin/activate

export TAURI_PRIVATE_KEY="dW50cnVzdGVkIGNvbW1lbnQ6IHJzaWduIGVuY3J5cHRlZCBzZWNyZXQga2V5ClJXUlRZMEl5U2drSzQvU3BBVS9iZTZjMkM2ckJTRWRzVGhnQy85WG9SbUdXb3JVYnN3QUFBQkFBQUFBQUFBQUFBQUlBQUFBQUFGTTR1NlRpRTJwUUFYRjhmRXRwSmh1NzRmY0MxWW1wcHBYdVZ6Wmo4Mm5OVm1QeWtIT2tqTDM5ak54aHNsb3pKUzl0bExadExrZW1zM1lYdnBEV0FrVnR6WUp4NGNOUUk2aUNld0dqaUNjUWIydDRBMk9vMkZ0ZkdKeTUzWU5EcXNha3Ztd21kMGM9Cg=="
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
