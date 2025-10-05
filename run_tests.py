#!/usr/bin/env python3
"""
Test runner script that uses Docker containers to run tests
"""
import subprocess
import sys
import os

def run_command(cmd, description):
    """Run a command and handle errors"""
    print(f"\n🔄 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed successfully")
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed")
        if e.stdout:
            print("STDOUT:", e.stdout)
        if e.stderr:
            print("STDERR:", e.stderr)
        return False

def main():
    """Run tests in Docker container"""
    print("QuickBuild MCP Server - Docker Test Runner")
    print("=" * 50)
    
    # Create coverage directory
    os.makedirs("coverage", exist_ok=True)
    
    # Build test container
    if not run_command("docker-compose build test", "Building test container"):
        sys.exit(1)
    
    # Run tests
    if not run_command("docker-compose --profile test run --rm test", "Running tests with coverage"):
        print("\n❌ Tests failed! Check the output above for details.")
        sys.exit(1)
    
    print("\n🎉 All tests passed!")
    print("\n📊 Coverage report generated in ./coverage/htmlcov/index.html")
    print("📋 To view coverage report, open ./coverage/htmlcov/index.html in your browser")
    
    # Show coverage summary if available
    coverage_file = "coverage/htmlcov/index.html"
    if os.path.exists(coverage_file):
        print(f"\n✅ Coverage report available at: {os.path.abspath(coverage_file)}")

if __name__ == "__main__":
    main()