# STK 应用打包工具

这个目录包含了 STK 应用的打包工具和相关脚本，实现了依赖管理、钩子生成和应用打包的自动化流程。

## 目录结构

- `__init__.py` - 包初始化文件
- `builder.py` - 主要打包脚本
- `dependencies.py` - 依赖提取和管理工具
- `hooks_generator.py` - 自动生成 PyInstaller 钩子文件的工具
- `hooks/` - 放置 PyInstaller 钩子文件的目录

## 使用方法

### 打包应用

使用 Poetry 命令直接运行打包脚本:

```bash
# 基本用法
poetry run build-app

# 清理旧的构建文件再打包
poetry run build-app --clean

# 调试模式打包
poetry run build-app --debug

# 使用控制台模式打包
poetry run build-app --console
```

或者直接运行 Python 模块:

```bash
python -m suan.gui.packaging.builder [参数]
```

### 生成钩子文件

```bash
# 生成所有钩子文件
poetry run generate-hooks --all

# 生成指定的钩子文件
poetry run generate-hooks --hook matplotlib
```

### 提取依赖信息

```bash
# 默认列表格式输出
poetry run extract-deps

# JSON 格式输出
python -m suan.gui.packaging.dependencies --format=json

# 输出到文件
python -m suan.gui.packaging.dependencies --format=json --output=deps.json
```

## 单一真实来源策略

所有依赖配置只在 `pyproject.toml` 一处定义，包含:

- GUI 组件
- 第三方库依赖
- 按库分类的特定模块配置

这种设计确保了依赖管理的一致性，避免了配置分散导致的维护问题。 