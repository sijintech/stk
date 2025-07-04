#!/usr/bin/env python3
"""
STK MCP Server 入口点
"""

import sys
from suan.mcp.server import run_server

if __name__ == "__main__":
    sys.exit(run_server())
