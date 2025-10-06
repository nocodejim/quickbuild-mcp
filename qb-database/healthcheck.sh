#!/bin/bash
# QuickBuild 14 Database Health Check Script
# Verifies SQL Server is running and accepting connections
# Used by Docker health check mechanism

set -e

# Configuration
MAX_RETRIES=3
RETRY_DELAY=2
TIMEOUT=10

# Health check function
check_database_health() {
    local attempt=1
    
    while [ $attempt -le $MAX_RETRIES ]; do
        echo "Health check attempt $attempt of $MAX_RETRIES..."
        
        # Test basic SQL Server connectivity
        if /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P "$SA_PASSWORD" -Q "SELECT 1 as HealthCheck" -t $TIMEOUT > /dev/null 2>&1; then
            echo "✓ SQL Server is responding to connections"
            
            # Test quickbuild database accessibility
            if /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P "$SA_PASSWORD" -d quickbuild -Q "SELECT DB_NAME() as CurrentDB" -t $TIMEOUT > /dev/null 2>&1; then
                echo "✓ quickbuild database is accessible"
                
                # Test qb_user can connect (if password is available)
                if [ ! -z "$QB_DB_PASSWORD" ]; then
                    if /opt/mssql-tools/bin/sqlcmd -S localhost -U qb_user -P "$QB_DB_PASSWORD" -d quickbuild -Q "SELECT USER_NAME() as CurrentUser" -t $TIMEOUT > /dev/null 2>&1; then
                        echo "✓ qb_user can connect to quickbuild database"
                        echo "Database health check passed!"
                        return 0
                    else
                        echo "⚠ qb_user connection test failed (may not be initialized yet)"
                        # Don't fail health check if qb_user isn't ready yet
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
    echo "Error: SA_PASSWORD environment variable is required"
    exit 1
fi

# Run health check
echo "Starting database health check..."
check_database_health