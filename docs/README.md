# STK 文档

本目录同时保存开发设计文档和 Astro/Starlight 文档站。

- 第一次使用：[Linux 快速上手](quickstart-linux.md)（文档站同名页面直接引用该文件）。
- 当前开发方向：[开发计划](development-plan.md)、[项目工作台设计](design/project-workbench.md)。
- 可测试能力：[项目表格指南](project.md)、[验收记录](runtime-validation.md)、[开发交接记录](development-log.md)。
- 版本化技能目录（实验契约 `stk.skill/1`）：[技能目录](skills.md)。
- 文档站页面在 `src/content/docs/`，英文页面在其 `en/` 子目录；根目录设计文档不会自动成为站点页面。
- 图片在 `src/assets/`，静态文件在 `public/`；`dist/` 为生成文件，不提交。

## 本地构建

使用 `docs/.node-version` 指定的 Node 22 和 `package.json` 指定的 pnpm 8.15.9。
从仓库根目录执行：

```sh
npm install --global pnpm@8.15.9
cd docs
pnpm install --frozen-lockfile
pnpm run build
```

构建包含 Astro 类型检查、静态页面、图片优化和 Pagefind 搜索索引。
确认 `dist/index.html`、`dist/en/index.html` 和 `dist/pagefind/pagefind.js` 已生成。
本地开发用 `pnpm run dev`；预览生成站点用 `pnpm run preview`，默认仅监听本机。

依赖以 `pnpm-lock.yaml` 为准，不用 `npm install` 重新解析另一套版本。
需要修改依赖时用同版本 pnpm 更新并提交锁文件；CI 使用 `--frozen-lockfile` 拒绝漂移。
`tsconfig.json` 排除生成目录，重复构建不会对上次输出的压缩 JS 做源码类型检查。

## 发布

`main` 上的文档变更由 `.github/workflows/publish_docs.yml` 构建并发布到既有 Cloudflare Pages 项目。
发布凭据保留在 GitHub Secrets，不写入文档或本地配置。修复构建不等于已经验证部署；以该提交的工作流结果为准。

2026-09-28 已在隔离目录用锁定依赖和 Node 22 构建 36 个页面，Pagefind 索引 35 个页面、两种语言。
这修复了此前 Node 18、未使用锁文件时 Astro 依赖加载的 `ERR_REQUIRE_ESM`。
Node 的同步 ESM 加载行为见[官方模块文档](https://nodejs.org/download/release/v22.13.1/docs/api/modules.html#loading-ecmascript-modules-using-require)。
