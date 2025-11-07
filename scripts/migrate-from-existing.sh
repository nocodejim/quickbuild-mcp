#!/bin/bash
# QuickBuild 14 Migration Script
# Migrates data from existing QuickBuild installation to containerized deployment
# Supports migration of configuration, build history, and user data

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

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
    echo "  -s, --source-path PATH   Path to existing QuickBuild installation"
    echo "  -d, --database-backup    Path to existing database backup file"
    echo "  -e, --environment ENV    Target environment (docker-compose|kubernetes)"
    echo "  -n, --namespace NS       Kubernetes namespace (default: quickbuild)"
    echo "  -p, --project NAME       Docker Compose project name"
    echo "  --dry-run               Show what would be migrated without doing it"
    echo "  -h, --help              Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 -s /opt/quickbuild -d /backup/qb_database.bak -e docker-compose"
    echo "  $0 -s C:\\QuickBuild -d database_backup.sql -e kubernetes"
    echo "  $0 -s /home/qb/quickbuild --dry-run"
    echo ""
}

# Parse command line arguments
SOURCE_PATH=""
DATABASE_BACKUP=""
ENVIRONMENT=""
NAMESPACE="quickbuild"
COMPOSE_PROJECT="${COMPOSE_PROJECT_NAME:-quickbuild14}"
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -s|--source-path)
            SOURCE_PATH="$2"
            shift 2
            ;;
        -d|--database-backup)
            DATABASE_BACKUP="$2"
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
if [[ -z "$SOURCE_PATH" ]]; then
    error "Source QuickBuild path must be specified (-s /path/to/quickbuild)"
    usage
    exit 1
fi

if [[ ! -d "$SOURCE_PATH" ]]; then
    error "Source path does not exist or is not a directory: $SOURCE_PATH"
    exit 1
fi

# Detect QuickBuild installation
detect_quickbuild_installation() {
    log "Detecting QuickBuild installation at: $SOURCE_PATH"
    
    # Check for QuickBuild server files
    if [[ ! -f "$SOURCE_PATH/bin/server.sh" && ! -f "$SOURCE_PATH/bin/server.bat" ]]; then
        error "QuickBuild server installation not found in $SOURCE_PATH"
        error "Expected to find bin/server.sh or bin/server.bat"
        exit 1
    fi
    
    # Detect version
    local version_file=""
    if [[ -f "$SOURCE_PATH/version.txt" ]]; then
        version_file="$SOURCE_PATH/version.txt"
    elif [[ -f "$SOURCE_PATH/VERSION" ]]; then
        version_file="$SOURCE_PATH/VERSION"
    fi
    
    if [[ -n "$version_file" ]]; then
        local version=$(cat "$version_file" | head -1)
        log "Detected QuickBuild version: $version"
        
        # Check if version is compatible
        if [[ ! "$version" =~ ^14\. ]]; then
            warning "Source version ($version) may not be fully compatible with QuickBuild 14 containers"
            warning "Migration may require manual adjustments"
        fi
    else
        warning "Could not detect QuickBuild version"
    fi
    
    success "QuickBuild installation detected"
}

# Analyze existing configuration
analyze_configuration() {
    log "Analyzing existing configuration..."
    
    local config_files=()
    
    # Check for configuration files
    if [[ -f "$SOURCE_PATH/conf/hibernate.properties" ]]; then
        config_files+=("hibernate.properties")
        log "Found database configuration: hibernate.properties"
        
        # Analyze database type
        local db_driver=$(grep "hibernate.connection.driver_class" "$SOURCE_PATH/conf/hibernate.properties" 2>/dev/null || echo "")
        if [[ "$db_driver" == *"sqlserver"* ]]; then
            success "Database type: Microsoft SQL Server (compatible)"
        elif [[ "$db_driver" == *"postgresql"* ]]; then
            warning "Database type: PostgreSQL (requires conversion to SQL Server)"
        elif [[ "$db_driver" == *"mysql"* ]]; then
            warning "Database type: MySQL (requires conversion to SQL Server)"
        else
            warning "Database type: Unknown or embedded (may require manual configuration)"
        fi
    fi
    
    if [[ -f "$SOURCE_PATH/conf/wrapper.conf" ]]; then
        config_files+=("wrapper.conf")
        log "Found Java wrapper configuration: wrapper.conf"
    fi
    
    # Check for data directories
    local data_dirs=()
    if [[ -d "$SOURCE_PATH/logs" ]]; then
        data_dirs+=("logs")
        local log_size=$(du -sh "$SOURCE_PATH/logs" 2>/dev/null | cut -f1 || echo "unknown")
        log "Found logs directory (size: $log_size)"
    fi
    
    if [[ -d "$SOURCE_PATH/artifacts" ]]; then
        data_dirs+=("artifacts")
        local artifacts_size=$(du -sh "$SOURCE_PATH/artifacts" 2>/dev/null | cut -f1 || echo "unknown")
        log "Found artifacts directory (size: $artifacts_size)"
    fi
    
    if [[ -d "$SOURCE_PATH/repository" ]]; then
        data_dirs+=("repository")
        local repo_size=$(du -sh "$SOURCE_PATH/repository" 2>/dev/null | cut -f1 || echo "unknown")
        log "Found repository directory (size: $repo_size)"
    fi
    
    # Estimate total migration size
    local total_size=$(du -sh "$SOURCE_PATH" 2>/dev/null | cut -f1 || echo "unknown")
    log "Total installation size: $total_size"
    
    if [[ ${#config_files[@]} -eq 0 ]]; then
        warning "No configuration files found - this may not be a complete QuickBuild installation"
    fi
    
    if [[ ${#data_dirs[@]} -eq 0 ]]; then
        warning "No data directories found - this may be a fresh installation"
    fi
}

# Create migration plan
create_migration_plan() {
    log "Creating migration plan..."
    
    local migration_dir="$PROJECT_ROOT/migration_$(date +%Y%m%d_%H%M%S)"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would create migration directory: $migration_dir"
    else
        mkdir -p "$migration_dir"/{config,data,database}
        log "Created migration directory: $migration_dir"
    fi
    
    # Plan configuration migration
    log "Planning configuration migration..."
    if [[ -f "$SOURCE_PATH/conf/hibernate.properties" ]]; then
        if [[ "$DRY_RUN" == "true" ]]; then
            log "[DRY RUN] Would copy hibernate.properties for analysis"
        else
            cp "$SOURCE_PATH/conf/hibernate.properties" "$migration_dir/config/"
            log "Copied hibernate.properties for analysis"
        fi
    fi
    
    if [[ -f "$SOURCE_PATH/conf/wrapper.conf" ]]; then
        if [[ "$DRY_RUN" == "true" ]]; then
            log "[DRY RUN] Would copy wrapper.conf for analysis"
        else
            cp "$SOURCE_PATH/conf/wrapper.conf" "$migration_dir/config/"
            log "Copied wrapper.conf for analysis"
        fi
    fi
    
    # Plan data migration
    log "Planning data migration..."
    for dir in logs artifacts repository; do
        if [[ -d "$SOURCE_PATH/$dir" ]]; then
            if [[ "$DRY_RUN" == "true" ]]; then
                log "[DRY RUN] Would migrate $dir directory"
            else
                log "Copying $dir directory..."
                cp -r "$SOURCE_PATH/$dir" "$migration_dir/data/"
                success "$dir directory copied"
            fi
        fi
    done
    
    # Create migration instructions
    if [[ "$DRY_RUN" != "true" ]]; then
        cat > "$migration_dir/MIGRATION_INSTRUCTIONS.md" << 'EOF'
# QuickBuild Migration Instructions

This directory contains the migrated data from your existing QuickBuild installation.

## Migration Steps

### 1. Database Migration
If you have a database backup:
1. Restore the database backup to the new SQL Server container
2. Update connection settings in the containerized deployment

### 2. Configuration Migration
1. Review the copied configuration files in config/
2. Update the containerized deployment's environment variables accordingly
3. Pay special attention to database connection settings

### 3. Data Migration
1. The data/ directory contains your existing logs, artifacts, and repository
2. Copy this data to the appropriate volumes in your containerized deployment
3. Ensure proper file permissions after copying

### 4. Validation
1. Start the containerized QuickBuild deployment
2. Verify that all configurations are working
3. Test build functionality with existing projects
4. Validate that all historical data is accessible

## Important Notes
- Always backup your existing installation before migration
- Test the migration in a development environment first
- Some manual configuration adjustments may be required
- Database schema updates may be needed for version compatibility
EOF
        
        success "Migration instructions created: $migration_dir/MIGRATION_INSTRUCTIONS.md"
    fi
    
    if [[ "$DRY_RUN" != "true" ]]; then
        success "Migration preparation completed: $migration_dir"
        log "Next steps:"
        log "1. Review the migration directory contents"
        log "2. Follow the instructions in MIGRATION_INSTRUCTIONS.md"
        log "3. Deploy the containerized QuickBuild solution"
        log "4. Import the migrated data and configuration"
    fi
}

# Database migration helper
migrate_database() {
    if [[ -n "$DATABASE_BACKUP" ]]; then
        log "Processing database backup: $DATABASE_BACKUP"
        
        if [[ ! -f "$DATABASE_BACKUP" ]]; then
            error "Database backup file not found: $DATABASE_BACKUP"
            return 1
        fi
        
        local backup_size=$(du -sh "$DATABASE_BACKUP" | cut -f1)
        log "Database backup size: $backup_size"
        
        # Detect backup format
        local backup_format="unknown"
        case "${DATABASE_BACKUP,,}" in
            *.bak)
                backup_format="SQL Server BAK"
                ;;
            *.sql)
                backup_format="SQL Script"
                ;;
            *.dump)
                backup_format="PostgreSQL Dump"
                ;;
            *)
                warning "Unknown backup format, manual processing may be required"
                ;;
        esac
        
        log "Detected backup format: $backup_format"
        
        if [[ "$DRY_RUN" != "true" ]]; then
            # Copy database backup to migration directory
            cp "$DATABASE_BACKUP" "$migration_dir/database/"
            success "Database backup copied to migration directory"
            
            # Create database migration instructions
            cat >> "$migration_dir/MIGRATION_INSTRUCTIONS.md" << EOF

## Database Migration Details

### Backup Information
- Original file: $DATABASE_BACKUP
- Format: $backup_format
- Size: $backup_size

### Restoration Steps
1. Ensure the SQL Server container is running
2. Copy the backup file into the container
3. Restore using appropriate SQL Server commands
4. Update connection settings in QuickBuild configuration

EOF
        fi
    else
        warning "No database backup specified - you'll need to migrate database data separately"
    fi
}

# Main execution
main() {
    log "Starting QuickBuild migration analysis..."
    log "Source path: $SOURCE_PATH"
    
    if [[ -n "$DATABASE_BACKUP" ]]; then
        log "Database backup: $DATABASE_BACKUP"
    fi
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "DRY RUN MODE - No files will be copied"
    fi
    
    detect_quickbuild_installation
    analyze_configuration
    migrate_database
    create_migration_plan
    
    if [[ "$DRY_RUN" == "true" ]]; then
        success "Migration analysis completed (dry run)"
        log "Run without --dry-run to perform the actual migration preparation"
    else
        success "Migration preparation completed!"
        log "Review the migration directory and follow the instructions to complete the migration"
    fi
}

# Run main function
main