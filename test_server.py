#!/usr/bin/env python3
"""
Simple test script to verify QuickBuild MCP Server functionality
"""
import asyncio
import os
import sys
sys.path.insert(0, 'src')

from src.quickbuild_client import QuickBuildClient
from src.server import QuickBuildMCPServer

async def test_quickbuild_connection():
    """Test basic QuickBuild connection"""
    print("Testing QuickBuild connection...")
    
    # Check environment variables
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
        client = QuickBuildClient()
        await client.authenticate()
        print("✓ Authentication successful")
        
        # Test configurations
        configs = await client.get_configurations()
        print(f"✓ Retrieved {len(configs)} configurations")
        
        await client.close()
        return True
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False

async def test_server_setup():
    """Test MCP server setup"""
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

async def main():
    """Run all tests"""
    print("QuickBuild MCP Server Test Suite")
    print("=" * 40)
    
    # Test QuickBuild connection
    qb_ok = await test_quickbuild_connection()
    
    # Test server setup
    server_ok = await test_server_setup()
    
    print("\n" + "=" * 40)
    if qb_ok and server_ok:
        print("✓ All tests passed! Server is ready to run.")
        print("\nTo start the server:")
        print("  docker-compose up -d")
        print("  # or")
        print("  python -m src.server")
    else:
        print("❌ Some tests failed. Check configuration and try again.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())