# 仓库结构与归档边界

更新：2026-09-28。目标依据：[开发计划](development-plan.md)与[工作台设计](design/project-workbench.md)。

## 检查结论

当前顶层按桌面、Python 服务、网页和协议文档划分，适合继续实现统一项目模型与 AI 工作台，
没有必要为新界面整体改名或迁移现有包。主要问题是历史 C/C++ 工程、实验脚本和旧打包入口混在活跃代码中。
本轮已把确认不参与当前构建/运行的内容移到根目录 `archive/`，保持原始内容及来源映射。

## 活跃目录的职责

| 目录 | 当前职责 | 后续开发放置原则 |
|---|---|---|
| `desktop/` | 原生 C++ 应用、引擎、编辑器、桌面测试、打包与 Mac/Windows 启动脚本 | AI/表格/节点/预览的 UI 放在应用与 UI 库中；保留现有 GPU 渲染模块，不另建平行桌面工程 |
| `suan/` | CLI、桥、Runtime、控制服务、数据、节点求值与科学服务 | 共享项目与计算语义留在无 UI 依赖的服务层；不要分别在 AI、表格和节点编辑器保存业务状态 |
| `toolkits/` | CLI 与科学代码仍使用的 Python 工具 | 保留公开入口和数据夹具；新通用处理优先复用 `suan/data`、`suan/analysis`、`suan/graph` |
| `web/` | 控制服务网页/PWA 与网页查看器 | 继续使用已有服务契约；原生 AI 页面不因此另起一个全栈应用 |
| `docs/design/`、`docs/specs/` | 设计提案与已发布协议 | 保持两者区别；未实现的项目数据库方案不作为已冻结协议发布 |
| `docs/src/` 等站点文件 | 仍由发布工作流构建的 Astro 文档站，含旧 Qt 说明 | 更新站点导航属于后续文档工作，不因内容旧就移动整个站点 |
| `tests/` | Python/协议/集成与打包测试 | 新项目持久化、引用和批次执行验证接入这里；桌面 C++ 测试留在 `desktop/tests/` |
| `examples/`、`deploy/` | 可执行工作流示例与部署配置 | 与 Runtime/客户端行为一同维护 |
| `plugins/` | 可选 Synorder 集成 | 暂缓不等于无用；保留独立可选依赖，不加入主流程必需依赖 |
| `archive/` | 不参与当前产品构建的历史文件 | 保留来源、理由与恢复说明；新功能不从这里导入代码 |

## 本轮归档与保留依据

[归档索引](../archive/README.md)和[机器可读清单](../archive/manifest.json)列出全部原路径及目标路径。
归档判断检查了 Python 包映射/入口、导入、CLI 动态发现、CMake、CI、测试与文档引用。
这说明内容不参与当前 STK 主线，不表示其中科学算法没有未来参考价值。

以下内容看似旧，但仍需保留：

- `toolkits/sjob`、`smesh`、`sviz`：`suan/cli/main.py` 动态发现它们；`suan/visualization` 和科学测试
  仍使用可视化工具；`structure_generator`、`stk_data` 仍是显式打包的公开包。
  特别是 `toolkits/sviz/test/` 中的数据仍被当前 DAT 和分析回归测试引用。
- `suan/gui/`：`suan-gui`、Qt 打包工具与桌面兼容测试仍在；按既定计划，完整归档要通过替代能力验收。
  本轮只移走未使用的备份/实验，不删除 Qt 功能。
- `.github/workflows/release_stk_app.yml`、`suan/scripts/`、`poetry.lock`：手动旧 Qt 发布入口仍有关联。
  退出旧 Qt 支持时一并核对，不能只移动其中一个造成悬空调用。
- `desktop/spike/`：虽名为原型，仍由 `STK_DESKTOP_BUILD_SPIKE` CMake 选项构建，不能按目录名判断无用。
- `docs/` 的 Astro 配置、资源和锁文件：`publish_docs.yml` 仍调用其构建/发布。
- `desktop/engine/third_party/`：原生引擎的真实依赖与许可证，不属于历史归档。

## 下一阶段的模块边界

P1 可考虑新增 `suan/project/`，集中项目存储、统一修改命令、稳定引用和轻量依赖求值；
桌面通过桥访问。具体语言/进程归属仍按[项目模型提案](design/project-model.md)在 P1 确定，
本轮不建立空包或承诺尚未选定的接口。

AI 编排以后通过同一项目服务与 Runtime 操作；通用表格的字段展示/编辑属于 `desktop` UI，
字段类型和校验语义属于共享模型。分析重活继续复用 `suan/graph`、`suan/data` 与现有 worker。
这样可以实现新目标，同时保留现有的 Python 包路径、客户端协议和原生构建入口。

之后每次归档都应更新清单、检查引用、验证受影响入口及发布物；不把 archive 加入模块搜索路径、
包扫描或默认测试收集范围。归档源码内部的历史说明保留原样，不当作当前安装指导。

## 本轮验证

- 按归档前 Git 对象逐个校验 644 个文件，内容字节一致，原路径已移除。
- `tests/test_packaging.py`、`test_science.py`、`test_data_dat.py`、`test_analysis_labels.py`：
  41 项通过，1 项性能基准按默认配置跳过。
- `desktop/tests/test_setup.py`：13 项通过，Windows PowerShell 集成项在 Linux 上跳过。
- 构建 sdist，并从 sdist 构建 wheel；两种发布物均不包含归档内容，仍包含当前科学包和 Qt 兼容资源。
- 从 wheel 解包目录、在源码目录外验证公开包导入、CLI 帮助与桌面桥入口。
- 文档本地链接和 Git 差异格式检查通过。本轮未修改 C++ 源码或 CMake，未重新执行完整原生/GPU 验收。
