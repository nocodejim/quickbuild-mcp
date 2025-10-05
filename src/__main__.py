"""
Entry point for running the QuickBuild MCP Server
"""
import asyncio
from .server import main

if __name__ == "__main__":
    asyncio.run(main())