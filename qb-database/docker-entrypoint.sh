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
echo "SQL Server Version: $(cat /etc/os-release | grep VERSION= | cut -d'"' -f2)"

# Validate required environment variables
if [ -z "$SA_PASSWORD" ]; then
    echo "Error: SA_PASSWORD environment variable is required"
    exit 1
fi

if [ -z "$QB_DB_PASSWORD" ]; then
    echo "Warning: QB_DB_PASSWORD not set, using default password"
    export QB_DB_PASSWORD="QBUserPassword123!"
fi

# Function to wait for SQL Server to be ready
wait_for_sqlserver() {
    echo "Waiting for SQL Server to start..."
    local elapsed=0
    
    while [ $elapsed -lt $MAX_STARTUP_WAIT ]; do
        if /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P "$SA_PASSWORD" -Q "SELECT 1" > /dev/null 2>&1; then
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
    
    # Replace password placeholder in scripts
    for script in "$INIT_SCRIPTS_DIR"/*.sql; do
        if [ -f "$script" ]; then
            echo "Processing script: $(basename "$script")"
            # Create temporary script with password substitution
            temp_script="/tmp/$(basename "$script")"
            sed "s/\$(QB_DB_PASSWORD)/$QB_DB_PASSWORD/g" "$script" > "$temp_script"
            
            # Execute the script
            if /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P "$SA_PASSWORD" -i "$temp_script"; then
                echo "✓ Successfully executed $(basename "$script")"
            else
                echo "✗ Failed to execute $(basename "$script")"
                rm -f "$temp_script"
                return 1
            fi
            
            # Clean up temporary script
            rm -f "$temp_script"
        fi
    done
    
    # Create initialization flag file
    touch "$INIT_FLAG_FILE"
    echo "✓ QuickBuild database initialization completed!"
    return 0
}

# Main execution flow
main() {
    # Start SQL Server using the original entrypoint in background
    echo "Starting SQL Server using original entrypoint..."
    /opt/mssql/bin/launch_sqlservr.sh &
    SQLSERVER_PID=$!
    
    # Wait for SQL Server to be ready
    if ! wait_for_sqlserver; then
        echo "Failed to start SQL Server"
        exit 1
    fi
    
    # Run initialization if not already done
    if [ ! -f "$INIT_FLAG_FILE" ]; then
        echo "First run detected, initializing QuickBuild database..."
        if ! run_initialization; then
            echo "Database initialization failed"
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
    wait $SQLSERVER_PID
}

# Handle shutdown signals
trap 'echo "Shutting down..."; kill $SQLSERVER_PID 2>/dev/null; exit 0' SIGTERM SIGINT

# Run main function
main