#!/bin/bash
# QuickBuild 14 Server Container Entrypoint
# Handles dynamic configuration, data volume setup, and server startup
# Implements consolidated volume approach for persistence

set -e

# Configuration
QB_HOME="/opt/quickbuild"
QB_DATA="/opt/quickbuild/data"
FIRST_RUN_FLAG="$QB_DATA/.qb-server-initialized"
MAX_DB_WAIT=300
DB_CHECK_INTERVAL=10

echo "Starting QuickBuild 14 Server Container..."
echo "QuickBuild Home: $QB_HOME"
echo "Data Directory: $QB_DATA"

# Function to validate environment variables
validate_environment() {
    echo "Validating environment variables..."
    
    local required_vars=(
        "QB_DB_HOST"
        "QB_DB_PORT" 
        "QB_DB_NAME"
        "QB_DB_USER"
        "QB_DB_PASSWORD"
    )
    
    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            echo "Error: Required environment variable $var is not set"
            exit 1
        fi
    done
    
    echo "✓ All required environment variables are set"
}

# Function to wait for database availability (mock version)
wait_for_database() {
    echo "Mock: Waiting for database to be available..."
    
    # For testing, just check if we can reach the database host
    local elapsed=0
    while [ $elapsed -lt $MAX_DB_WAIT ]; do
        if nc -z "$QB_DB_HOST" "$QB_DB_PORT" 2>/dev/null; then
            echo "✓ Database host is reachable!"
            return 0
        fi
        
        echo "Waiting for database... (${elapsed}s/${MAX_DB_WAIT}s)"
        sleep $DB_CHECK_INTERVAL
        elapsed=$((elapsed + DB_CHECK_INTERVAL))
    done
    
    echo "Warning: Database not reachable after ${MAX_DB_WAIT} seconds (continuing anyway for mock)"
    return 0
}

# Function to setup data volume structure
setup_data_volume() {
    echo "Setting up data volume structure..."
    
    # Create data subdirectories if they don't exist
    mkdir -p "$QB_DATA/conf"
    mkdir -p "$QB_DATA/logs" 
    mkdir -p "$QB_DATA/artifacts"
    mkdir -p "$QB_DATA/backup"
    
    # If first run, move existing directories to data volume
    if [ ! -f "$FIRST_RUN_FLAG" ]; then
        echo "First run detected, migrating directories to data volume..."
        
        # Move conf directory if it exists and has content
        if [ -d "$QB_HOME/conf" ] && [ "$(ls -A $QB_HOME/conf 2>/dev/null)" ]; then
            echo "Migrating conf directory..."
            cp -r "$QB_HOME/conf"/* "$QB_DATA/conf/" 2>/dev/null || true
        fi
        
        # Move logs directory if it exists
        if [ -d "$QB_HOME/logs" ] && [ "$(ls -A $QB_HOME/logs 2>/dev/null)" ]; then
            echo "Migrating logs directory..."
            cp -r "$QB_HOME/logs"/* "$QB_DATA/logs/" 2>/dev/null || true
        fi
        
        # Move artifacts directory if it exists
        if [ -d "$QB_HOME/artifacts" ] && [ "$(ls -A $QB_HOME/artifacts 2>/dev/null)" ]; then
            echo "Migrating artifacts directory..."
            cp -r "$QB_HOME/artifacts"/* "$QB_DATA/artifacts/" 2>/dev/null || true
        fi
    fi
    
    # Remove original directories and create symlinks
    rm -rf "$QB_HOME/conf" "$QB_HOME/logs" "$QB_HOME/artifacts" 2>/dev/null || true
    
    # Create symlinks to data volume
    ln -sf "$QB_DATA/conf" "$QB_HOME/conf"
    ln -sf "$QB_DATA/logs" "$QB_HOME/logs"
    ln -sf "$QB_DATA/artifacts" "$QB_HOME/artifacts"
    
    echo "✓ Data volume structure setup complete"
}

# Function to generate configuration files from templates
generate_configuration() {
    echo "Generating configuration files from templates..."
    
    # Generate hibernate.properties
    if [ -f "$QB_HOME/conf/hibernate.properties.template" ]; then
        echo "Generating hibernate.properties..."
        envsubst < "$QB_HOME/conf/hibernate.properties.template" > "$QB_DATA/conf/hibernate.properties"
        echo "✓ hibernate.properties generated"
    else
        echo "Warning: hibernate.properties.template not found"
    fi
    
    # Generate wrapper.conf
    if [ -f "$QB_HOME/conf/wrapper.conf.template" ]; then
        echo "Generating wrapper.conf..."
        envsubst < "$QB_HOME/conf/wrapper.conf.template" > "$QB_DATA/conf/wrapper.conf"
        echo "✓ wrapper.conf generated"
    else
        echo "Warning: wrapper.conf.template not found"
    fi
    
    # Set proper permissions
    chmod 600 "$QB_DATA/conf/hibernate.properties" 2>/dev/null || true
    chmod 644 "$QB_DATA/conf/wrapper.conf" 2>/dev/null || true
    
    echo "✓ Configuration files generated successfully"
}

# Function to create first run flag
mark_initialization_complete() {
    echo "Marking initialization as complete..."
    echo "Initialized on: $(date)" > "$FIRST_RUN_FLAG"
    echo "Container: $(hostname)" >> "$FIRST_RUN_FLAG"
    echo "Version: QuickBuild 14" >> "$FIRST_RUN_FLAG"
}

# Function to start QuickBuild server
start_quickbuild() {
    echo "Starting QuickBuild server..."
    echo "Server will be available on port ${QB_SERVER_PORT:-8810}"
    echo "Data persisted in: $QB_DATA"
    
    # Change to QB home directory
    cd "$QB_HOME"
    
    # Start QuickBuild directly with Java to bypass wrapper license issues
    echo "Starting QuickBuild directly with Java (bypassing wrapper license)..."
    
    # Set up Java classpath for QuickBuild (include framework, plugins, and bootstrap directory)
    export CLASSPATH="$QB_HOME/framework/*:$QB_HOME/plugins/*:$QB_HOME/plugins/com.pmease.quickbuild.bootstrap:$QB_HOME/lib/*"
    
    # Set QuickBuild system properties
    JAVA_OPTS="-Xmx2048m -Xms1024m"
    JAVA_OPTS="$JAVA_OPTS -Dqb.home=$QB_HOME"
    JAVA_OPTS="$JAVA_OPTS -Dqb.data=$QB_DATA"
    JAVA_OPTS="$JAVA_OPTS -Dqb.server.port=${QB_SERVER_PORT:-8810}"
    JAVA_OPTS="$JAVA_OPTS -Djava.awt.headless=true"
    
    # Debug: Show what we're trying to run
    echo "Java classpath: $CLASSPATH"
    echo "Looking for Bootstrap class..."
    
    # Start QuickBuild main class directly
    exec java $JAVA_OPTS -cp "$CLASSPATH" com.pmease.quickbuild.bootstrap.Bootstrap
}

# Function to display startup information
display_startup_info() {
    echo ""
    echo "=========================================="
    echo "QuickBuild 14 Server Container"
    echo "=========================================="
    echo "Database Host: $QB_DB_HOST"
    echo "Database Port: $QB_DB_PORT"
    echo "Database Name: $QB_DB_NAME"
    echo "Database User: $QB_DB_USER"
    echo "Server Port: ${QB_SERVER_PORT:-8810}"
    echo "Data Volume: $QB_DATA"
    echo "First Run: $([ -f "$FIRST_RUN_FLAG" ] && echo "No" || echo "Yes")"
    echo "=========================================="
    echo ""
}

# Main execution flow
main() {
    display_startup_info
    
    # Validate environment
    validate_environment
    
    # Wait for database
    wait_for_database
    
    # Setup data volume
    setup_data_volume
    
    # Generate configuration
    generate_configuration
    
    # Mark initialization complete if first run
    if [ ! -f "$FIRST_RUN_FLAG" ]; then
        mark_initialization_complete
    fi
    
    # Start QuickBuild
    start_quickbuild
}

# Handle shutdown signals gracefully
trap 'echo "Received shutdown signal, stopping QuickBuild..."; exit 0' SIGTERM SIGINT

# Run main function
main