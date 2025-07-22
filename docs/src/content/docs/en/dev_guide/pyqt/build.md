---
title: STK Application Packaging Guide
description: Guide for packaging STK applications
---

# STK Application Packaging Guide

## Adding New Third-Party Libraries to STK Packaging Process

When you need to use a new third-party library in the STK application and ensure it works properly in the packaged application, follow these steps:

### 1. Add Dependencies Using Poetry

First, install and add the required third-party library to the project dependencies in the development environment using Poetry:

```bash
poetry add library-name
```

### 2. Update pyproject.toml Configuration

STK project uses `pyproject.toml` as the single source of truth for dependency management. After adding a new library, ensure you add relevant configuration for PyInstaller:

```toml
# Add the new library in [tool.pyinstaller.hidden_imports]
[tool.pyinstaller]
hidden_imports = [
    # ...existing hidden imports...
    "new-library-name",
    "new-library-name.submodule"
]

# Add a dedicated configuration section for complex libraries
[tool.pyinstaller.new-library-name]
modules = [
    "submodule1-to-import",
    "submodule2-to-import"
]
```

### 3. Use the Built-in Hook Generator

STK provides a tool to automatically generate PyInstaller hook files. Use this tool to generate hooks for newly added libraries:

```bash
# Generate hooks for a specific library
poetry run generate-hooks --hook new-library-name

# Or generate all hooks
poetry run generate-hooks --all
```

### 4. Create Custom Hooks for Special Libraries

For libraries that require special handling, you may need to manually create or edit hook files. Hook files should be placed in the `suan/gui/pkg_tools/hooks/` directory.

Common hook content includes:

#### Handling Data Files

```python
# Collect data files
datas = collect_data_files('new-library-name', includes=['*.json', '*.yml'])

# Or manually specify data files
datas = [
    ('path/to/data/file', 'target-relative-path')
]
```

#### Handling Binary Files

```python
# Collect binary dependencies
binaries = collect_dynamic_libs('new-library-name')

# Or manually specify binary files
binaries = [
    ('path/to/binary/file', 'target-relative-path')
]
```

### 5. Test Using Built-in Packaging Tools

Use the packaging tools provided by STK to test whether the newly added library can be correctly packaged:

```bash
# Basic packaging
poetry run build-app

# Debug mode packaging, providing more detailed logs
poetry run build-app --debug

# Clean and package
poetry run build-app --clean
```

### 6. Troubleshooting

If you encounter problems related to the new library after packaging:

1. Check the application logs for error messages related to the new library
2. Check PyInstaller's build logs (in the `build_logs` directory)
3. Look at the `check_dependencies` function in `builder.py` to ensure the new library has been correctly detected
4. Use the `--debug` option to repackage and get more detailed logs
5. Check if the generated hook file correctly handles all dependencies of the library

#### Common Problem Solutions

##### 1. Module Not Found Error

This is usually because the hidden import configuration is incomplete. Add the missing module in `pyproject.toml`:

```toml
[tool.pyinstaller]
hidden_imports = [
    # ...existing hidden imports...
    "missing-module"
]
```

Then regenerate the hook files and package again.

##### 2. Data File Not Found Error

You need to correctly collect data files in the hook file:

```python
# In hook-new-library-name.py
datas = collect_data_files('new-library-name', subdir='data_dir')
```

##### 3. Binary Compatibility Issues

For libraries containing pre-compiled binaries, ensure you collect all required binary files and dependencies:

```python
# In hook-new-library-name.py
binaries = []
if is_windows:
    binaries.extend([('path/to/windows/dll', '.')])
elif is_macos:
    binaries.extend([('path/to/macos/dylib', '.')])
else:  # Linux
    binaries.extend([('path/to/linux/so', '.')])
```