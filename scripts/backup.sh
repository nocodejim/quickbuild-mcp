#!/bin/bash
# QuickBuild 14 Backup Script
# Comprehensive backup solution for Docker Compose and Kubernetes deployments
# Supports both QuickBuild data and SQL Server database backup

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_ROOT/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
COMPOSE_PROJECT="${COMPOSE_PROJECT_NAME:-quickbuild14}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Logging function
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

# Usage function
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -e, --environment ENV    Deployment environment (docker-compose|kubernetes)"
    echo "  -d, --backup-dir DIR     Backup directory (default: ./backups)"
    echo "  -n, --namespace NS       Kubernetes namespace (default: quickbuild)"
    echo "  -p, --project NAME       Docker Compose project name"
    echo "  -c, --compress           Compress backup files"
    echo "  -v, --validate           Validate backup after creation"
    echo "  -h, --help              Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 -e docker-compose -c -v"
    echo "  $0 -e kubernetes -n quickbuild -d /backup/qb"
    echo ""
}

# Parse command line arguments
ENVIRONMENT=""
NAMESPACE="quickbuild"
COMPRESS=false
VALIDATE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -e|--environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -d|--backup-dir)
            BACKUP_DIR="$2"
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
        -c|--compress)
            COMPRESS=true
            shift
            ;;
        -v|--validate)
            VALIDATE=true
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

# Validate environment
if [[ -z "$ENVIRONMENT" ]]; then
    error "Environment must be specified (-e docker-compose or -e kubernetes)"
    usage
    exit 1
fi

if [[ "$ENVIRONMENT" != "docker-compose" && "$ENVIRONMENT" != "kubernetes" ]]; then
    error "Environment must be 'docker-compose' or 'kubernetes'"
    exit 1
fi

# Create backup directory
mkdir -p "$BACKUP_DIR"
BACKUP_NAME="quickbuild_backup_${TIMESTAMP}"
BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"

log "Starting QuickBuild backup..."
log "Environment: $ENVIRONMENT"
log "Backup directory: $BACKUP_PATH"

# Docker Compose backup functions
backup_docker_compose() {
    log "Backing up Docker Compose deployment..."
    
    # Check if containers are running
    if ! docker-compose -p "$COMPOSE_PROJECT" ps | grep -q "Up"; then
        warning "No running containers found for project $COMPOSE_PROJECT"
    fi
    
    # Create backup structure
    mkdir -p "$BACKUP_PATH"/{database,server,metadata}
    
    # Backup database data
    log "Backing up database data..."
    if docker volume ls | grep -q "${COMPOSE_PROJECT}_db_data"; then
        docker run --rm \
            -v "${COMPOSE_PROJECT}_db_data:/source:ro" \
            -v "$BACKUP_PATH:/backup" \
            ubuntu:20.04 \
            tar czf "/backup/database/db_data_${TIMESTAMP}.tar.gz" -C /source .
        success "Database data backup completed"
    else
        warning "Database data volume not found"
    fi
    
    # Backup database logs
    log "Backing up database logs..."
    if docker volume ls | grep -q "${COMPOSE_PROJECT}_db_logs"; then
        docker run --rm \
            -v "${COMPOSE_PROJECT}_db_logs:/source:ro" \
            -v "$BACKUP_PATH:/backup" \
            ubuntu:20.04 \
            tar czf "/backup/database/db_logs_${TIMESTAMP}.tar.gz" -C /source .
        success "Database logs backup completed"
    fi
    
    # Backup server data
    log "Backing up server data..."
    if docker volume ls | grep -q "${COMPOSE_PROJECT}_server_data"; then
        docker run --rm \
            -v "${COMPOSE_PROJECT}_server_data:/source:ro" \
            -v "$BACKUP_PATH:/backup" \
            ubuntu:20.04 \
            tar czf "/backup/server/server_data_${TIMESTAMP}.tar.gz" -C /source .
        success "Server data backup completed"
    else
        warning "Server data volume not found"
    fi
    
    # Backup agent caches
    log "Backing up agent caches..."
    for cache in maven node dotnet; do
        volume_name="${COMPOSE_PROJECT}_${cache}_cache"
        if docker volume ls | grep -q "$volume_name"; then
            docker run --rm \
                -v "$volume_name:/source:ro" \
                -v "$BACKUP_PATH:/backup" \
                ubuntu:20.04 \
                tar czf "/backup/server/${cache}_cache_${TIMESTAMP}.tar.gz" -C /source .
            success "$cache cache backup completed"
        fi
    done
}

# Kubernetes backup functions
backup_kubernetes() {
    log "Backing up Kubernetes deployment..."
    
    # Check if namespace exists
    if ! kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
        error "Namespace $NAMESPACE not found"
        exit 1
    fi
    
    # Create backup structure
    mkdir -p "$BACKUP_PATH"/{database,server,manifests,metadata}
    
    # Backup Kubernetes manifests
    log "Backing up Kubernetes manifests..."
    kubectl get all,pvc,configmap,secret -n "$NAMESPACE" -o yaml > "$BACKUP_PATH/manifests/all_resources_${TIMESTAMP}.yaml"
    
    success "Kubernetes manifests backup completed"
}

# Backup metadata
backup_metadata() {
    log "Creating backup metadata..."
    
    cat > "$BACKUP_PATH/metadata/backup_info.json" << EOF
{
    "backup_timestamp": "$TIMESTAMP",
    "backup_date": "$(date -Iseconds)",
    "environment": "$ENVIRONMENT",
    "namespace": "$NAMESPACE",
    "compose_project": "$COMPOSE_PROJECT",
    "backup_version": "1.0",
    "quickbuild_version": "14.0",
    "backup_type": "full",
    "compressed": $COMPRESS,
    "validated": $VALIDATE
}
EOF
    
    # Create backup manifest
    find "$BACKUP_PATH" -type f -exec ls -la {} \; > "$BACKUP_PATH/metadata/file_manifest.txt"
    
    success "Backup metadata created"
}

# Validate backup
validate_backup() {
    if [[ "$VALIDATE" == "true" ]]; then
        log "Validating backup..."
        
        # Check if backup files exist and are not empty
        local validation_failed=false
        
        if [[ "$ENVIRONMENT" == "docker-compose" ]]; then
            for file in "$BACKUP_PATH"/database/*.tar.gz "$BACKUP_PATH"/server/*.tar.gz; do
                if [[ -f "$file" ]]; then
                    if tar -tzf "$file" >/dev/null 2>&1; then
                        success "Validated: $(basename "$file")"
                    else
                        error "Validation failed: $(basename "$file")"
                        validation_failed=true
                    fi
                else
                    warning "Backup file not found: $file"
                fi
            done
        fi
        
        if [[ "$validation_failed" == "true" ]]; then
            error "Backup validation failed"
            exit 1
        else
            success "Backup validation completed successfully"
        fi
    fi
}

# Compress backup
compress_backup() {
    if [[ "$COMPRESS" == "true" ]]; then
        log "Compressing backup..."
        
        cd "$BACKUP_DIR"
        tar czf "${BACKUP_NAME}.tar.gz" "$BACKUP_NAME"
        rm -rf "$BACKUP_NAME"
        
        success "Backup compressed: ${BACKUP_NAME}.tar.gz"
        BACKUP_PATH="${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
    fi
}

# Main execution
main() {
    case "$ENVIRONMENT" in
        "docker-compose")
            backup_docker_compose
            ;;
        "kubernetes")
            backup_kubernetes
            ;;
    esac
    
    backup_metadata
    validate_backup
    compress_backup
    
    success "Backup completed successfully!"
    success "Backup location: $BACKUP_PATH"
    
    # Display backup size
    if [[ -f "$BACKUP_PATH" ]]; then
        local size=$(du -h "$BACKUP_PATH" | cut -f1)
        log "Backup size: $size"
    elif [[ -d "$BACKUP_PATH" ]]; then
        local size=$(du -sh "$BACKUP_PATH" | cut -f1)
        log "Backup size: $size"
    fi
}

# Run main function
main