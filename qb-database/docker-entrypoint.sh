#!/bin/bash
# QuickBuild 14 Database Container Entrypoint
# Handles SQL Server startup and QuickBuild database initialization
# Runs initialization scripts after SQL Server is ready

set -e

# Configuration
INIT_FLAG_FILE="/var/opt/mssql/data/.qb-initialized"
INIT_SCRIPTS_DIR="/opt/mssql-scripts"
MAX_STARTUP_WAIT=120
STARTUP_CHECK_INTERVAL=5

echo "Starting QuickBuild 14 Database Container..."
echo "SQL Server Version: $(grep VERSION= /etc/os-release | cut -d'"' -f2)"

# Load secret file environment variables when provided (e.g. Docker secrets)
load_secret_env() {
    local var="$1"
    local file_var="${var}_FILE"
    if [ -z "${!var:-}" ] && [ -n "${!file_var:-}" ] && [ -f "${!file_var}" ]; then
        export "$var"="$(tr -d '\r\n' < "${!file_var}")"
    fi
}

load_secret_env SA_PASSWORD
load_secret_env MSSQL_SA_PASSWORD
export SA_PASSWORD="${SA_PASSWORD:-${MSSQL_SA_PASSWORD:-}}"
load_secret_env QB_DB_PASSWORD

# Validate required environment variables
if [ -z "$SA_PASSWORD" ]; then
    echo "Error: SA_PASSWORD (or MSSQL_SA_PASSWORD) environment variable is required"
    exit 1
fi

if [ -z "${QB_DB_PASSWORD:-}" ]; then
    echo "Warning: QB_DB_PASSWORD not set, using default password"
    export QB_DB_PASSWORD="QBUserPassword123!"
fi

# Locate sqlcmd (MSSQL 2022 CU images moved tools to mssql-tools18 requiring -C)
SQLCMD_BIN=""
SQLCMD_FLAGS=""
find_sqlcmd() {
    if [ -x /opt/mssql-tools18/bin/sqlcmd ]; then
        SQLCMD_BIN="/opt/mssql-tools18/bin/sqlcmd"
        SQLCMD_FLAGS="-C"
    elif [ -x /opt/mssql-tools/bin/sqlcmd ]; then
        SQLCMD_BIN="/opt/mssql-tools/bin/sqlcmd"
        SQLCMD_FLAGS=""
    else
        echo "Error: sqlcmd not found in /opt/mssql-tools18/bin or /opt/mssql-tools/bin"
        exit 1
    fi
}

# Function to wait for SQL Server to be ready
wait_for_sqlserver() {
    echo "Waiting for SQL Server to start..."
    local elapsed=0

    while [ $elapsed -lt $MAX_STARTUP_WAIT ]; do
        if "$SQLCMD_BIN" $SQLCMD_FLAGS -S localhost -U sa -P "$SA_PASSWORD" -Q "SELECT 1" > /dev/null 2>&1; then
            echo "✓ SQL Server is ready!"
            return 0
        fi

        echo "Waiting for SQL Server... (${elapsed}s/${MAX_STARTUP_WAIT}s)"
        sleep $STARTUP_CHECK_INTERVAL
        elapsed=$((elapsed + STARTUP_CHECK_INTERVAL))
    done

    echo "Error: SQL Server failed to start within ${MAX_STARTUP_WAIT} seconds"
    return 1
}

# Function to run initialization scripts
run_initialization() {
    echo "Running QuickBuild database initialization..."

    for script in "$INIT_SCRIPTS_DIR"/*.sql; do
        if [ -f "$script" ]; then
            echo "Processing script: $(basename "$script")"

            if "$SQLCMD_BIN" $SQLCMD_FLAGS -S localhost -U sa -P "$SA_PASSWORD" -v QB_DB_PASSWORD="$QB_DB_PASSWORD" -i "$script"; then
                echo "✓ Successfully executed $(basename "$script")"
            else
                echo "✗ Failed to execute $(basename "$script")"
                return 1
            fi
        fi
    done

    touch "$INIT_FLAG_FILE"
    echo "✓ QuickBuild database initialization completed!"
    return 0
}

# Main execution flow
main() {
    find_sqlcmd

    # Start SQL Server in background
    echo "Starting SQL Server..."
    if [ -x /opt/mssql/bin/launch_sqlservr.sh ]; then
        /opt/mssql/bin/launch_sqlservr.sh &
    else
        /opt/mssql/bin/sqlservr &
    fi
    SQLSERVER_PID=$!

    # Wait for SQL Server to be ready
    if ! wait_for_sqlserver; then
        echo "Failed to start SQL Server"
        kill "$SQLSERVER_PID" 2>/dev/null || true
        exit 1
    fi

    # Run initialization if not already done
    if [ ! -f "$INIT_FLAG_FILE" ]; then
        echo "First run detected, initializing QuickBuild database..."
        if ! run_initialization; then
            echo "Database initialization failed"
            kill "$SQLSERVER_PID" 2>/dev/null || true
            exit 1
        fi
    else
        echo "Database already initialized, skipping initialization scripts"
    fi

    echo "QuickBuild database container is ready!"
    echo "Database: quickbuild"
    echo "User: qb_user"
    echo "Port: 1433"

    # Wait for SQL Server process to complete
    wait "$SQLSERVER_PID"
}

# Handle shutdown signals
trap 'echo "Shutting down..."; kill ${SQLSERVER_PID:-} 2>/dev/null || true; exit 0' SIGTERM SIGINT

# Run main function
main
