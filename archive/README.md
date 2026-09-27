# 历史代码与实验归档

本目录保存已退出当前构建/运行路径的历史内容，供查阅与有选择地复用。
2026-09-28 从主线原路径移动；原始文件内容和目录内部结构保持不变。
精确映射、文件数及移动前提交见 [manifest.json](manifest.json)。

| 原路径 | 归档位置 | 归档依据 |
|---|---|---|
| `toolkits/cpp/` | [legacy/toolkits/cpp/](legacy/toolkits/cpp/) | 旧 C/C++ 工具、求解器、结构生成器与 EffectiveProperties 工程；不被当前 `desktop/CMakeLists.txt` 引用，此前已排除在 Python 打包外 |
| `toolkits/smesh/src/new_package/` | [legacy/toolkits/smesh/src/new_package/](legacy/toolkits/smesh/src/new_package/) | 未接入 CLI/节点的结构生成实验；当前 smesh 使用另一个 `structure_generator` 包 |
| `install.ps1` | [legacy/install.ps1](legacy/install.ps1) | 保存的 Scoop 安装器，不是当前 STK Windows 启动脚本；旧文档/工作流中的同名文件由下载步骤生成 |
| `.github/workflows/release_cli.yml` | [legacy/.github/workflows/release_cli.yml](legacy/.github/workflows/release_cli.yml) | 两个平台构建 job 都已设为 `if: false`，发布 job 依赖它们；停止保留无效的活跃工作流入口 |
| `suan/cli/setup.py`、`main.spec` | [legacy/suan/cli/](legacy/suan/cli/) | 旧独立 CLI 打包方案；当前入口和打包由根 `pyproject.toml` 管理，旧 spec 仅被上述停用工作流引用 |
| `suan/gui/info_bar.py.1.bak.py` | [legacy/suan/gui/info_bar.py.1.bak.py](legacy/suan/gui/info_bar.py.1.bak.py) | 未被导入的手工备份，正式模块仍在 `suan/gui/info_bar.py` |
| `suan/gui/testpython.py` | [legacy/suan/gui/testpython.py](legacy/suan/gui/testpython.py) | 未被调用的独立 AI/PDF 实验脚本，不是当前或计划中 AI 工作区实现 |

归档源码不进入 wheel/sdist，不加入当前构建，也不作为自动测试收集目录。
归档工作流离开 `.github/workflows/` 后不会被 GitHub Actions 发现。
内容未经重新适配，可能含过期依赖、相对路径或历史网络地址；归档不承诺可直接运行。
要恢复使用，先按清单核对原位置与依赖，再作为正常开发变更接回当前项目；不要直接执行旧发布脚本。
原有许可证与第三方声明随文件保留。

仍在使用的 Python 科学工具、Qt 兼容客户端、手动 Qt 打包入口和文档站点未归档；
原因及后续目录规划见[仓库结构说明](../docs/repository-structure.md)。
更早的 Blender 与 Rust 原型保留在已有 `archive/*` Git 标签中，无需再复制到这里。
