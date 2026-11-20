#!/bin/bash
# QuickBuild 14 Database Health Check Script
# Verifies SQL Server is running and accepting connections
# Used by Docker health check mechanism

set -e

# Configuration
MAX_RETRIES=3
RETRY_DELAY=2
TIMEOUT=10

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
        return 1
    fi
}

# Health check function
check_database_health() {
    local attempt=1

    while [ $attempt -le $MAX_RETRIES ]; do
        echo "Health check attempt $attempt of $MAX_RETRIES..."

        # Test basic SQL Server connectivity
        if "$SQLCMD_BIN" $SQLCMD_FLAGS -S localhost -U sa -P "$SA_PASSWORD" -Q "SELECT 1 as HealthCheck" -t $TIMEOUT > /dev/null 2>&1; then
            echo "✓ SQL Server is responding to connections"

            # Test quickbuild database accessibility
            if "$SQLCMD_BIN" $SQLCMD_FLAGS -S localhost -U sa -P "$SA_PASSWORD" -d quickbuild -Q "SELECT DB_NAME() as CurrentDB" -t $TIMEOUT > /dev/null 2>&1; then
                echo "✓ quickbuild database is accessible"

                # Test qb_user can connect (if password is available)
                if [ -n "${QB_DB_PASSWORD:-}" ]; then
                    if "$SQLCMD_BIN" $SQLCMD_FLAGS -S localhost -U qb_user -P "$QB_DB_PASSWORD" -d quickbuild -Q "SELECT USER_NAME() as CurrentUser" -t $TIMEOUT > /dev/null 2>&1; then
                        echo "✓ qb_user can connect to quickbuild database"
                        echo "Database health check passed!"
                        return 0
                    else
                        echo "⚠ qb_user connection test failed (may not be initialized yet)"
                        echo "Database health check passed (basic connectivity OK)!"
                        return 0
                    fi
                else
                    echo "⚠ QB_DB_PASSWORD not set, skipping qb_user test"
                    echo "Database health check passed (basic connectivity OK)!"
                    return 0
                fi
            else
                echo "✗ quickbuild database is not accessible"
            fi
        else
            echo "✗ SQL Server is not responding (attempt $attempt)"
        fi

        if [ $attempt -lt $MAX_RETRIES ]; then
            echo "Retrying in $RETRY_DELAY seconds..."
            sleep $RETRY_DELAY
        fi

        attempt=$((attempt + 1))
    done

    echo "Database health check failed after $MAX_RETRIES attempts"
    return 1
}

# Validate required environment variables
if [ -z "$SA_PASSWORD" ]; then
    echo "Error: SA_PASSWORD (or MSSQL_SA_PASSWORD) environment variable is required"
    exit 1
fi

find_sqlcmd

# Run health check
echo "Starting database health check..."
check_database_health
