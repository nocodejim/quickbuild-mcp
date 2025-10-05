@echo off
echo QuickBuild MCP Server - Test Runner
echo ====================================

echo Building test container...
docker-compose build test
if %errorlevel% neq 0 (
    echo Failed to build test container
    exit /b 1
)

echo Running tests...
docker-compose --profile test run --rm test
if %errorlevel% neq 0 (
    echo Tests failed
    exit /b 1
)

echo.
echo Tests completed successfully!
echo Coverage report available in ./coverage/htmlcov/index.html