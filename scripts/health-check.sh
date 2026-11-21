#!/bin/bash
# QuickBuild 14 Health Check Utility
# Comprehensive health checking for individual components
# Can be used for external monitoring systems and alerting

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMEOUT=30
OUTPUT_FORMAT="text"
EXIT_ON_FAILURE=true

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Health check results
HEALTH_STATUS="healthy"
HEALTH_DETAILS=()
HEALTH_METRICS=()

# Logging functions
log() {
    if [[ "$OUTPUT_FORMAT" == "text" ]]; then
        echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
    fi
}

error() {
    if [[ "$OUTPUT_FORMAT" == "text" ]]; then
        echo -e "${RED}[ERROR]${NC} $1" >&2
    fi
    HEALTH_STATUS="unhealthy"
}

success() {
    if [[ "$OUTPUT_FORMAT" == "text" ]]; then
        echo -e "${GREEN}[SUCCESS]${NC} $1"
    fi
}

warning() {
    if [[ "$OUTPUT_FORMAT" == "text" ]]; then
        echo -e "${YELLOW}[WARNING]${NC} $1"
    fi
    if [[ "$HEALTH_STATUS" == "healthy" ]]; then
        HEALTH_STATUS="degraded"
    fi
}

add_detail() {
    HEALTH_DETAILS+=("$1")
}

add_metric() {
    HEALTH_METRICS+=("$1")
}

# Usage function
usage() {
    echo "Usage: $0 [OPTIONS] COMPONENT"
    echo ""
    echo "Components:"
    echo "  database         Check database health"
    echo "  server           Check QuickBuild server health"
    echo "  agent            Check build agent health"
    echo "  network          Check network connectivity"
    echo "  storage          Check storage/volume health"
    echo "  all              Check all components"
    echo ""
    echo "Options:"
    echo "  -f, --format FORMAT  Output format (text|json|prometheus) (default: text)"
    echo "  -t, --timeout SEC    Timeout for checks (default: 30)"
    echo "  -u, --url URL        QuickBuild server URL (default: auto-detect)"
    echo "  -c, --continue       Continue on failures (don't exit on first failure)"
    echo "  -v, --verbose        Verbose output"
    echo "  -h, --help          Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 database"
    echo "  $0 server -u http://localhost:8810"
    echo "  $0 all -f json"
    echo "  $0 network --verbose"
    echo ""
}

# Parse command line arguments
COMPONENT=""
QB_URL=""
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--format)
            OUTPUT_FORMAT="$2"
            shift 2
            ;;
        -t|--timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        -u|--url)
            QB_URL="$2"
            shift 2
            ;;
        -c|--continue)
            EXIT_ON_FAILURE=false
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        -*)
            error "Unknown option: $1"
            usage
            exit 1
            ;;
        *)
            if [[ -z "$COMPONENT" ]]; then
                COMPONENT="$1"
            else
                error "Multiple components specified"
                usage
                exit 1
            fi
            shift
            ;;
    esac
done

if [[ -z "$COMPONENT" ]]; then
    error "Component must be specified"
    usage
    exit 1
fi

# Auto-detect QuickBuild URL if not provided
if [[ -z "$QB_URL" ]]; then
    if nc -z localhost 8810 2>/dev/null; then
        QB_URL="http://localhost:8810"
    else
        QB_URL="http://localhost:8810"  # Default, will fail if not accessible
    fi
fi

# Health check functions
check_database_health() {
    log "Checking database health..."
    
    # Check if database port is accessible
    if nc -z localhost 1433 2>/dev/null; then
        success "Database port 1433 is accessible"
        add_detail "database_port_accessible=true"
        add_metric "quickbuild_database_port_accessible 1"
    else
        error "Database port 1433 is not accessible"
        add_detail "database_port_accessible=false"
        add_metric "quickbuild_database_port_accessible 0"
        return 1
    fi
    
    # Try to connect via QuickBuild (indirect check)
    local db_status=$(curl -s --max-time $TIMEOUT "$QB_URL/rest/system/database" 2>/dev/null || echo "")
    if [[ -n "$db_status" ]]; then
        success "Database connectivity confirmed via QuickBuild"
        add_detail "database_connectivity=true"
        add_metric "quickbuild_database_connectivity 1"
    else
        warning "Could not verify database connectivity via QuickBuild"
        add_detail "database_connectivity=unknown"
        add_metric "quickbuild_database_connectivity 0"
    fi
    
    return 0
}

check_server_health() {
    log "Checking QuickBuild server health..."
    
    # Basic HTTP connectivity
    local http_status=$(curl -s -o /dev/null -w "%{http_code}" --max-time $TIMEOUT "$QB_URL" 2>/dev/null || echo "000")
    if [[ "$http_status" == "200" ]]; then
        success "QuickBuild server HTTP interface is accessible"
        add_detail "server_http_accessible=true"
        add_metric "quickbuild_server_http_accessible 1"
    else
        error "QuickBuild server HTTP interface is not accessible (HTTP $http_status)"
        add_detail "server_http_accessible=false"
        add_detail "server_http_status=$http_status"
        add_metric "quickbuild_server_http_accessible 0"
        return 1
    fi
    
    # Version information
    local version=$(curl -s --max-time $TIMEOUT "$QB_URL/rest/version" 2>/dev/null | grep -o '"version":"[^"]*"' | cut -d'"' -f4 || echo "unknown")
    if [[ "$version" != "unknown" ]]; then
        success "QuickBuild version: $version"
        add_detail "server_version=$version"
        add_metric "quickbuild_server_version_info{version=\"$version\"} 1"
    else
        warning "Could not retrieve QuickBuild version"
        add_detail "server_version=unknown"
    fi
    
    # System status
    local system_status=$(curl -s --max-time $TIMEOUT "$QB_URL/rest/system/status" 2>/dev/null || echo "")
    if [[ -n "$system_status" ]]; then
        success "System status API is accessible"
        add_detail "system_status_accessible=true"
        add_metric "quickbuild_system_status_accessible 1"
        
        # Parse system metrics if available
        local memory_usage=$(echo "$system_status" | grep -o '"memoryUsage":[0-9]*' | cut -d: -f2 || echo "0")
        local cpu_usage=$(echo "$system_status" | grep -o '"cpuUsage":[0-9]*' | cut -d: -f2 || echo "0")
        
        if [[ "$memory_usage" -gt 0 ]]; then
            add_metric "quickbuild_server_memory_usage $memory_usage"
        fi
        if [[ "$cpu_usage" -gt 0 ]]; then
            add_metric "quickbuild_server_cpu_usage $cpu_usage"
        fi
    else
        warning "System status API is not accessible"
        add_detail "system_status_accessible=false"
        add_metric "quickbuild_system_status_accessible 0"
    fi
    
    return 0
}

check_agent_health() {
    log "Checking build agent health..."
    
    # Get agent list
    local agents_response=$(curl -s --max-time $TIMEOUT "$QB_URL/rest/agents" 2>/dev/null || echo "")
    if [[ -n "$agents_response" ]]; then
        local agent_count=$(echo "$agents_response" | grep -o '"name"' | wc -l || echo "0")
        local online_agents=$(echo "$agents_response" | grep -c '"online":true' || echo "0")
        
        success "Agent API is accessible"
        add_detail "agents_total=$agent_count"
        add_detail "agents_online=$online_agents"
        add_metric "quickbuild_agents_total $agent_count"
        add_metric "quickbuild_agents_online $online_agents"
        
        if [[ "$agent_count" -gt 0 ]]; then
            success "$agent_count total agents, $online_agents online"
        else
            warning "No build agents registered"
        fi
        
        # Check agent types if verbose
        if [[ "$VERBOSE" == "true" && "$agent_count" -gt 0 ]]; then
            local maven_agents=$(echo "$agents_response" | grep -c '"name":".*maven.*"' || echo "0")
            local node_agents=$(echo "$agents_response" | grep -c '"name":".*node.*"' || echo "0")
            local dotnet_agents=$(echo "$agents_response" | grep -c '"name":".*dotnet.*"' || echo "0")
            
            add_metric "quickbuild_agents_maven $maven_agents"
            add_metric "quickbuild_agents_node $node_agents"
            add_metric "quickbuild_agents_dotnet $dotnet_agents"
        fi
    else
        error "Could not retrieve agent information"
        add_detail "agents_accessible=false"
        add_metric "quickbuild_agents_accessible 0"
        return 1
    fi
    
    return 0
}

check_network_health() {
    log "Checking network connectivity..."
    
    # Check QuickBuild server port
    if nc -z localhost 8810 2>/dev/null; then
        success "QuickBuild server port 8810 is accessible"
        add_detail "server_port_accessible=true"
        add_metric "quickbuild_network_server_port_accessible 1"
    else
        error "QuickBuild server port 8810 is not accessible"
        add_detail "server_port_accessible=false"
        add_metric "quickbuild_network_server_port_accessible 0"
    fi
    
    # Check database port
    if nc -z localhost 1433 2>/dev/null; then
        success "Database port 1433 is accessible"
        add_detail "database_port_accessible=true"
        add_metric "quickbuild_network_database_port_accessible 1"
    else
        warning "Database port 1433 is not accessible (may be internal only)"
        add_detail "database_port_accessible=false"
        add_metric "quickbuild_network_database_port_accessible 0"
    fi
    
    # DNS resolution test
    if nslookup localhost >/dev/null 2>&1; then
        success "DNS resolution is working"
        add_detail "dns_resolution=true"
        add_metric "quickbuild_network_dns_resolution 1"
    else
        warning "DNS resolution issues detected"
        add_detail "dns_resolution=false"
        add_metric "quickbuild_network_dns_resolution 0"
    fi
    
    return 0
}

check_storage_health() {
    log "Checking storage health..."
    
    # Check disk space
    local disk_usage=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
    if [[ "$disk_usage" -lt 90 ]]; then
        success "Disk usage is acceptable ($disk_usage%)"
        add_detail "disk_usage_percent=$disk_usage"
        add_metric "quickbuild_storage_disk_usage_percent $disk_usage"
    else
        error "Disk usage is critical ($disk_usage%)"
        add_detail "disk_usage_percent=$disk_usage"
        add_metric "quickbuild_storage_disk_usage_percent $disk_usage"
    fi
    
    # Check if QuickBuild data directory is accessible
    local data_check=$(curl -s --max-time $TIMEOUT "$QB_URL/rest/system/storage" 2>/dev/null || echo "")
    if [[ -n "$data_check" ]]; then
        success "Storage API is accessible"
        add_detail "storage_api_accessible=true"
        add_metric "quickbuild_storage_api_accessible 1"
    else
        warning "Storage API is not accessible"
        add_detail "storage_api_accessible=false"
        add_metric "quickbuild_storage_api_accessible 0"
    fi
    
    return 0
}

# Output formatting functions
output_text() {
    echo ""
    echo "=========================================="
    echo "QuickBuild Health Check Report"
    echo "=========================================="
    echo "Component: $COMPONENT"
    echo "Timestamp: $(date)"
    echo "Overall Status: $HEALTH_STATUS"
    echo ""
    
    if [[ ${#HEALTH_DETAILS[@]} -gt 0 ]]; then
        echo "Details:"
        for detail in "${HEALTH_DETAILS[@]}"; do
            echo "  $detail"
        done
        echo ""
    fi
    
    case "$HEALTH_STATUS" in
        "healthy")
            echo -e "${GREEN}✓ All health checks passed${NC}"
            ;;
        "degraded")
            echo -e "${YELLOW}⚠ Some health checks failed or returned warnings${NC}"
            ;;
        "unhealthy")
            echo -e "${RED}✗ Critical health check failures detected${NC}"
            ;;
    esac
    echo "=========================================="
}

output_json() {
    local json_details=""
    local json_metrics=""
    
    # Build details JSON
    if [[ ${#HEALTH_DETAILS[@]} -gt 0 ]]; then
        for detail in "${HEALTH_DETAILS[@]}"; do
            local key=$(echo "$detail" | cut -d= -f1)
            local value=$(echo "$detail" | cut -d= -f2-)
            if [[ -n "$json_details" ]]; then
                json_details+=","
            fi
            json_details+="\"$key\":\"$value\""
        done
    fi
    
    # Build metrics JSON
    if [[ ${#HEALTH_METRICS[@]} -gt 0 ]]; then
        for metric in "${HEALTH_METRICS[@]}"; do
            local name=$(echo "$metric" | awk '{print $1}')
            local value=$(echo "$metric" | awk '{print $2}')
            if [[ -n "$json_metrics" ]]; then
                json_metrics+=","
            fi
            json_metrics+="\"$name\":$value"
        done
    fi
    
    cat << EOF
{
  "component": "$COMPONENT",
  "status": "$HEALTH_STATUS",
  "timestamp": "$(date -Iseconds)",
  "details": {$json_details},
  "metrics": {$json_metrics}
}
EOF
}

output_prometheus() {
    echo "# HELP quickbuild_health_status QuickBuild component health status"
    echo "# TYPE quickbuild_health_status gauge"
    
    local status_value=0
    case "$HEALTH_STATUS" in
        "healthy") status_value=1 ;;
        "degraded") status_value=0.5 ;;
        "unhealthy") status_value=0 ;;
    esac
    
    echo "quickbuild_health_status{component=\"$COMPONENT\"} $status_value"
    
    # Output metrics
    for metric in "${HEALTH_METRICS[@]}"; do
        echo "$metric"
    done
}

# Main execution
main() {
    case "$COMPONENT" in
        "database")
            check_database_health
            ;;
        "server")
            check_server_health
            ;;
        "agent")
            check_agent_health
            ;;
        "network")
            check_network_health
            ;;
        "storage")
            check_storage_health
            ;;
        "all")
            check_database_health || true
            check_server_health || true
            check_agent_health || true
            check_network_health || true
            check_storage_health || true
            ;;
        *)
            error "Unknown component: $COMPONENT"
            usage
            exit 1
            ;;
    esac
    
    # Output results
    case "$OUTPUT_FORMAT" in
        "text")
            output_text
            ;;
        "json")
            output_json
            ;;
        "prometheus")
            output_prometheus
            ;;
        *)
            error "Unknown output format: $OUTPUT_FORMAT"
            exit 1
            ;;
    esac
    
    # Exit with appropriate code
    case "$HEALTH_STATUS" in
        "healthy")
            exit 0
            ;;
        "degraded")
            exit 1
            ;;
        "unhealthy")
            exit 2
            ;;
    esac
}

# Run main function
main