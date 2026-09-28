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
# 先检查工具链：不安装依赖、不编译、不打开窗口
powershell -NoProfile -ExecutionPolicy Bypass -File desktop/setup-windows.ps1 --check

# 检查通过后，编译并打开自带示例；普通 PowerShell 即可
powershell -NoProfile -ExecutionPolicy Bypass -File desktop/setup-windows.ps1 --demo
```

脚本优先选择 x64 Python 3.12，缺少该版本时使用 `py -3`，然后检查 Python 版本及位数。
`--check` 会检查 Git、VS2022 C++ 工具、Windows SDK 的头文件、x64 库和资源编译器，
在默认缓存目录写入检测日志；不会自动安装系统工具或修改系统配置。
VS2022 的检测使用 [vswhere](https://github.com/microsoft/vswhere)，
编译和依赖安装使用同一个已检测的 VS 实例。

ExecutionPolicy 仅用于本次 PowerShell 进程，不修改系统策略。也可直接运行：

```powershell
py -3 desktop/setup.py --demo
```

若需选择特定 Python，设置 `$env:STK_SETUP_PYTHON = 'C:\Python312\python.exe'` 后运行 PowerShell 入口。
脚本使用 Visual Studio CMake 生成器和 OpenGL，无需 Developer PowerShell 或 Vulkan SDK。
真机需要支持 OpenGL 4.3 的显卡驱动；暂不支持 Windows ARM64 原生构建。

再次打开已编译程序：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File desktop/setup-windows.ps1 --launch-only --demo
```

缺少工具时，安装 Git for Windows、x64 Python 3.12，以及 Visual Studio Installer 中的
“使用 C++ 的桌面开发”（Build Tools 中通常显示为“C++ 生成工具”）。确保同时选中
MSVC v143 x64/x86 工具和 Windows 10/11 SDK，然后重新打开 PowerShell 并运行 `--check`。
若 `py` / `python` 打开 Microsoft Store，使用 `STK_SETUP_PYTHON` 指定已安装的解释器。
若切换过 VS 安装路径，使用新的 `--work-dir C:\stk-build`，避免复用旧 CMake 工具链缓存。

窗口测试建议：先确认示例模型可见，再拖动旋转、滚轮缩放、切换中英文；关闭窗口后用
`--launch-only --demo` 重开。默认日志在 `desktop\build-dev-windows-x64\setup.log`。
显卡驱动不足时，环境检查可能通过，但 OpenGL 窗口仍会启动失败；请安装显卡厂商驱动。

## 常用选项

两个入口接受相同参数。不加 `--demo` 时打开普通主窗口。

| 参数 | 用途 |
|---|---|
| `--check` | 只检查当前 Python、Git 和原生编译工具，不安装或编译 |
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

## 测试项目表格

更新源码后重跑脚本进行增量编译（本次不要用 `--launch-only`）。主窗口内选择
**文件 → 项目表格**，填入一个新的绝对目录和名称创建项目，再添加表格、字段、记录并编辑值。
每次修改立即保存到该目录的 `project.sqlite3`；关闭后可再次打开同一目录验证数据。
表格区域可用 `Ctrl+Space` 最大化。详细步骤和当前限制见[项目指南](../docs/project.md)。

## English quick start

Install Git and Python 3.12, plus full Xcode 16+ on macOS or Visual Studio/Build Tools 2022 with the
Desktop development with C++ workload and Windows SDK on x64 Windows. From the repository root:

```bash
# macOS (native arm64 or Intel; Metal)
bash desktop/setup-macos.sh --demo
```

```powershell
# Windows x64 (OpenGL 4.3 driver required)
powershell -NoProfile -ExecutionPolicy Bypass -File desktop/setup-windows.ps1 --check
powershell -NoProfile -ExecutionPolicy Bypass -File desktop/setup-windows.ps1 --demo
```

The Windows wrapper prefers x64 Python 3.12; `STK_SETUP_PYTHON` overrides it. The `--check` mode
verifies Git, VS2022 C++ tools and the Windows SDK headers/x64 libraries/resource compiler before
any dependencies are installed. It writes a diagnostic log but does not install system tools.

These scripts create a private venv, install CMake/Ninja and pinned vcpkg dependencies, build only
`stk-desktop`, then open its main window with the prepared Python bridge. Re-run for an incremental
build, use `--launch-only` to reopen without building, or `--no-launch` to build without opening.
Use `--work-dir PATH` for a custom cache location, `--jobs N` to limit memory use, and `--dry-run`
to inspect commands. Application flags follow `--`, for example `-- --lang en --open /path/to/data`.
Command output is saved in `setup.log`. Native Mac/Windows window, GPU and IME acceptance still
needs testing on your machines.
