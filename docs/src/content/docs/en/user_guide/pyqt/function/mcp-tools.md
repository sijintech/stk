---
title: MCP Module
description: MCP Module
---
STK provides a set of tools based on the Model Context Protocol (MCP), allowing AI assistants to securely access and use the functionality in the STK toolkit. This guide will introduce how to set up and use these MCP tools.

## Feature Overview

STK MCP Server is a server implementation based on the Model Context Protocol standard, providing the following features:

- Allows AI assistants to securely access functionality in the STK toolkit
- Provides a rich set of scientific computing tools, including data processing, visualization, and simulation functions
- Supports multiple MCP-compatible clients (such as Cursor, VSCode, etc.)
- Extensible tool integration architecture
- Automatic integration of CLI commands as MCP tools

## Prerequisites

Before using STK MCP tools, you need to prepare:

- Downloaded STK codebase
- MCP-compatible client (e.g., Cursor, Claude Desktop, VSCode with MCP plugin)
- Python environment (Python 3.8 or higher recommended)

## Environment Preparation

Before using MCP tools, please ensure you have completed the following preparations:

1. Install Python environment (Python 3.10 or higher required)
2. Clone or download the STK codebase locally
3. Install STK dependencies:
   ```bash
   pip install -e .
   ```
   Or using Poetry:
   ```bash
   poetry install
   ```
4. Ensure the STK toolkit can run normally

## Usage Steps

### 1. Start the Server

After completing the environment preparation, you can start the MCP server in the following ways:

#### Method 1: Direct Start

In the terminal (Command Prompt or PowerShell), navigate to the STK project root directory, then run:

```bash
python -m suan.mcp
```

After the server starts, you will see output similar to the following:

```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

#### Method 2: Start via MCP Client

If you have already configured the MCP server in Cursor or VSCode, the client will automatically start the server when needed.

### 2. Connect to the Server

After the server starts, your MCP client (Cursor, VSCode, etc.) will automatically connect to the running server (usually at http://localhost:8000).

If the connection is successful, you will be able to use the MCP tools provided by STK in the client.

### 3. Configure in Cursor

To use STK MCP tools in Cursor, follow these steps:

1. Create a `.cursor/mcp.json` file in the project root directory.
2. Add the following content:

   ```json
   {
       "mcpServers": {
           "stk-toolkit": {
               "command": "cmd.exe",
               "args": ["/c", "python -m suan.mcp"],
               "cwd": "Your STK project path",
               "env": {
                   "PYTHONIOENCODING": "utf-8",
                   "PYTHONLEGACYWINDOWSSTDIO": "1"
               }
           }
       }
   }
   ```

3. Replace "Your STK project path" with the actual absolute path of your STK project (e.g., "D:/stk/work/stk").
4. When using the AI assistant in Cursor, it will automatically connect to the configured MCP server.
5. If you are using a Windows system, make sure to use `cmd.exe` as the command executor; if you are using Linux or macOS, modify the command and parameters accordingly.

### 4. Configure in VSCode

To use STK MCP tools in VSCode, follow these steps:

1. Install the VSCode MCP plugin (if available).
2. Create a `.vscode/mcp.json` file in the project root directory.
3. Add the following content:

   ```json
   {
     "servers": {
       "stk-toolkit": {
         "command": "cmd.exe",
         "args": ["/c", "python -m suan.mcp"],
         "cwd": "Your STK project path",
         "env": {
           "PYTHONIOENCODING": "utf-8",
           "PYTHONLEGACYWINDOWSSTDIO": "1"
         }
       }
     }
   }
   ```

4. Replace "Your STK project path" with the actual absolute path of your STK project (e.g., "D:/stk/work/stk").
5. Use the MCP plugin in VSCode to connect to the server.
6. If you are using a Windows system, make sure to use `cmd.exe` as the command executor; if you are using Linux or macOS, modify the command and parameters accordingly.

## Available Tools

The STK MCP server provides various tools, which can be categorized as follows:

### Core Tools

- `stk_info()`: Get basic information and a list of available features of the STK toolkit
- `run_stk_command(command: str)`: Run STK command-line tools
- `get_file_content(file_path: str)`: Get file content
- `list_directory(directory_path: str)`: List files and subdirectories in a directory

### Scientific Computing Tools

- `calculate_statistics(data: List[float])`: Calculate basic statistics
- `generate_plot(data: List[float], title: str, xlabel: str, ylabel: str)`: Generate simple data visualization charts

### STK Core Tools

- `run_smesh(command: str)`: Directly run smesh mesh processing tool commands
- `run_sviz(command: str)`: Directly run sviz visualization tool commands
- `run_sjob(command: str)`: Directly run sjob job management tool commands

### CLI Integration Tools

The MCP server automatically discovers and integrates existing CLI commands, with each CLI command being converted into an MCP tool named `{module_name}_{command_name}`. For example:

- The `sviz plot-scalar` command is converted to the `sviz_plot-scalar` tool
- The `smesh generate` command is converted to the `smesh_generate` tool

## Usage Examples

Here are some common MCP tool usage examples that you can use directly in MCP-supporting AI assistants.

### Basic Tool Usage

```python
# Get STK toolkit information
stk_info()

# Run STK command
run_stk_command("sviz plot-scalar --help")

# Read file content
get_file_content("example.txt")

# List directory contents
list_directory("/path/to/your/directory")
```

### Using smesh Tools

```python
# Generate mesh
run_smesh("generate --input input.json --output output.mesh")

# Or use CLI integration tool
smesh_generate(input="input.json", output="output.mesh")
```

### Using sviz Visualization Tools

```python
# Plot scalar field
run_sviz("plot-scalar --input data.vtk --output plot.png")

# Or use CLI integration tool
sviz_plot_scalar(input="data.vtk", output="plot.png")
```

### Using sjob Job Management Tools

```python
# Create job
run_sjob("create --name my_job --script job.py")

# Execute job
run_sjob("execute --name my_job")

# Or use CLI integration tool
sjob_create(name="my_job", script="job.py")
sjob_execute(name="my_job")
```

### Data Processing Examples

```python
# Calculate statistics
data = [1.2, 3.4, 5.6, 7.8, 9.0]
result = calculate_statistics(data)
print(f"Mean: {result['mean']}, Standard Deviation: {result['std']}")

# Generate chart
generate_plot(data, title="Data Analysis", xlabel="Index", ylabel="Value")
```

> **Note**: When using file paths, it is recommended to use absolute paths to avoid path resolution issues.

## Best Practices

When using STK MCP tools, please follow these best practices:

1. **Use the correct tool type**: Prefer specialized tools (such as `run_smesh`) over generic tools (such as `run_stk_command`).

2. **Provide complete paths**: When dealing with files, try to use absolute paths to avoid path resolution issues.

3. **Error handling**: Always check error messages returned by tools and adjust as needed.

4. **Resource management**: For long-running jobs, use the `sjob` tool for management instead of running them directly in the MCP session.

5. **Use CLI integration tools**: When available, prefer CLI integration tools (such as `smesh_generate`) as they provide better parameter validation and help information.

## Troubleshooting

### Security Considerations

When using STK MCP tools, please note the following security considerations:

1. **File access restrictions**: The MCP server may restrict access to certain directories; please ensure your files are in directories that are allowed to be accessed.

2. **Command execution restrictions**: Only commands in the whitelist can be executed, which by default includes `sviz`, `smesh`, and `sjob`.

3. **Timeout limits**: Long-running commands may be automatically terminated; please use `sjob` to manage long-running tasks.

4. **Parameter validation**: All tool parameters will be validated to ensure they conform to expected formats and ranges.

5. **Do not share sensitive information**: Avoid sharing sensitive information in MCP sessions, such as passwords or access tokens.

### Configuration Issues

If you encounter configuration issues:

1. Check if the paths in the `mcp.json` file are correct
2. Confirm that the Python environment and dependencies are correctly installed
3. Verify that the MCP server is running
4. View server logs for more detailed error information

Security options and other server parameters can be configured in the `suan/mcp/config.py` file.

For developer guides on adding tools, please refer to the [Developer Guide](/dev_guide/pyqt/add-mcp-tool).