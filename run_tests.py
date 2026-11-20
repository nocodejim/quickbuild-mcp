#!/usr/bin/env python3
"""
Test runner script that uses Docker containers to run tests
"""
import os
import shutil
import subprocess
import sys


def detect_compose_cmd() -> str:
    """Detect whether 'docker compose' or legacy 'docker-compose' is available."""
    try:
        subprocess.run(
            ["docker", "compose", "version"],
            check=True,
            capture_output=True,
            text=True,
        )
        return "docker compose"
    except (subprocess.CalledProcessError, FileNotFoundError):
        if shutil.which("docker-compose"):
            return "docker-compose"
    return "docker compose"


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

    compose_cmd = detect_compose_cmd()
    os.makedirs("coverage", exist_ok=True)

    if not run_command(f"{compose_cmd} build test", "Building test container"):
        sys.exit(1)

    if not run_command(
        f"{compose_cmd} --profile test run --rm test", "Running tests with coverage"
    ):
        print("\n❌ Tests failed! Check the output above for details.")
        sys.exit(1)

    print("\n🎉 All tests passed!")
    print("\n📊 Coverage report generated in ./coverage/index.html")

    coverage_file = "coverage/index.html"
    if os.path.exists(coverage_file):
        print(f"\n✅ Coverage report available at: {os.path.abspath(coverage_file)}")


if __name__ == "__main__":
    main()
