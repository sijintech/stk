# STK 应用打包指南

## 添加新的第三方库到 STK 打包过程

当需要在 STK 应用中使用新的第三方库并确保其在打包后的应用中正常工作时，请按照以下步骤操作：

### 1. 使用 Poetry 添加依赖

首先，使用 Poetry 在开发环境中安装并添加所需的第三方库到项目依赖中：

```bash
poetry add 库名称
```

### 2. 更新 pyproject.toml 配置

STK 项目使用 `pyproject.toml` 作为依赖管理的单一真实来源。在添加新库后，确保为 PyInstaller 添加相关配置：

```toml
# 在 [tool.pyinstaller.hidden_imports] 中添加新库
[tool.pyinstaller]
hidden_imports = [
    # ...现有隐藏导入...
    "新库名称",
    "新库名称.子模块"
]

# 为复杂库添加专门的配置部分
[tool.pyinstaller.新库名称]
modules = [
    "需要导入的子模块1",
    "需要导入的子模块2"
]
```

### 3. 使用内置的钩子生成器

STK 提供了自动生成 PyInstaller 钩子文件的工具。使用该工具为新添加的库生成钩子：

```bash
# 生成指定库的钩子
poetry run generate-hooks --hook 新库名称

# 或生成所有钩子
poetry run generate-hooks --all
```

### 4. 为特殊库创建自定义钩子

对于需要特殊处理的库，您可能需要手动创建或编辑钩子文件。钩子文件应放在 `suan/gui/pkg_tools/hooks/` 目录下

常见的钩子内容包括：

#### 处理数据文件

```python
# 收集数据文件
datas = collect_data_files('新库名称', includes=['*.json', '*.yml'])

# 或手动指定数据文件
datas = [
    ('path/to/data/file', '目标相对路径')
]
```

#### 处理二进制文件

```python
# 收集二进制依赖
binaries = collect_dynamic_libs('新库名称')

# 或手动指定二进制文件
binaries = [
    ('path/to/binary/file', '目标相对路径')
]
```

### 5. 使用内置打包工具测试

使用 STK 提供的打包工具测试新添加的库是否能正确打包：

```bash
# 基本打包
poetry run build-app

# 调试模式打包，提供更详细的日志
poetry run build-app --debug

# 清理后打包
poetry run build-app --clean
```

### 6. 故障排除

如果打包后遇到与新库相关的问题：

1. 检查应用日志中与新库相关的错误信息
2. 检查 PyInstaller 的构建日志（在 `build_logs` 目录下）
3. 查看 `builder.py` 中的 `check_dependencies` 函数，确保新库已被正确检测
4. 使用 `--debug` 选项重新打包获取更详细的日志
5. 检查生成的钩子文件是否正确处理了库的所有依赖

#### 常见问题解决方法

##### 1. 找不到模块错误

这通常是因为隐藏导入配置不完整。在 `pyproject.toml` 中添加缺失的模块：

```toml
[tool.pyinstaller]
hidden_imports = [
    # ...现有隐藏导入...
    "缺失的模块"
]
```

然后重新生成钩子文件并打包。

##### 2. 找不到数据文件错误

需要在钩子文件中正确收集数据文件：

```python
# 在 hook-新库名称.py 中
datas = collect_data_files('新库名称', subdir='data_dir')
```

##### 3. 二进制兼容性问题

对于包含预编译二进制的库，确保收集所有所需的二进制文件和依赖项：

```python
# 在 hook-新库名称.py 中
binaries = []
if is_windows:
    binaries.extend([('path/to/windows/dll', '.')])
elif is_macos:
    binaries.extend([('path/to/macos/dylib', '.')])
else:  # Linux
    binaries.extend([('path/to/linux/so', '.')])
```

