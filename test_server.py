#!/usr/bin/env python3
"""
Simple live verification script to test QuickBuild MCP Server against a running QuickBuild instance.
"""
import asyncio
import os
import sys

from dotenv import load_dotenv

from src.quickbuild_client import QuickBuildClient
from src.server import QuickBuildMCPServer

load_dotenv()


async def check_quickbuild_connection() -> bool:
    """Verify basic QuickBuild connection"""
    print("Testing QuickBuild connection...")

    qb_url = os.getenv("QB_URL")
    qb_user = os.getenv("QB_USER")
    qb_password = os.getenv("QB_PASSWORD")

    if not all([qb_url, qb_user, qb_password]):
        print("❌ Missing required environment variables:")
        print(f"  QB_URL: {'✓' if qb_url else '❌'}")
        print(f"  QB_USER: {'✓' if qb_user else '❌'}")
        print(f"  QB_PASSWORD: {'✓' if qb_password else '❌'}")
        return False

    print(f"  QB_URL: {qb_url}")
    print(f"  QB_USER: {qb_user}")

    try:
        async with QuickBuildClient() as client:
            await client.authenticate()
            print("✓ Authentication successful")

            configs = await client.get_configurations()
            print(f"✓ Retrieved {len(configs)} configurations")
            return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False


async def check_server_setup() -> bool:
    """Verify MCP server setup"""
    print("\nTesting MCP server setup...")

    try:
        server = QuickBuildMCPServer()
        await server.setup()
        print("✓ Server setup successful")
        print(f"✓ Loaded {len(server.features)} features")
        print(f"✓ Registered {len(server.tool_handlers)} tools")
        print(f"✓ Registered {len(server.resource_handlers)} resources")

        await server.qb_client.close()
        return True
    except Exception as e:
        print(f"❌ Server setup failed: {e}")
        return False


async def main() -> None:
    """Run all live checks"""
    print("QuickBuild MCP Server Verification")
    print("=" * 40)

    qb_ok = await check_quickbuild_connection()
    server_ok = await check_server_setup()

    print("\n" + "=" * 40)
    if qb_ok and server_ok:
        print("✓ All checks passed! Server is ready to run.")
        print("\nTo start the server:")
        print("  docker compose up -d mcp-quickbuild-server")
        print("  # or")
        print("  python -m src.server")
    else:
        print("❌ Some checks failed. Check configuration and try again.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
