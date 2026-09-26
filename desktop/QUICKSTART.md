# macOS / Windows：编译并打开主窗口

在仓库根目录运行。首次会下载并编译依赖、创建 Python 环境，然后编译并启动 `stk-desktop`；
后续复用缓存。首次耗时取决于网络和机器性能，通常明显长于增量编译。

## macOS

准备 **完整 Xcode 16+**（打开一次并完成组件安装）、Git 和 Python 3.12。
确认 `xcode-select -p` 指向所用 Xcode，`python3 --version` 为 3.10–3.14。
支持当前 Python 进程的架构：Apple Silicon arm64 或 Intel x64，最低 macOS 13.3。
建议 Apple Silicon 使用原生 arm64 Python。

```bash
bash desktop/setup-macos.sh --demo
```

若 `python3` 是系统旧版本，可指定解释器：

```bash
STK_SETUP_PYTHON=/path/to/python3.12 bash desktop/setup-macos.sh --demo
```

脚本使用 Metal，从 vcpkg 编译支持 Brotli/WOFF2 的 FreeType，无需手工安装 Homebrew C++ 库。

## Windows x64

准备 **Visual Studio 2022 或 Build Tools 2022**，安装“使用 C++ 的桌面开发”工作负载
（MSVC x64/x86 工具与 Windows SDK）、Git，以及 **x64 Python 3.12**。
重新打开 PowerShell，确认 `git --version` 和 `py -3 --version` 可用。

```powershell
powershell -ExecutionPolicy Bypass -File desktop/setup-windows.ps1 --demo
```

ExecutionPolicy 仅用于本次 PowerShell 进程，不修改系统策略。也可直接运行：

```powershell
py -3 desktop/setup.py --demo
```

若需选择特定 Python，设置 `$env:STK_SETUP_PYTHON = 'C:\Python312\python.exe'` 后运行 PowerShell 入口。
脚本使用 Visual Studio CMake 生成器和 OpenGL，无需 Developer PowerShell 或 Vulkan SDK。
真机需要支持 OpenGL 4.3 的显卡驱动；暂不支持 Windows ARM64 原生构建。

## 常用选项

两个入口接受相同参数。不加 `--demo` 时打开普通主窗口。

| 参数 | 用途 |
|---|---|
| `--demo` | 打开仓库内的畴结构数据包，检查窗口、字体和 GPU |
| `--launch-only` | 使用已有程序与 Python 环境，跳过安装和编译 |
| `--no-launch` | 只准备和编译，成功后退出 |
| `--jobs 4` | 限制并行编译数；默认最多 8，内存不足时调低 |
| `--work-dir PATH` | 指定依赖和编译缓存目录；路径可包含空格 |
| `--dry-run` | 只打印步骤，不下载、不执行命令、不写文件 |
| `-- --lang en` | 将 `--` 后参数传给主程序；也支持 `--open PATH --preset volume` |

```bash
# macOS：重新编译，或直接重开程序
bash desktop/setup-macos.sh
bash desktop/setup-macos.sh --launch-only --demo -- --lang en
```

```powershell
# Windows：重新编译，或直接重开程序
py -3 desktop/setup.py
py -3 desktop/setup.py --launch-only --demo -- --lang en
```

默认缓存位于 `desktop/build-dev-macos-arm64`、`desktop/build-dev-macos-x64` 或
`desktop/build-dev-windows-x64`（已被 Git 忽略），包含 `venv`、vcpkg、依赖二进制缓存、
`build` 和 `setup.log`。请保留终端；主窗口关闭后脚本退出。

依赖固定为 [vcpkg 2026.07.29](https://github.com/microsoft/vcpkg/tree/9e593bb18ea69cc5095e012465dcd675a822ed0d)，
遵循 [vcpkg 官方引导流程](https://learn.microsoft.com/en-us/vcpkg/get_started/get-started)。
CMake、Ninja 和 STK science / visualization / control 依赖安装在专用 venv 中。
脚本只编译主程序目标，不构建完整测试套件，也不启动 Runtime 或 hub 服务。

失败时查看终端最后一个错误和 `setup.log`。修复工具链或网络后重跑；若 vcpkg 缓存不完整或被修改，
使用新的 `--work-dir`。这是源码开发测试流程；Windows 安装包和内置 Python 发布仍属于后续里程碑。

## English quick start

Install Git and Python 3.12, plus full Xcode 16+ on macOS or Visual Studio/Build Tools 2022 with the
Desktop development with C++ workload and Windows SDK on x64 Windows. From the repository root:

```bash
# macOS (native arm64 or Intel; Metal)
bash desktop/setup-macos.sh --demo
```

```powershell
# Windows x64 (OpenGL 4.3 driver required)
py -3 desktop/setup.py --demo
```

These scripts create a private venv, install CMake/Ninja and pinned vcpkg dependencies, build only
`stk-desktop`, then open its main window with the prepared Python bridge. Re-run for an incremental
build, use `--launch-only` to reopen without building, or `--no-launch` to build without opening.
Use `--work-dir PATH` for a custom cache location, `--jobs N` to limit memory use, and `--dry-run`
to inspect commands. Application flags follow `--`, for example `-- --lang en --open /path/to/data`.
Command output is saved in `setup.log`. Native Mac/Windows window, GPU and IME acceptance still
needs testing on your machines.
