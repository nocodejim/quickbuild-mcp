#!/bin/bash
# QuickBuild 14 Monitoring Script
# Continuous monitoring and health checking for QuickBuild deployment
# Provides real-time status, metrics, and alerting capabilities

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_PROJECT="${COMPOSE_PROJECT_NAME:-quickbuild14}"
NAMESPACE="quickbuild"
REFRESH_INTERVAL=10
LOG_FILE="/tmp/qb_monitor.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Monitoring state
MONITORING=true
ALERT_THRESHOLD_CPU=80
ALERT_THRESHOLD_MEMORY=85
ALERT_THRESHOLD_DISK=90

# Logging functions
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
    echo "[ERROR] $1" >> "$LOG_FILE"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
    echo "[WARNING] $1" >> "$LOG_FILE"
}

alert() {
    echo -e "${RED}[ALERT]${NC} $1" >&2
    echo "[ALERT] $1" >> "$LOG_FILE"
}

# Usage function
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -e, --environment ENV    Deployment environment (docker-compose|kubernetes)"
    echo "  -n, --namespace NS       Kubernetes namespace (default: quickbuild)"
    echo "  -p, --project NAME       Docker Compose project name"
    echo "  -i, --interval SEC       Refresh interval in seconds (default: 10)"
    echo "  -l, --log-file FILE      Log file path (default: /tmp/qb_monitor.log)"
    echo "  --cpu-threshold PCT      CPU alert threshold percentage (default: 80)"
    echo "  --memory-threshold PCT   Memory alert threshold percentage (default: 85)"
    echo "  --disk-threshold PCT     Disk alert threshold percentage (default: 90)"
    echo "  -o, --once              Run once and exit (no continuous monitoring)"
    echo "  -h, --help              Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 -e docker-compose"
    echo "  $0 -e kubernetes -n quickbuild -i 30"
    echo "  $0 -e docker-compose --once"
    echo ""
    echo "Interactive Commands (during monitoring):"
    echo "  q - Quit monitoring"
    echo "  r - Refresh display"
    echo "  s - Show detailed status"
    echo "  l - Show recent logs"
    echo ""
}

# Parse command line arguments
ENVIRONMENT=""
RUN_ONCE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -e|--environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -p|--project)
            COMPOSE_PROJECT="$2"
            shift 2
            ;;
        -i|--interval)
            REFRESH_INTERVAL="$2"
            shift 2
            ;;
        -l|--log-file)
            LOG_FILE="$2"
            shift 2
            ;;
        --cpu-threshold)
            ALERT_THRESHOLD_CPU="$2"
            shift 2
            ;;
        --memory-threshold)
            ALERT_THRESHOLD_MEMORY="$2"
            shift 2
            ;;
        --disk-threshold)
            ALERT_THRESHOLD_DISK="$2"
            shift 2
            ;;
        -o|--once)
            RUN_ONCE=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Auto-detect environment if not specified
if [[ -z "$ENVIRONMENT" ]]; then
    if command -v docker-compose >/dev/null 2>&1 && [[ -f "$PROJECT_ROOT/docker-compose.yml" ]]; then
        ENVIRONMENT="docker-compose"
    elif command -v kubectl >/dev/null 2>&1; then
        ENVIRONMENT="kubernetes"
    else
        error "Could not auto-detect environment. Please specify with -e"
        exit 1
    fi
fi

# Initialize log file
echo "QuickBuild Monitoring Started - $(date)" > "$LOG_FILE"

# Signal handlers
cleanup() {
    MONITORING=false
    log "Monitoring stopped"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Utility functions
format_bytes() {
    local bytes=$1
    if [[ $bytes -gt 1073741824 ]]; then
        echo "$(( bytes / 1073741824 ))GB"
    elif [[ $bytes -gt 1048576 ]]; then
        echo "$(( bytes / 1048576 ))MB"
    elif [[ $bytes -gt 1024 ]]; then
        echo "$(( bytes / 1024 ))KB"
    else
        echo "${bytes}B"
    fi
}

get_percentage() {
    local used=$1
    local total=$2
    if [[ $total -gt 0 ]]; then
        echo $(( used * 100 / total ))
    else
        echo "0"
    fi
}

# Docker Compose monitoring functions
monitor_docker_compose() {
    clear
    echo -e "${CYAN}QuickBuild 14 Monitoring Dashboard - Docker Compose${NC}"
    echo -e "${CYAN}=================================================${NC}"
    echo "Project: $COMPOSE_PROJECT"
    echo "Refresh: ${REFRESH_INTERVAL}s | Time: $(date +'%H:%M:%S')"
    echo ""
    
    # Container status
    echo -e "${BLUE}Container Status:${NC}"
    local containers=$(docker-compose -p "$COMPOSE_PROJECT" ps 2>/dev/null || echo "")
    if [[ -n "$containers" ]]; then
        echo "$containers"
    else
        echo -e "${RED}No containers found${NC}"
    fi
    echo ""
    
    # Resource usage
    echo -e "${BLUE}Resource Usage:${NC}"
    local container_ids=$(docker-compose -p "$COMPOSE_PROJECT" ps -q 2>/dev/null)
    if [[ -n "$container_ids" ]]; then
        docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}\t{{.BlockIO}}" $container_ids 2>/dev/null || echo "Resource stats unavailable"
        
        # Check for alerts
        while read -r line; do
            if [[ "$line" =~ ([0-9]+\.[0-9]+)% ]]; then
                local cpu_usage=${BASH_REMATCH[1]%.*}
                if [[ $cpu_usage -gt $ALERT_THRESHOLD_CPU ]]; then
                    alert "High CPU usage detected: ${cpu_usage}%"
                fi
            fi
        done <<< "$(docker stats --no-stream --format "{{.CPUPerc}}" $container_ids 2>/dev/null)"
    else
        echo -e "${RED}No containers running${NC}"
    fi
    echo ""
    
    # Volume usage
    echo -e "${BLUE}Volume Usage:${NC}"
    local volumes=$(docker volume ls | grep "$COMPOSE_PROJECT" 2>/dev/null || echo "")
    if [[ -n "$volumes" ]]; then
        echo "$volumes"
    else
        echo "No volumes found"
    fi
    echo ""
    
    # Network status
    echo -e "${BLUE}Network Status:${NC}"
    local network=$(docker network ls | grep "${COMPOSE_PROJECT}_qb_net" 2>/dev/null || echo "")
    if [[ -n "$network" ]]; then
        echo "$network"
    else
        echo -e "${YELLOW}Custom network not found${NC}"
    fi
    echo ""
    
    # QuickBuild specific checks
    check_quickbuild_health "http://localhost:8810"
}

# Kubernetes monitoring functions
monitor_kubernetes() {
    clear
    echo -e "${CYAN}QuickBuild 14 Monitoring Dashboard - Kubernetes${NC}"
    echo -e "${CYAN}=============================================${NC}"
    echo "Namespace: $NAMESPACE"
    echo "Refresh: ${REFRESH_INTERVAL}s | Time: $(date +'%H:%M:%S')"
    echo ""
    
    # Pod status
    echo -e "${BLUE}Pod Status:${NC}"
    kubectl get pods -n "$NAMESPACE" 2>/dev/null || echo -e "${RED}No pods found or namespace inaccessible${NC}"
    echo ""
    
    # Service status
    echo -e "${BLUE}Service Status:${NC}"
    kubectl get services -n "$NAMESPACE" 2>/dev/null || echo "No services found"
    echo ""
    
    # PVC status
    echo -e "${BLUE}Persistent Volume Claims:${NC}"
    kubectl get pvc -n "$NAMESPACE" 2>/dev/null || echo "No PVCs found"
    echo ""
    
    # Resource usage (if metrics server is available)
    echo -e "${BLUE}Resource Usage:${NC}"
    local pod_metrics=$(kubectl top pods -n "$NAMESPACE" 2>/dev/null || echo "")
    if [[ -n "$pod_metrics" ]]; then
        echo "$pod_metrics"
    else
        echo -e "${YELLOW}Metrics not available (metrics server may not be installed)${NC}"
    fi
    echo ""
    
    # Node resource usage
    echo -e "${BLUE}Node Resource Usage:${NC}"
    kubectl top nodes 2>/dev/null || echo -e "${YELLOW}Node metrics not available${NC}"
    echo ""
    
    # QuickBuild specific checks
    local qb_service=$(kubectl get service qb-server-service -n "$NAMESPACE" -o jsonpath='{.spec.clusterIP}' 2>/dev/null || echo "")
    if [[ -n "$qb_service" ]]; then
        check_quickbuild_health "http://${qb_service}:8810"
    fi
}

# QuickBuild health checks
check_quickbuild_health() {
    local qb_url="$1"
    
    echo -e "${BLUE}QuickBuild Health:${NC}"
    
    # Basic connectivity
    local status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$qb_url" 2>/dev/null || echo "000")
    if [[ "$status" == "200" ]]; then
        echo -e "${GREEN}✓ Web interface accessible${NC}"
        
        # Version check
        local version=$(curl -s --max-time 5 "$qb_url/rest/version" 2>/dev/null | grep -o '"version":"[^"]*"' | cut -d'"' -f4 || echo "unknown")
        if [[ "$version" != "unknown" ]]; then
            echo "  Version: $version"
        fi
        
        # Agent count
        local agents=$(curl -s --max-time 5 "$qb_url/rest/agents" 2>/dev/null | grep -o '"name"' | wc -l || echo "0")
        echo "  Connected agents: $agents"
        
        # Build queue
        local queue=$(curl -s --max-time 5 "$qb_url/rest/builds/queue" 2>/dev/null | grep -o '"id"' | wc -l || echo "0")
        echo "  Queued builds: $queue"
        
    else
        echo -e "${RED}✗ Web interface not accessible (HTTP $status)${NC}"
        alert "QuickBuild web interface is not accessible"
    fi
}

# Interactive command handler
handle_input() {
    if [[ "$RUN_ONCE" == "true" ]]; then
        return
    fi
    
    # Check for input without blocking
    if read -t 0; then
        read -n 1 key
        case "$key" in
            q|Q)
                MONITORING=false
                ;;
            r|R)
                # Force refresh (do nothing, will refresh on next loop)
                ;;
            s|S)
                show_detailed_status
                ;;
            l|L)
                show_recent_logs
                ;;
        esac
    fi
}

# Show detailed status
show_detailed_status() {
    clear
    echo -e "${CYAN}Detailed System Status${NC}"
    echo -e "${CYAN}===================${NC}"
    
    case "$ENVIRONMENT" in
        "docker-compose")
            echo "Docker system info:"
            docker system df 2>/dev/null || echo "Docker system info unavailable"
            echo ""
            echo "Container logs (last 10 lines):"
            docker-compose -p "$COMPOSE_PROJECT" logs --tail=10 2>/dev/null || echo "Logs unavailable"
            ;;
        "kubernetes")
            echo "Cluster info:"
            kubectl cluster-info 2>/dev/null || echo "Cluster info unavailable"
            echo ""
            echo "Recent events:"
            kubectl get events -n "$NAMESPACE" --sort-by='.lastTimestamp' | tail -10 2>/dev/null || echo "Events unavailable"
            ;;
    esac
    
    echo ""
    echo "Press any key to return to main dashboard..."
    read -n 1
}

# Show recent logs
show_recent_logs() {
    clear
    echo -e "${CYAN}Recent Monitor Logs${NC}"
    echo -e "${CYAN}=================${NC}"
    
    if [[ -f "$LOG_FILE" ]]; then
        tail -20 "$LOG_FILE"
    else
        echo "No log file found"
    fi
    
    echo ""
    echo "Press any key to return to main dashboard..."
    read -n 1
}

# Main monitoring loop
main() {
    log "Starting QuickBuild monitoring (Environment: $ENVIRONMENT)"
    
    if [[ "$RUN_ONCE" == "true" ]]; then
        case "$ENVIRONMENT" in
            "docker-compose")
                monitor_docker_compose
                ;;
            "kubernetes")
                monitor_kubernetes
                ;;
        esac
        return 0
    fi
    
    echo -e "${GREEN}QuickBuild Monitoring Started${NC}"
    echo "Environment: $ENVIRONMENT"
    echo "Press 'q' to quit, 'r' to refresh, 's' for detailed status, 'l' for logs"
    echo ""
    
    while [[ "$MONITORING" == "true" ]]; do
        case "$ENVIRONMENT" in
            "docker-compose")
                monitor_docker_compose
                ;;
            "kubernetes")
                monitor_kubernetes
                ;;
        esac
        
        # Show interactive commands
        echo -e "${CYAN}Commands: [q]uit | [r]efresh | [s]tatus | [l]ogs${NC}"
        
        # Handle input and wait
        for ((i=0; i<REFRESH_INTERVAL; i++)); do
            handle_input
            if [[ "$MONITORING" == "false" ]]; then
                break
            fi
            sleep 1
        done
    done
    
    log "Monitoring stopped"
}

# Run main function
main