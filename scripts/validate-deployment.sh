#!/bin/bash
# QuickBuild 14 Deployment Validation Script
# Comprehensive validation of containerized QuickBuild deployment
# Verifies system health, connectivity, and proper operation

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_PROJECT="${COMPOSE_PROJECT_NAME:-quickbuild14}"
NAMESPACE="quickbuild"
TIMEOUT=30
MAX_RETRIES=5

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Test results tracking
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

# Logging functions
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

test_start() {
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    echo -e "${BLUE}[TEST $TESTS_TOTAL]${NC} $1"
}

test_pass() {
    TESTS_PASSED=$((TESTS_PASSED + 1))
    success "✓ $1"
}

test_fail() {
    TESTS_FAILED=$((TESTS_FAILED + 1))
    error "✗ $1"
}

# Usage function
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -e, --environment ENV    Deployment environment (docker-compose|kubernetes)"
    echo "  -n, --namespace NS       Kubernetes namespace (default: quickbuild)"
    echo "  -p, --project NAME       Docker Compose project name"
    echo "  -t, --timeout SEC        Timeout for checks (default: 30)"
    echo "  -q, --quick             Run quick validation (skip detailed checks)"
    echo "  -v, --verbose           Verbose output"
    echo "  -h, --help              Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 -e docker-compose"
    echo "  $0 -e kubernetes -n quickbuild"
    echo "  $0 -e docker-compose --quick"
    echo ""
}

# Parse command line arguments
ENVIRONMENT=""
QUICK=false
VERBOSE=false

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
        -t|--timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        -q|--quick)
            QUICK=true
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
        log "Auto-detected environment: docker-compose"
    elif command -v kubectl >/dev/null 2>&1; then
        ENVIRONMENT="kubernetes"
        log "Auto-detected environment: kubernetes"
    else
        error "Could not auto-detect environment. Please specify with -e"
        exit 1
    fi
fi

# Utility functions
wait_for_service() {
    local service_name="$1"
    local host="$2"
    local port="$3"
    local max_wait="${4:-$TIMEOUT}"
    
    local elapsed=0
    while [ $elapsed -lt $max_wait ]; do
        if nc -z "$host" "$port" 2>/dev/null; then
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    return 1
}

check_http_endpoint() {
    local url="$1"
    local expected_status="${2:-200}"
    
    local status=$(curl -s -o /dev/null -w "%{http_code}" --max-time $TIMEOUT "$url" 2>/dev/null || echo "000")
    
    if [[ "$status" == "$expected_status" ]]; then
        return 0
    else
        if [[ "$VERBOSE" == "true" ]]; then
            log "HTTP check failed: $url returned $status (expected $expected_status)"
        fi
        return 1
    fi
}

# Docker Compose validation functions
validate_docker_compose() {
    log "Validating Docker Compose deployment..."
    
    # Test 1: Check if Docker Compose is available
    test_start "Docker Compose availability"
    if command -v docker-compose >/dev/null 2>&1; then
        test_pass "Docker Compose is available"
    else
        test_fail "Docker Compose not found"
        return 1
    fi
    
    # Test 2: Check if compose file exists
    test_start "Docker Compose file existence"
    if [[ -f "$PROJECT_ROOT/docker-compose.yml" ]]; then
        test_pass "docker-compose.yml found"
    else
        test_fail "docker-compose.yml not found in $PROJECT_ROOT"
        return 1
    fi
    
    # Test 3: Check container status
    test_start "Container status check"
    local containers=$(docker-compose -p "$COMPOSE_PROJECT" ps -q 2>/dev/null || echo "")
    if [[ -n "$containers" ]]; then
        local running_containers=$(docker-compose -p "$COMPOSE_PROJECT" ps | grep -c "Up" || echo "0")
        if [[ "$running_containers" -gt 0 ]]; then
            test_pass "$running_containers containers are running"
        else
            test_fail "No containers are running"
        fi
    else
        test_fail "No containers found for project $COMPOSE_PROJECT"
    fi
    
    # Test 4: Database connectivity
    test_start "Database connectivity"
    if wait_for_service "database" "localhost" "1433" 10; then
        test_pass "Database is accessible on port 1433"
    else
        test_fail "Database is not accessible"
    fi
    
    # Test 5: QuickBuild server connectivity
    test_start "QuickBuild server connectivity"
    if wait_for_service "qb-server" "localhost" "8810" 15; then
        test_pass "QuickBuild server is accessible on port 8810"
        
        # Test HTTP endpoint
        if check_http_endpoint "http://localhost:8810"; then
            test_pass "QuickBuild web interface is responding"
        else
            test_fail "QuickBuild web interface is not responding"
        fi
    else
        test_fail "QuickBuild server is not accessible"
    fi
    
    # Test 6: Volume mounts
    test_start "Volume mounts validation"
    local volumes=$(docker volume ls | grep "$COMPOSE_PROJECT" | wc -l)
    if [[ "$volumes" -gt 0 ]]; then
        test_pass "$volumes Docker volumes found"
    else
        test_fail "No Docker volumes found for project"
    fi
    
    # Test 7: Network connectivity
    test_start "Network connectivity"
    local network=$(docker network ls | grep "${COMPOSE_PROJECT}_qb_net" || echo "")
    if [[ -n "$network" ]]; then
        test_pass "Custom network found"
    else
        test_fail "Custom network not found"
    fi
}

# Kubernetes validation functions
validate_kubernetes() {
    log "Validating Kubernetes deployment..."
    
    # Test 1: Check if kubectl is available
    test_start "kubectl availability"
    if command -v kubectl >/dev/null 2>&1; then
        test_pass "kubectl is available"
    else
        test_fail "kubectl not found"
        return 1
    fi
    
    # Test 2: Check namespace
    test_start "Namespace existence"
    if kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
        test_pass "Namespace $NAMESPACE exists"
    else
        test_fail "Namespace $NAMESPACE not found"
        return 1
    fi
    
    # Test 3: Check pod status
    test_start "Pod status check"
    local pods=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)
    if [[ "$pods" -gt 0 ]]; then
        local running_pods=$(kubectl get pods -n "$NAMESPACE" --no-headers | grep -c "Running" || echo "0")
        if [[ "$running_pods" -gt 0 ]]; then
            test_pass "$running_pods pods are running"
        else
            test_fail "No pods are running"
        fi
    else
        test_fail "No pods found in namespace $NAMESPACE"
    fi
    
    # Test 4: Check services
    test_start "Service availability"
    local services=$(kubectl get services -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)
    if [[ "$services" -gt 0 ]]; then
        test_pass "$services services found"
    else
        test_fail "No services found"
    fi
    
    # Test 5: Check PVCs
    test_start "Persistent Volume Claims"
    local pvcs=$(kubectl get pvc -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)
    if [[ "$pvcs" -gt 0 ]]; then
        local bound_pvcs=$(kubectl get pvc -n "$NAMESPACE" --no-headers | grep -c "Bound" || echo "0")
        test_pass "$bound_pvcs/$pvcs PVCs are bound"
    else
        test_fail "No PVCs found"
    fi
    
    # Test 6: Check ingress (if exists)
    test_start "Ingress configuration"
    local ingress=$(kubectl get ingress -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)
    if [[ "$ingress" -gt 0 ]]; then
        test_pass "Ingress configuration found"
    else
        warning "No ingress configuration found (external access may not be available)"
    fi
}

# Common validation functions
validate_quickbuild_functionality() {
    if [[ "$QUICK" == "true" ]]; then
        log "Skipping detailed QuickBuild functionality tests (quick mode)"
        return 0
    fi
    
    log "Validating QuickBuild functionality..."
    
    # Determine QuickBuild URL based on environment
    local qb_url=""
    case "$ENVIRONMENT" in
        "docker-compose")
            qb_url="http://localhost:8810"
            ;;
        "kubernetes")
            # Try to get ingress URL or use port-forward
            qb_url="http://localhost:8810"  # Assuming port-forward or ingress
            ;;
    esac
    
    # Test QuickBuild REST API
    test_start "QuickBuild REST API"
    if check_http_endpoint "$qb_url/rest/version"; then
        test_pass "QuickBuild REST API is accessible"
        
        # Get version information
        local version=$(curl -s --max-time $TIMEOUT "$qb_url/rest/version" 2>/dev/null | grep -o '"version":"[^"]*"' | cut -d'"' -f4 || echo "unknown")
        if [[ "$version" != "unknown" ]]; then
            log "QuickBuild version: $version"
        fi
    else
        test_fail "QuickBuild REST API is not accessible"
    fi
    
    # Test agent connectivity (if agents are running)
    test_start "Build agent connectivity"
    local agents_response=$(curl -s --max-time $TIMEOUT "$qb_url/rest/agents" 2>/dev/null || echo "")
    if [[ -n "$agents_response" ]]; then
        local agent_count=$(echo "$agents_response" | grep -o '"name"' | wc -l || echo "0")
        if [[ "$agent_count" -gt 0 ]]; then
            test_pass "$agent_count build agents connected"
        else
            warning "No build agents connected (this may be expected for a fresh deployment)"
        fi
    else
        test_fail "Could not retrieve agent information"
    fi
}

# Performance and resource validation
validate_performance() {
    if [[ "$QUICK" == "true" ]]; then
        log "Skipping performance validation (quick mode)"
        return 0
    fi
    
    log "Validating system performance..."
    
    case "$ENVIRONMENT" in
        "docker-compose")
            # Check Docker resource usage
            test_start "Docker resource usage"
            local containers=$(docker-compose -p "$COMPOSE_PROJECT" ps -q 2>/dev/null)
            if [[ -n "$containers" ]]; then
                local stats=$(docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" $containers 2>/dev/null || echo "")
                if [[ -n "$stats" ]]; then
                    test_pass "Resource usage information available"
                    if [[ "$VERBOSE" == "true" ]]; then
                        echo "$stats"
                    fi
                else
                    test_fail "Could not retrieve resource usage"
                fi
            fi
            ;;
        "kubernetes")
            # Check Kubernetes resource usage
            test_start "Kubernetes resource usage"
            local pod_metrics=$(kubectl top pods -n "$NAMESPACE" 2>/dev/null || echo "")
            if [[ -n "$pod_metrics" ]]; then
                test_pass "Pod metrics available"
                if [[ "$VERBOSE" == "true" ]]; then
                    echo "$pod_metrics"
                fi
            else
                warning "Pod metrics not available (metrics server may not be installed)"
            fi
            ;;
    esac
}

# Generate validation report
generate_report() {
    echo ""
    echo "=========================================="
    echo "QuickBuild Deployment Validation Report"
    echo "=========================================="
    echo "Environment: $ENVIRONMENT"
    echo "Timestamp: $(date)"
    echo "Tests Total: $TESTS_TOTAL"
    echo "Tests Passed: $TESTS_PASSED"
    echo "Tests Failed: $TESTS_FAILED"
    
    local success_rate=$((TESTS_PASSED * 100 / TESTS_TOTAL))
    echo "Success Rate: ${success_rate}%"
    
    if [[ $TESTS_FAILED -eq 0 ]]; then
        success "All validation tests passed! ✓"
        echo "QuickBuild deployment is healthy and ready for use."
    elif [[ $success_rate -ge 80 ]]; then
        warning "Most validation tests passed with some warnings"
        echo "QuickBuild deployment is mostly healthy but may need attention."
    else
        error "Multiple validation tests failed"
        echo "QuickBuild deployment has issues that need to be resolved."
    fi
    
    echo "=========================================="
}

# Main execution
main() {
    log "Starting QuickBuild deployment validation..."
    log "Environment: $ENVIRONMENT"
    log "Timeout: ${TIMEOUT}s"
    
    if [[ "$QUICK" == "true" ]]; then
        log "Running in quick mode"
    fi
    
    case "$ENVIRONMENT" in
        "docker-compose")
            validate_docker_compose
            ;;
        "kubernetes")
            validate_kubernetes
            ;;
        *)
            error "Unsupported environment: $ENVIRONMENT"
            exit 1
            ;;
    esac
    
    validate_quickbuild_functionality
    validate_performance
    
    generate_report
    
    # Exit with appropriate code
    if [[ $TESTS_FAILED -eq 0 ]]; then
        exit 0
    else
        exit 1
    fi
}

# Run main function
main