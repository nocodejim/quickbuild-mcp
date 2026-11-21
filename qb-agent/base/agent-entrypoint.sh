#!/bin/bash
# QuickBuild Agent Container Entrypoint
# Handles agent registration, configuration, and startup
# Implements auto-discovery and server connection

set -e

# Configuration
QB_AGENT_HOME="/opt/qb-agent"
AGENT_CONF_DIR="$QB_AGENT_HOME/conf"
NODE_PROPERTIES="$AGENT_CONF_DIR/node.properties"
MAX_SERVER_WAIT=300
SERVER_CHECK_INTERVAL=10

echo "Starting QuickBuild ${QB_VERSION:-} Build Agent Container..."
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
    echo "Detecting container IP address..." >&2
    
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
        echo "⚠ Could not detect container IP, using localhost" >&2
    fi
    
    echo "✓ Container IP detected: $container_ip" >&2
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

    # QuickBuild 16 agents refuse to start without a "token" (a value without ':' marks a
    # build agent). Use QB_AGENT_TOKEN, else keep the token from a previous start of this
    # container, else generate one. New tokens must be authorized once on the server's Grid
    # page or via GET /rest/tokens/authorize?ip=<agent ip>&port=<agent port>.
    local agent_token="${QB_AGENT_TOKEN:-}"
    if [ -z "$agent_token" ] && [ -f "$NODE_PROPERTIES" ]; then
        agent_token="$(grep '^token=' "$NODE_PROPERTIES" | head -n 1 | cut -d= -f2-)"
    fi
    if [ -z "$agent_token" ]; then
        agent_token="$(cat /proc/sys/kernel/random/uuid)"
        echo "Generated new agent token (authorize this agent on the QuickBuild server)"
    fi

    # Generate node.properties (same keys as the server's buildagent download)
    {
        echo "# QuickBuild Agent Configuration"
        echo "# Generated automatically by container entrypoint"
        echo "serverUrl=$QB_SERVER_URL"
        echo "ip=$container_ip"
        echo "port=${AGENT_PORT:-8811}"
        echo "token=$agent_token"
    } > "$NODE_PROPERTIES"

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
    sed "s/^token=.*/token=********/" "$NODE_PROPERTIES"
    echo "==================="
    
    # Change to agent home directory
    cd "$QB_AGENT_HOME"
    
    local wrapper
    case "$(uname -m)" in
        x86_64|amd64) wrapper="$QB_AGENT_HOME/bin/wrapper-linux-x86-64" ;;
        aarch64|arm64) wrapper="$QB_AGENT_HOME/bin/wrapper-linux-arm-64" ;;
        *) echo "Error: unsupported CPU architecture $(uname -m)"; exit 1 ;;
    esac

    # Run the Java Service Wrapper in the foreground (equivalent to "bin/agent.sh console")
    # as PID 1 so it receives SIGTERM directly and stops the JVM gracefully.
    cd "$QB_AGENT_HOME/bin"
    exec "$wrapper" ../conf/wrapper.conf \
        wrapper.syslog.ident=buildagent \
        wrapper.pidfile=./buildagent.pid \
        wrapper.name=buildagent \
        "wrapper.displayname=QuickBuild Build Agent" \
        "wrapper.java.command=${JAVA_HOME:-/opt/java/openjdk}/bin/java" \
        wrapper.console.flush=TRUE \
        wrapper.script.version=3.5.49
}

# Function to display startup information
display_startup_info() {
    echo ""
    echo "=========================================="
    echo "QuickBuild ${QB_VERSION:-} Build Agent Container"
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