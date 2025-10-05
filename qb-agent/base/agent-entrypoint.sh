#!/bin/bash
# QuickBuild 14 Agent Container Entrypoint
# Handles agent registration, configuration, and startup
# Implements auto-discovery and server connection

set -e

# Configuration
QB_AGENT_HOME="/opt/qb-agent"
AGENT_CONF_DIR="$QB_AGENT_HOME/conf"
NODE_PROPERTIES="$AGENT_CONF_DIR/node.properties"
MAX_SERVER_WAIT=300
SERVER_CHECK_INTERVAL=10

echo "Starting QuickBuild 14 Build Agent Container..."
echo "Agent Home: $QB_AGENT_HOME"

# Function to validate environment variables
validate_environment() {
    echo "Validating environment variables..."
    
    if [ -z "$QB_SERVER_URL" ]; then
        echo "Error: QB_SERVER_URL environment variable is required"
        exit 1
    fi
    
    echo "✓ Required environment variables are set"
    echo "Server URL: $QB_SERVER_URL"
}

# Function to detect container IP address
detect_container_ip() {
    echo "Detecting container IP address..."
    
    # Try multiple methods to get container IP
    local container_ip=""
    
    # Method 1: hostname -i (most reliable in Docker)
    if command -v hostname > /dev/null 2>&1; then
        container_ip=$(hostname -i 2>/dev/null | awk '{print $1}' || true)
    fi
    
    # Method 2: ip route (fallback)
    if [ -z "$container_ip" ] && command -v ip > /dev/null 2>&1; then
        container_ip=$(ip route get 1 2>/dev/null | awk '{print $7}' | head -1 || true)
    fi
    
    # Method 3: ifconfig (fallback)
    if [ -z "$container_ip" ] && command -v ifconfig > /dev/null 2>&1; then
        container_ip=$(ifconfig eth0 2>/dev/null | grep 'inet ' | awk '{print $2}' | cut -d: -f2 || true)
    fi
    
    # Default fallback
    if [ -z "$container_ip" ]; then
        container_ip="127.0.0.1"
        echo "⚠ Could not detect container IP, using localhost"
    fi
    
    echo "✓ Container IP detected: $container_ip"
    echo "$container_ip"
}

# Function to generate agent name
generate_agent_name() {
    if [ -n "$AGENT_NAME" ]; then
        echo "$AGENT_NAME"
    else
        # Generate name from hostname and container info
        local hostname=$(hostname 2>/dev/null || echo "agent")
        local timestamp=$(date +%s)
        echo "${hostname}-${timestamp}"
    fi
}

# Function to wait for QuickBuild server
wait_for_server() {
    echo "Waiting for QuickBuild server to be available..."
    local elapsed=0
    local server_host=$(echo "$QB_SERVER_URL" | sed 's|http://||' | sed 's|https://||' | cut -d: -f1)
    local server_port=$(echo "$QB_SERVER_URL" | sed 's|http://||' | sed 's|https://||' | cut -d: -f2 | cut -d/ -f1)
    
    # Default port if not specified
    if [ "$server_port" = "$server_host" ]; then
        server_port="8810"
    fi
    
    while [ $elapsed -lt $MAX_SERVER_WAIT ]; do
        if curl -f -s --max-time 10 "$QB_SERVER_URL/" > /dev/null 2>&1; then
            echo "✓ QuickBuild server is available!"
            return 0
        fi
        
        echo "Waiting for server... (${elapsed}s/${MAX_SERVER_WAIT}s)"
        sleep $SERVER_CHECK_INTERVAL
        elapsed=$((elapsed + SERVER_CHECK_INTERVAL))
    done
    
    echo "Error: QuickBuild server not available after ${MAX_SERVER_WAIT} seconds"
    return 1
}

# Function to generate node.properties configuration
generate_node_properties() {
    echo "Generating node.properties configuration..."
    
    local container_ip=$(detect_container_ip)
    local agent_name=$(generate_agent_name)
    
    # Create conf directory if it doesn't exist
    mkdir -p "$AGENT_CONF_DIR"
    
    # Generate node.properties
    cat > "$NODE_PROPERTIES" << EOF
# QuickBuild 14 Agent Configuration
# Generated automatically by container entrypoint

# Server connection settings
serverUrl=$QB_SERVER_URL

# Agent network settings
ip=$container_ip
port=${AGENT_PORT:-8811}

# Agent identification
name=$agent_name

# Agent capabilities (will be detected automatically)
# Additional properties can be added here

# Logging settings
logLevel=INFO

# Performance settings
maxConcurrentBuilds=2
buildTimeout=3600

# Security settings (if needed)
# sslEnabled=false
# keystorePath=
# keystorePassword=

EOF

    echo "✓ node.properties generated successfully"
    echo "Agent Name: $agent_name"
    echo "Agent IP: $container_ip"
    echo "Agent Port: ${AGENT_PORT:-8811}"
}

# Function to start QuickBuild agent
start_agent() {
    echo "Starting QuickBuild agent..."
    echo "Configuration file: $NODE_PROPERTIES"
    
    # Display configuration for debugging
    echo "Agent Configuration:"
    echo "==================="
    cat "$NODE_PROPERTIES"
    echo "==================="
    
    # Change to agent home directory
    cd "$QB_AGENT_HOME"
    
    # Start QuickBuild agent
    exec "$QB_AGENT_HOME/bin/agent.sh" console
}

# Function to display startup information
display_startup_info() {
    echo ""
    echo "=========================================="
    echo "QuickBuild 14 Build Agent Container"
    echo "=========================================="
    echo "Server URL: $QB_SERVER_URL"
    echo "Agent Port: ${AGENT_PORT:-8811}"
    echo "Agent Name: ${AGENT_NAME:-auto-generated}"
    echo "Agent Home: $QB_AGENT_HOME"
    echo "Container: $(hostname)"
    echo "=========================================="
    echo ""
}

# Main execution flow
main() {
    display_startup_info
    
    # Validate environment
    validate_environment
    
    # Wait for server
    wait_for_server
    
    # Generate configuration
    generate_node_properties
    
    # Start agent
    start_agent
}

# Handle shutdown signals gracefully
trap 'echo "Received shutdown signal, stopping agent..."; exit 0' SIGTERM SIGINT

# Run main function
main