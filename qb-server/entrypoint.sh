#!/bin/bash
# QuickBuild Server Container Entrypoint
# Handles dynamic configuration, data volume setup, and server startup
# Implements consolidated volume approach for persistence

set -e

# Configuration
QB_HOME="/opt/quickbuild"
QB_DATA="/opt/quickbuild/data"
QB_VERSION="${QB_VERSION:-unknown}"
CONF_DIST="$QB_HOME/conf.dist"
TEMPLATE_DIR="$QB_HOME/templates"
FIRST_RUN_FLAG="$QB_DATA/.qb-server-initialized"
MAX_DB_WAIT=300
DB_CHECK_INTERVAL=10

# Version-specific files that are always refreshed from the image on start
# (wrapper.conf references versioned jar names, so a stale copy breaks upgrades)
REFRESHED_CONF_FILES=("wrapper.conf" "wrapper-license.conf")

echo "Starting QuickBuild ${QB_VERSION} Server Container..."
echo "QuickBuild Home: $QB_HOME"
echo "Data Directory: $QB_DATA"

# Function to validate environment variables
validate_environment() {
    echo "Validating environment variables..."

    if [ -z "${QB_DB_PASSWORD:-}" ] && [ -n "${QB_DB_PASSWORD_FILE:-}" ] && [ -f "${QB_DB_PASSWORD_FILE}" ]; then
        export QB_DB_PASSWORD="$(tr -d '\r\n' < "${QB_DB_PASSWORD_FILE}")"
    fi

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

# Function to wait for the database port to accept TCP connections
wait_for_database() {
    echo "Waiting for database at ${QB_DB_HOST}:${QB_DB_PORT}..."

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

    echo "Error: Database not reachable after ${MAX_DB_WAIT} seconds"
    exit 1
}

# Function to setup data volume structure
setup_data_volume() {
    echo "Setting up data volume structure..."

    # Create data subdirectories if they don't exist
    mkdir -p "$QB_DATA/conf"
    mkdir -p "$QB_DATA/logs"
    mkdir -p "$QB_DATA/artifacts"
    mkdir -p "$QB_DATA/backup"

    # If first run, seed the data volume from the image
    if [ ! -f "$FIRST_RUN_FLAG" ]; then
        echo "First run detected, seeding data volume..."

        if [ -d "$CONF_DIST" ]; then
            echo "Seeding conf directory..."
            cp -a "$CONF_DIST"/. "$QB_DATA/conf/"
        fi

        # Move logs directory if it exists
        if [ -d "$QB_HOME/logs" ] && [ ! -L "$QB_HOME/logs" ] && [ "$(ls -A "$QB_HOME/logs" 2>/dev/null)" ]; then
            echo "Migrating logs directory..."
            cp -r "$QB_HOME/logs"/* "$QB_DATA/logs/" 2>/dev/null || true
        fi

        # Move artifacts directory if it exists
        if [ -d "$QB_HOME/artifacts" ] && [ ! -L "$QB_HOME/artifacts" ] && [ "$(ls -A "$QB_HOME/artifacts" 2>/dev/null)" ]; then
            echo "Migrating artifacts directory..."
            cp -r "$QB_HOME/artifacts"/* "$QB_DATA/artifacts/" 2>/dev/null || true
        fi
    fi

    # Refresh version-specific conf files and add any conf files new in this version
    if [ -d "$CONF_DIST" ]; then
        for file in "${REFRESHED_CONF_FILES[@]}"; do
            if [ -f "$CONF_DIST/$file" ]; then
                cp -f "$CONF_DIST/$file" "$QB_DATA/conf/$file"
            fi
        done
        cp -an "$CONF_DIST"/. "$QB_DATA/conf/" 2>/dev/null || true
    fi

    # Remove original directories and create symlinks
    rm -rf "$QB_HOME/conf" "$QB_HOME/logs" "$QB_HOME/artifacts" 2>/dev/null || true

    # Create symlinks to data volume
    ln -sfn "$QB_DATA/conf" "$QB_HOME/conf"
    ln -sfn "$QB_DATA/logs" "$QB_HOME/logs"
    ln -sfn "$QB_DATA/artifacts" "$QB_HOME/artifacts"

    echo "✓ Data volume structure setup complete"
}

# Function to generate configuration files from templates
generate_configuration() {
    echo "Generating configuration files from templates..."

    # Generate hibernate.properties (only substitute our own variables)
    if [ -f "$TEMPLATE_DIR/hibernate.properties.template" ]; then
        echo "Generating hibernate.properties..."
        envsubst '${QB_DB_HOST} ${QB_DB_PORT} ${QB_DB_NAME} ${QB_DB_USER} ${QB_DB_PASSWORD}' \
            < "$TEMPLATE_DIR/hibernate.properties.template" > "$QB_DATA/conf/hibernate.properties"
        chmod 600 "$QB_DATA/conf/hibernate.properties" 2>/dev/null || true
        echo "✓ hibernate.properties generated"
    else
        echo "Warning: hibernate.properties.template not found"
    fi

    # Set the HTTP port in node.properties
    local node_props="$QB_DATA/conf/node.properties"
    local port="${QB_SERVER_PORT:-8810}"
    if [ -f "$node_props" ] && grep -q '^port=' "$node_props"; then
        sed -i "s/^port=.*/port=${port}/" "$node_props"
    else
        echo "port=${port}" >> "$node_props"
    fi
    echo "✓ node.properties port set to ${port}"

    echo "✓ Configuration files generated successfully"
}

# Function to create first run flag
mark_initialization_complete() {
    echo "Marking initialization as complete..."
    echo "Initialized on: $(date)" > "$FIRST_RUN_FLAG"
    echo "Container: $(hostname)" >> "$FIRST_RUN_FLAG"
    echo "Version: QuickBuild ${QB_VERSION}" >> "$FIRST_RUN_FLAG"
}

# Resolve the Java Service Wrapper binary shipped with QuickBuild for this CPU
wrapper_binary() {
    case "$(uname -m)" in
        x86_64|amd64) echo "$QB_HOME/bin/wrapper-linux-x86-64" ;;
        aarch64|arm64) echo "$QB_HOME/bin/wrapper-linux-arm-64" ;;
        *) echo "Error: unsupported CPU architecture $(uname -m)" >&2; exit 1 ;;
    esac
}

# Function to start QuickBuild server
start_quickbuild() {
    echo "Starting QuickBuild server..."
    echo "Server will be available on port ${QB_SERVER_PORT:-8810}"
    echo "Data persisted in: $QB_DATA"

    local wrapper
    wrapper="$(wrapper_binary)"

    local extra_args=()
    if [ -n "${QB_JAVA_MAX_MEMORY_MB:-}" ]; then
        extra_args+=("wrapper.java.maxmemory=${QB_JAVA_MAX_MEMORY_MB}")
    fi

    # Run the Java Service Wrapper in the foreground (equivalent to "bin/server.sh console")
    # as PID 1 so it receives SIGTERM directly and stops the JVM gracefully.
    cd "$QB_HOME/bin"
    exec "$wrapper" ../conf/wrapper.conf \
        wrapper.syslog.ident=quickbuild \
        wrapper.pidfile=./quickbuild.pid \
        wrapper.name=quickbuild \
        "wrapper.displayname=QuickBuild Server" \
        "wrapper.java.command=${JAVA_HOME:-/opt/java/openjdk}/bin/java" \
        wrapper.console.flush=TRUE \
        wrapper.script.version=3.5.49 \
        "${extra_args[@]}"
}

# Function to display startup information
display_startup_info() {
    echo ""
    echo "=========================================="
    echo "QuickBuild ${QB_VERSION} Server Container"
    echo "=========================================="
    echo "Database Host: $QB_DB_HOST"
    echo "Database Port: $QB_DB_PORT"
    echo "Database Name: $QB_DB_NAME"
    echo "Database User: $QB_DB_USER"
    echo "Server Port: ${QB_SERVER_PORT:-8810}"
    echo "Data Volume: $QB_DATA"
    echo "Storage Directory: ${QB_STORAGE_DIR:-/var/lib/quickbuild/storage} (enter this as 'Global Storage Directory' in the setup wizard)"
    echo "Java: $(java -version 2>&1 | head -n 1)"
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

# Handle shutdown signals gracefully (before the wrapper takes over as PID 1)
trap 'echo "Received shutdown signal, stopping QuickBuild..."; exit 0' SIGTERM SIGINT

# Run main function
main
