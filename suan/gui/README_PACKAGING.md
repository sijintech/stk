# STK GUI 打包指南

本文档提供了 STK GUI 应用程序的打包指南和常见问题排除方法。

## 打包流程

STK GUI 应用程序使用 PyInstaller 进行打包，并结合 Poetry 进行依赖管理。整个打包流程已经自动化，可以通过以下步骤进行：

### 1. 安装依赖

```bash
# 使用 Poetry 安装依赖
poetry install

# 或者使用 pip 安装关键依赖
pip install -r requirements.txt
```

### 2. 自动化打包

```bash
# 使用基于 Poetry 的打包脚本
cd suan/gui
python build_with_poetry.py

# 或者直接使用 Poetry 脚本命令
poetry run build-app
```

### 3. 手动打包

如果需要手动控制打包过程，可以执行以下操作：

```bash
# 先更新依赖
python update_dependencies.py

# 然后运行 PyInstaller
pyinstaller main.spec
```

## 依赖管理

项目使用 Poetry 进行依赖管理。关键依赖项在 `pyproject.toml` 文件中定义。

### 更新依赖

当引入新的外部库时，需要更新依赖列表：

1. 在代码中导入并使用新库
2. 运行 `python update_dependencies.py` 自动扫描并更新依赖
3. 检查 `pyproject.toml` 是否已包含新依赖，如果没有，手动添加

### 重要依赖项

以下是项目的关键依赖项，这些项会被自动包含在打包中：

- PySide6: GUI框架
- vtk: 可视化工具包
- matplotlib: 绘图库
- numpy: 数值计算库
- pandas: 数据分析库
- requests: HTTP请求库
- toml: 配置文件解析库

## 常见问题与解决方案

### 1. "No module named X" 错误

**问题**: 打包后的应用程序无法找到某个模块。

**解决方案**:
- 检查该模块是否在 `pyproject.toml` 中列出
- 在 `main.spec` 文件中的 `hiddenimports` 列表中添加该模块
- 运行 `update_dependencies.py` 重新生成依赖并更新 spec 文件

### 2. VTK 相关问题

**问题**: VTK 组件加载失败。

**解决方案**:
- 确保在 `hiddenimports` 中包含了 `vtkmodules.all` 和 `vtkmodules.util`
- 在 hooks 目录中创建 `hook-vtk.py` 文件，内容为：
  ```python
  from PyInstaller.utils.hooks import collect_submodules
  hiddenimports = collect_submodules('vtkmodules')
  ```

### 3. PySide6 资源问题

**问题**: PySide6 相关的图标、样式或插件无法加载。

**解决方案**:
- 确保 PySide6 的相关资源被正确包含
- 在 `main.spec` 的 `datas` 中添加：
  ```python
  datas = [
      # ... 其他数据 ...
      # PySide6 资源
      (site_packages + '/PySide6/plugins/platforms', 'platforms'),
      (site_packages + '/PySide6/plugins/styles', 'styles'),
  ]
  ```

### 4. 打包后的应用程序崩溃

**问题**: 应用程序在启动时或执行某些操作时崩溃。

**解决方案**:
- 临时将 `console=True` 以查看错误输出
- 使用 `try-except` 块包装主要功能，记录错误到日志文件
- 检查是否有任何依赖冲突或版本不兼容问题

## 进阶技巧

### 1. 缩小打包体积

- 使用 `--exclude-module` 排除不必要的模块
- 使用 UPX 压缩可执行文件和库（在 `main.spec` 中已配置）
- 考虑使用 `--onefile` 而非 `--onedir` 模式

### 2. 多平台打包

不同平台需要注意的特殊问题：

- **Windows**:
  - 确保 Microsoft Visual C++ Redistributable 已安装
  - 检查 DLL 依赖并包含必要的 DLL 文件

- **macOS**:
  - 需要签名才能避免 Gatekeeper 警告
  - 使用 `--osx-bundle-identifier` 设置应用标识符

- **Linux**:
  - 考虑 AppImage 或 Snap 包装格式
  - 检查动态库依赖并确保它们在目标系统上可用

## 自定义钩子

为了处理特殊依赖，项目使用了自定义 PyInstaller 钩子，位于 `hooks` 目录。如果需要为新的复杂依赖创建钩子，请参考 PyInstaller 文档。

## 自动化构建

项目配置了 GitHub Actions 工作流，可以自动构建和发布应用程序。详情请参考 `.github/workflows/release_stk_app.yml` 文件。

## 维护建议

1. 定期更新依赖以确保安全和功能改进
2. 每次重大更新后在不同平台测试应用程序
3. 保持 `pyproject.toml` 和 `main.spec` 文件的同步更新 