---
title: Adding MCP Tools
description: How to add new tools to the STK MCP server
---

This guide explains how to add new tools to the STK MCP server.

## Prerequisites

- Understanding of Python asynchronous functions
- Familiarity with the MCP protocol
- Access to STK source code

## Methods for Adding Tools

There are two main methods to add new tools to the STK MCP server:

1. Direct tool method addition
2. Adding tools through CLI integration

## Method 1: Direct Tool Method Addition

### Steps

1. Locate the server file: `suan/mcp/server.py`

2. Add a new function decorated with `@mcp.tool()`:

   ```python
   @mcp.tool()
   async def new_tool_example(param1: str, param2: int = 0) -> str:
       """ 
       Description of the new tool

       Args:
           param1: Description of param1
           param2: Description of param2 (optional)
       """
       # Implement here
       try:
           # Your code
           return "result"
       except Exception as e:
           return f"Error: {str(e)}"
   ```

3. Ensure security:
   - Validate inputs
   - Restrict file access to the working directory
   - Handle exceptions properly

## Method 2: Adding Tools Through CLI Integration

The STK MCP Server can automatically discover and integrate existing CLI commands, allowing AI assistants to directly call these scientific computing functions. The advantage of this method is that you can easily convert existing command-line tools into MCP tools without writing additional code.

### How It Works

1. The MCP server automatically scans and discovers CLI commands in the project when it starts (through the `discover_and_integrate_cli` function in `cli_integration.py`)
2. Extracts command and parameter information (name, help information, whether required, default value, etc.) from Click command groups
3. Generates an MCP tool definition for each CLI command, including tool name, description, and JSON Schema for parameters
4. Dynamically creates and registers MCP tools, making them callable through the MCP protocol
5. When an AI assistant calls a tool, parameters are converted to command-line arguments, and the corresponding command is executed
6. The command execution result is returned to the AI assistant

### Supported CLI Modules

The MCP server automatically looks for CLI commands in the following modules:

- `suan.cli.main` - Main CLI module
- `toolkits.sjob.cli` - Job management CLI
- `toolkits.smesh.cli` - Mesh processing CLI
- `toolkits.sviz.cli` - Visualization CLI

If you want to add a new CLI module, you can modify the `CLI_MODULES` list in the `CLIIntegration` class in the `suan/mcp/cli_integration.py` file.

### Tool Naming Rules

Each CLI command is converted into an MCP tool named `{module_name}_{command_name}`. For example:

- The `sviz plot-scalar` command is converted to the `sviz_plot-scalar` tool
- The `smesh generate` command is converted to the `smesh_generate` tool

For subcommands, the naming format is `{module_name}_{parent_command_name}_{subcommand_name}`.

### Adding New CLI Commands

To add new tools through CLI integration, you need to:

1. Create a Click-based CLI command:

   ```python
   # In your module (e.g., toolkits/your_tool/cli.py)
   import click
   
   @click.group()
   def cli():
       """Description of your tool"""
       pass
   
   @cli.command()
   @click.option('--input', '-i', required=True, help='Input file path')
   @click.option('--output', '-o', required=True, help='Output file path')
   def process(input, output):
       """Command to process data"""
       # Implement your command logic
       print(f"Processing {input} and saving to {output}")
   ```

2. Ensure your module is in the list of supported CLI modules (if not, modify the `CLI_MODULES` list)

3. Restart the MCP server, and your command will be automatically integrated as an MCP tool

### Configuration Options

The following options can be configured in the `suan/mcp/config.py` file:

- `ENABLE_COMMAND_EXECUTION` - Whether to enable CLI command execution (default is `True`)
- `COMMAND_TIMEOUT` - Maximum timeout for command execution (default is 60 seconds)
- `ALLOWED_COMMANDS` - Whitelist of allowed command prefixes (default is `["sviz", "smesh", "sjob"]`)

These configuration options can help you control the behavior and security of CLI integration.

## Testing New Tools

### Testing Directly Added Tools

1. Restart the MCP server:
   ```bash
   python -m suan.mcp
   ```

2. Use an MCP client (such as Cursor, Claude Desktop, or VSCode with MCP plugin) to connect to the server

3. Test your tool by calling it from the AI assistant

4. Check the server logs for any errors or issues

### Testing CLI Integration Tools

1. Ensure your CLI command works correctly when called directly from the command line

2. Restart the MCP server to discover and integrate your CLI command

3. Use an MCP client to connect to the server

4. Test your tool by calling it from the AI assistant using the integrated tool name (e.g., `your_module_your_command`)

5. Check the server logs for any errors or issues

## Debugging Tips

1. Enable debug logging in the MCP server by setting the log level to DEBUG in `suan/mcp/__main__.py`

2. Check the server logs for error messages and stack traces

3. Use print statements or logging in your tool implementation to track execution flow

4. Test your tool with simple inputs first, then gradually increase complexity

5. For CLI integration tools, test the CLI command directly from the command line first to ensure it works correctly

## Best Practices

### Security

1. Always validate user inputs to prevent injection attacks

2. Restrict file access to safe directories

3. Set appropriate timeouts for long-running operations

4. Use allowlists for commands that can be executed

5. Handle exceptions properly to avoid exposing sensitive information

### Code Quality

1. Write clear docstrings for your tools, including parameter descriptions

2. Follow Python's type hinting conventions for better IDE support

3. Keep tool functions focused on a single responsibility

4. Write unit tests for your tools to ensure they work correctly

### User Experience

1. Provide helpful error messages that guide users to fix issues

2. Return structured data when appropriate to make it easier for AI assistants to process

3. Design tool parameters to be intuitive and consistent with other tools

4. Consider providing examples in the tool's docstring

### Documenting Tools in User Guide

1. Update the user guide to include your new tool

2. Provide clear examples of how to use the tool

3. Document any limitations or special considerations

4. Include information about error handling and troubleshooting

By following these guidelines, you can create effective and secure MCP tools that enhance the capabilities of the STK toolkit.