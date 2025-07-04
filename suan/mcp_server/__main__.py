#!/usr/bin/env python3
"""
STK MCP Server 主入口点 - CLI集成版本
动态发现并集成现有CLI命令的科学工具包MCP服务器

用法:
    python -m suan.mcp_server
"""

import asyncio
import sys
from .cli_integrated_server import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped by user", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
