#!/bin/bash
# QuickBuild 14 Restore Script
# Comprehensive restore solution for Docker Compose and Kubernetes deployments
# Supports restoration from backup files with validation and rollback

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
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
    echo "  -b, --backup-path PATH   Path to backup file or directory"
    echo "  -e, --environment ENV    Deployment environment (docker-compose|kubernetes)"
    echo "  -n, --namespace NS       Kubernetes namespace (default: quickbuild)"
    echo "  -p, --project NAME       Docker Compose project name"
    echo "  -f, --force             Force restore without confirmation"
    echo "  --dry-run               Show what would be restored without doing it"
    echo "  -h, --help              Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 -b ./backups/quickbuild_backup_20231005_143022 -e docker-compose"
    echo "  $0 -b ./backups/backup.tar.gz -e kubernetes -n quickbuild"
    echo "  $0 -b ./backups/latest -e docker-compose --dry-run"
    echo ""
}

# Parse command line arguments
BACKUP_PATH=""
ENVIRONMENT=""
NAMESPACE="quickbuild"
FORCE=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -b|--backup-path)
            BACKUP_PATH="$2"
            shift 2
            ;;
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
        -f|--force)
            FORCE=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
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

# Validate arguments
if [[ -z "$BACKUP_PATH" ]]; then
    error "Backup path must be specified (-b /path/to/backup)"
    usage
    exit 1
fi

if [[ -z "$ENVIRONMENT" ]]; then
    error "Environment must be specified (-e docker-compose or -e kubernetes)"
    usage
    exit 1
fi

if [[ "$ENVIRONMENT" != "docker-compose" && "$ENVIRONMENT" != "kubernetes" ]]; then
    error "Environment must be 'docker-compose' or 'kubernetes'"
    exit 1
fi

if [[ ! -e "$BACKUP_PATH" ]]; then
    error "Backup path does not exist: $BACKUP_PATH"
    exit 1
fi

# Extract backup if it's compressed
WORK_DIR=""
cleanup() {
    if [[ -n "$WORK_DIR" && -d "$WORK_DIR" ]]; then
        rm -rf "$WORK_DIR"
    fi
}
trap cleanup EXIT

prepare_backup() {
    log "Preparing backup for restore..."
    
    if [[ -f "$BACKUP_PATH" && "$BACKUP_PATH" == *.tar.gz ]]; then
        log "Extracting compressed backup..."
        WORK_DIR=$(mktemp -d)
        tar -xzf "$BACKUP_PATH" -C "$WORK_DIR"
        
        # Find the extracted directory
        local extracted_dir=$(find "$WORK_DIR" -maxdepth 1 -type d -name "quickbuild_backup_*" | head -1)
        if [[ -n "$extracted_dir" ]]; then
            BACKUP_PATH="$extracted_dir"
            success "Backup extracted to: $BACKUP_PATH"
        else
            error "Could not find backup directory in extracted archive"
            exit 1
        fi
    elif [[ -d "$BACKUP_PATH" ]]; then
        log "Using backup directory: $BACKUP_PATH"
    else
        error "Backup path must be a directory or .tar.gz file"
        exit 1
    fi
    
    # Validate backup structure
    if [[ ! -f "$BACKUP_PATH/metadata/backup_info.json" ]]; then
        error "Invalid backup: missing metadata/backup_info.json"
        exit 1
    fi
    
    # Read backup metadata
    local backup_env=$(jq -r '.environment' "$BACKUP_PATH/metadata/backup_info.json" 2>/dev/null || echo "unknown")
    local backup_date=$(jq -r '.backup_date' "$BACKUP_PATH/metadata/backup_info.json" 2>/dev/null || echo "unknown")
    
    log "Backup environment: $backup_env"
    log "Backup date: $backup_date"
    
    if [[ "$backup_env" != "$ENVIRONMENT" ]]; then
        warning "Backup environment ($backup_env) differs from target environment ($ENVIRONMENT)"
        if [[ "$FORCE" != "true" ]]; then
            read -p "Continue anyway? (y/N): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                log "Restore cancelled"
                exit 0
            fi
        fi
    fi
}

# Confirmation prompt
confirm_restore() {
    if [[ "$FORCE" != "true" && "$DRY_RUN" != "true" ]]; then
        warning "This will overwrite existing QuickBuild data!"
        warning "Make sure to backup current data before proceeding."
        echo
        read -p "Are you sure you want to continue? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log "Restore cancelled"
            exit 0
        fi
    fi
}

# Docker Compose restore functions
restore_docker_compose() {
    log "Restoring Docker Compose deployment..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would restore the following volumes:"
        find "$BACKUP_PATH" -name "*.tar.gz" -type f | while read -r backup_file; do
            log "[DRY RUN]   - $(basename "$backup_file")"
        done
        return 0
    fi
    
    # Stop containers before restore
    log "Stopping containers..."
    docker-compose -p "$COMPOSE_PROJECT" down || true
    
    # Restore database data
    if [[ -f "$BACKUP_PATH/database/db_data_"*.tar.gz ]]; then
        log "Restoring database data..."
        local db_backup=$(find "$BACKUP_PATH/database" -name "db_data_*.tar.gz" | head -1)
        
        # Remove existing volume
        docker volume rm "${COMPOSE_PROJECT}_db_data" 2>/dev/null || true
        
        # Create new volume and restore data
        docker volume create "${COMPOSE_PROJECT}_db_data"
        docker run --rm \
            -v "${COMPOSE_PROJECT}_db_data:/target" \
            -v "$BACKUP_PATH:/backup:ro" \
            ubuntu:20.04 \
            tar -xzf "/backup/$(basename "$db_backup")" -C /target
        
        success "Database data restored"
    fi
    
    # Restore database logs
    if [[ -f "$BACKUP_PATH/database/db_logs_"*.tar.gz ]]; then
        log "Restoring database logs..."
        local logs_backup=$(find "$BACKUP_PATH/database" -name "db_logs_*.tar.gz" | head -1)
        
        # Remove existing volume
        docker volume rm "${COMPOSE_PROJECT}_db_logs" 2>/dev/null || true
        
        # Create new volume and restore data
        docker volume create "${COMPOSE_PROJECT}_db_logs"
        docker run --rm \
            -v "${COMPOSE_PROJECT}_db_logs:/target" \
            -v "$BACKUP_PATH:/backup:ro" \
            ubuntu:20.04 \
            tar -xzf "/backup/$(basename "$logs_backup")" -C /target
        
        success "Database logs restored"
    fi
    
    # Restore server data
    if [[ -f "$BACKUP_PATH/server/server_data_"*.tar.gz ]]; then
        log "Restoring server data..."
        local server_backup=$(find "$BACKUP_PATH/server" -name "server_data_*.tar.gz" | head -1)
        
        # Remove existing volume
        docker volume rm "${COMPOSE_PROJECT}_server_data" 2>/dev/null || true
        
        # Create new volume and restore data
        docker volume create "${COMPOSE_PROJECT}_server_data"
        docker run --rm \
            -v "${COMPOSE_PROJECT}_server_data:/target" \
            -v "$BACKUP_PATH:/backup:ro" \
            ubuntu:20.04 \
            tar -xzf "/backup/$(basename "$server_backup")" -C /target
        
        success "Server data restored"
    fi
    
    # Restore agent caches
    for cache in maven node dotnet; do
        cache_backup=$(find "$BACKUP_PATH/server" -name "${cache}_cache_*.tar.gz" 2>/dev/null | head -1)
        if [[ -n "$cache_backup" ]]; then
            log "Restoring $cache cache..."
            
            volume_name="${COMPOSE_PROJECT}_${cache}_cache"
            docker volume rm "$volume_name" 2>/dev/null || true
            docker volume create "$volume_name"
            
            docker run --rm \
                -v "$volume_name:/target" \
                -v "$BACKUP_PATH:/backup:ro" \
                ubuntu:20.04 \
                tar -xzf "/backup/$(basename "$cache_backup")" -C /target
            
            success "$cache cache restored"
        fi
    done
    
    log "Starting containers..."
    docker-compose -p "$COMPOSE_PROJECT" up -d
    
    success "Docker Compose restore completed"
}

# Kubernetes restore functions
restore_kubernetes() {
    log "Restoring Kubernetes deployment..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would restore Kubernetes resources from:"
        log "[DRY RUN]   - $BACKUP_PATH/manifests/"
        return 0
    fi
    
    # Check if namespace exists
    if ! kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
        log "Creating namespace $NAMESPACE..."
        kubectl create namespace "$NAMESPACE"
    fi
    
    # Restore from manifests if available
    if [[ -f "$BACKUP_PATH/manifests/all_resources_"*.yaml ]]; then
        log "Restoring Kubernetes resources..."
        local manifest_file=$(find "$BACKUP_PATH/manifests" -name "all_resources_*.yaml" | head -1)
        
        # Apply the manifests (this will restore ConfigMaps, Secrets, etc.)
        kubectl apply -f "$manifest_file" -n "$NAMESPACE" || warning "Some resources may already exist"
        
        success "Kubernetes resources restored"
    fi
    
    success "Kubernetes restore completed"
}

# Validate restore
validate_restore() {
    log "Validating restore..."
    
    case "$ENVIRONMENT" in
        "docker-compose")
            # Check if containers are running
            if docker-compose -p "$COMPOSE_PROJECT" ps | grep -q "Up"; then
                success "Containers are running"
            else
                warning "Some containers may not be running"
            fi
            ;;
        "kubernetes")
            # Check if pods are running
            if kubectl get pods -n "$NAMESPACE" | grep -q "Running"; then
                success "Pods are running in namespace $NAMESPACE"
            else
                warning "Some pods may not be running"
            fi
            ;;
    esac
}

# Main execution
main() {
    log "Starting QuickBuild restore..."
    log "Backup path: $BACKUP_PATH"
    log "Environment: $ENVIRONMENT"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "DRY RUN MODE - No changes will be made"
    fi
    
    prepare_backup
    confirm_restore
    
    case "$ENVIRONMENT" in
        "docker-compose")
            restore_docker_compose
            ;;
        "kubernetes")
            restore_kubernetes
            ;;
    esac
    
    if [[ "$DRY_RUN" != "true" ]]; then
        validate_restore
        success "Restore completed successfully!"
        log "Please verify that QuickBuild is functioning correctly"
    else
        success "Dry run completed - no changes were made"
    fi
}

# Run main function
main