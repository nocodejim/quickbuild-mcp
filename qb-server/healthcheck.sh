#!/bin/bash
# QuickBuild 14 Server Health Check Script
# Verifies server is running and responding to requests
# Used by Docker health check mechanism

set -e

# Configuration
SERVER_PORT="${QB_SERVER_PORT:-8810}"
MAX_RETRIES=3
RETRY_DELAY=2
TIMEOUT=10

# Health check function
check_server_health() {
    local attempt=1
    
    while [ $attempt -le $MAX_RETRIES ]; do
        echo "Health check attempt $attempt of $MAX_RETRIES..."
        
        # Test basic HTTP connectivity
        if curl -f -s --max-time $TIMEOUT "http://localhost:${SERVER_PORT}/" > /dev/null 2>&1; then
            echo "✓ QuickBuild server is responding to HTTP requests"
            return 0
        else
            echo "✗ QuickBuild server is not responding on port ${SERVER_PORT} (attempt $attempt)"
        fi
        
        if [ $attempt -lt $MAX_RETRIES ]; then
            echo "Retrying in $RETRY_DELAY seconds..."
            sleep $RETRY_DELAY
        fi
        
        attempt=$((attempt + 1))
    done
    
    echo "Server health check failed after $MAX_RETRIES attempts"
    return 1
}

# Check if curl is available
if ! command -v curl > /dev/null 2>&1; then
    echo "Error: curl is required for health check"
    exit 1
fi

# Run health check
echo "Starting QuickBuild server health check..."
echo "Checking server on port ${SERVER_PORT}..."
check_server_health