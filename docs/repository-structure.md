# 仓库结构与归档边界

更新：2026-09-28。目标依据：[开发计划](development-plan.md)与[工作台设计](design/project-workbench.md)。

## 检查结论

当前顶层按桌面、Python 服务、网页和协议文档划分，适合继续实现统一项目模型与 AI 工作台，
无需整体重组；其中 `toolkits/` 与 `suan/` 的功能边界需要按下述讨论决定逐步整合。
已完成的整理是将不参与当前构建/运行的历史 C/C++ 工程、实验脚本和旧打包入口移到根目录 `archive/`，
保持原始内容及来源映射。仍在使用的 Python 工具尚未迁移。

## 活跃目录的职责

| 目录 | 当前职责 | 后续开发放置原则 |
|---|---|---|
| `desktop/` | 原生 C++ 应用、引擎、编辑器、桌面测试、打包与 Mac/Windows 启动脚本 | AI/表格/节点/预览的 UI 放在应用与 UI 库中；保留现有 GPU 渲染模块，不另建平行桌面工程 |
| `suan/` | CLI、桥、Runtime、控制服务、数据、节点求值与科学服务 | 共享项目与计算语义留在无 UI 依赖的服务层；不要分别在 AI、表格和节点编辑器保存业务状态 |
| `toolkits/` | CLI 与科学代码仍使用的 Python 工具，处于待整合状态 | 按职责迁入 `suan/`，保留过渡兼容；验收完成后取消独立顶层目录 |
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
  特别是 `toolkits/sviz/test/` 中的数据仍被当前 DAT 和分析回归测试引用。这是迁移完成前的保留依据，
  不意味着长期维持两个功能目录。
- `suan/gui/`：`suan-gui`、Qt 打包工具与桌面兼容测试仍在；按既定计划，完整归档要通过替代能力验收。
  本轮只移走未使用的备份/实验，不删除 Qt 功能。
- `.github/workflows/release_stk_app.yml`、`suan/scripts/`、`poetry.lock`：手动旧 Qt 发布入口仍有关联。
  退出旧 Qt 支持时一并核对，不能只移动其中一个造成悬空调用。
- `desktop/spike/`：虽名为原型，仍由 `STK_DESKTOP_BUILD_SPIKE` CMake 选项构建，不能按目录名判断无用。
- `docs/` 的 Astro 配置、资源和锁文件：`publish_docs.yml` 仍调用其构建/发布。
- `desktop/engine/third_party/`：原生引擎的真实依赖与许可证，不属于历史归档。

## 2026-09-28 讨论决定：将 toolkits 整合进 suan

状态：已确定的后续开发方向，尚未实施代码迁移。迁移按职责拆分，具体新模块名与兼容期在实现时确定。

历史上没有 `desktop/`，`suan/` 是用户界面，`toolkits/` 是背后的功能插件集合。
现在原生界面进入 `desktop/`，`suan/` 已发展为主要 Python 功能与服务层，原来的目录边界不再清晰。
现有代码也存在双向依赖：`suan/visualization/scene.py` 使用 `toolkits.sviz.field`，后者的 DAT 读取
又调用 `suan.data.dat`。因此后续将仍有用的工具按职责并入 `suan/`，最终取消独立顶层 `toolkits/`。

| 现有功能 | 目标归属（新模块名为建议） | 整合原则 |
|---|---|---|
| `sjob` 参数扫描、批次输入生成 | `suan/batch/` | 将批次准备与执行分离；提交、监控和调度复用 `suan/runtime/`，不保留第二套调度器 |
| `smesh` 结构生成 | `suan/structure/` | 统一结构生成能力，核对现有 `structure_generator`、`stk_data` 的公开接口和实际职责 |
| `sviz` 文件读取与转换 | `suan/data/` | 复用已有读取器，明确格式与行为差异，消除重复实现 |
| `sviz` 科学分析、二维绘图、可视化辅助 | `suan/analysis/`、`suan/plot/`、`suan/visualization/` | 按功能拆分，保留必要资源；3D 原生渲染仍在 `desktop/` |
| 工具示例、测试数据、独立实验 | `examples/`、测试夹具、`archive/` | 有效示例与回归数据随功能迁移，未使用实验单独归档 |

插件能力由注册接口和类型契约提供，不依赖 `toolkits/` 目录。内置功能放在 `suan/`，后续通过共同接口
注册为节点、表格字段、预览或 AI 工具；外部扩展使用相同契约。`plugins/` 保留可选外部集成的定位，
当前 Synorder 插件不等同于未来通用节点/字段插件框架已经实现。

迁移要求：

1. 先列出导入、CLI 自动发现、MCP、旧 Qt、可选插件、资源路径及打包入口的依赖清单，确定行为基线。
2. 分批整合并消除重复实现，不把整个 `toolkits/` 简单改名为 `suan/toolkits/`。
3. 保持 `suan sjob`、`suan smesh`、`suan sviz` 命令可用；已有 Python 导入路径提供过渡兼容，
   显式评估 `toolkits.*`、`structure_generator` 和 `stk_data` 的使用者。兼容层只转发到新实现，避免两份逻辑。
4. 更新 CLI 注册/发现、MCP、Qt 调用、示例与测试、Poetry 包映射和资源定位；检查 wheel/sdist 的实际内容，
   并在源码目录外验证公开入口。保留可选依赖的延迟加载，基础 CLI 不应因此强制安装完整科学或 Qt 环境。
5. 功能与打包验收、旧入口兼容/退役安排完成后，再移除顶层 `toolkits/`；不能提前删除仍被引用的代码。

长期分工为：`desktop/` 提供原生界面，`suan/` 提供共享功能与服务，`plugins/` 提供可选外部扩展，
`archive/` 保存历史实现；`web/` 继续作为共享服务的网页客户端。本决定不改变 Qt 归档的独立验收门槛。

## 下一阶段的模块边界

P1 已新增 `suan/project/`，实现独立于 UI 的 Python 项目存储与原子修改命令，
提供 `suan project` CLI 验证入口，见[项目存储指南](project.md)。后续通过桥接入桌面，
继续补齐稳定引用、轻量求值和表格生命周期；不在 C++ 编辑器中复制数据库写入规则。

AI 编排以后通过同一项目服务与 Runtime 操作；通用表格的字段展示/编辑属于 `desktop` UI，
字段类型和校验语义属于共享模型。分析重活继续复用 `suan/graph`、`suan/data` 与现有 worker。
这样可以实现新目标；内部 Python 包路径按上述方向迁移，公开入口提供过渡兼容，
客户端协议和原生构建入口继续沿用。

之后每次归档都应更新清单、检查引用、验证受影响入口及发布物；不把 archive 加入模块搜索路径、
包扫描或默认测试收集范围。归档源码内部的历史说明保留原样，不当作当前安装指导。

## 已完成归档整理的验证

- 按归档前 Git 对象逐个校验 644 个文件，内容字节一致，原路径已移除。
- `tests/test_packaging.py`、`test_science.py`、`test_data_dat.py`、`test_analysis_labels.py`：
  41 项通过，1 项性能基准按默认配置跳过。
- `desktop/tests/test_setup.py`：13 项通过，Windows PowerShell 集成项在 Linux 上跳过。
- 构建 sdist，并从 sdist 构建 wheel；两种发布物均不包含归档内容，仍包含当前科学包和 Qt 兼容资源。
- 从 wheel 解包目录、在源码目录外验证公开包导入、CLI 帮助与桌面桥入口。
- 文档本地链接和 Git 差异格式检查通过。本轮未修改 C++ 源码或 CMake，未重新执行完整原生/GPU 验收。
