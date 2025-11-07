# QuickBuild 14 Backup Script (PowerShell)
# Comprehensive backup solution for Docker Compose and Kubernetes deployments
# Windows-compatible version of backup.sh

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("docker-compose", "kubernetes")]
    [string]$Environment,
    
    [string]$BackupDir = ".\backups",
    [string]$Namespace = "quickbuild",
    [string]$Project = $env:COMPOSE_PROJECT_NAME ?? "quickbuild14",
    [switch]$Compress,
    [switch]$Validate,
    [switch]$Help
)

# Configuration
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupName = "quickbuild_backup_$Timestamp"

# Functions
function Write-Log {
    param([string]$Message)
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message" -ForegroundColor Blue
}

function Write-Error-Log {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Write-Warning-Log {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Show-Usage {
    Write-Host "Usage: .\backup.ps1 -Environment <docker-compose|kubernetes> [OPTIONS]"
    Write-Host ""
    Write-Host "Parameters:"
    Write-Host "  -Environment ENV     Deployment environment (docker-compose|kubernetes)"
    Write-Host "  -BackupDir DIR       Backup directory (default: .\backups)"
    Write-Host "  -Namespace NS        Kubernetes namespace (default: quickbuild)"
    Write-Host "  -Project NAME        Docker Compose project name"
    Write-Host "  -Compress           Compress backup files"
    Write-Host "  -Validate           Validate backup after creation"
    Write-Host "  -Help               Show this help message"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  .\backup.ps1 -Environment docker-compose -Compress -Validate"
    Write-Host "  .\backup.ps1 -Environment kubernetes -Namespace quickbuild -BackupDir C:\backup\qb"
}

if ($Help) {
    Show-Usage
    exit 0
}

# Create backup directory
$BackupPath = Join-Path $BackupDir $BackupName
New-Item -ItemType Directory -Path $BackupPath -Force | Out-Null

Write-Log "Starting QuickBuild backup..."
Write-Log "Environment: $Environment"
Write-Log "Backup directory: $BackupPath"

# Docker Compose backup functions
function Backup-DockerCompose {
    Write-Log "Backing up Docker Compose deployment..."
    
    # Check if containers are running
    $containers = docker-compose -p $Project ps
    if (-not ($containers -match "Up")) {
        Write-Warning-Log "No running containers found for project $Project"
    }
    
    # Create backup structure
    New-Item -ItemType Directory -Path "$BackupPath\database" -Force | Out-Null
    New-Item -ItemType Directory -Path "$BackupPath\server" -Force | Out-Null
    New-Item -ItemType Directory -Path "$BackupPath\metadata" -Force | Out-Null
    
    # Backup database data
    Write-Log "Backing up database data..."
    $dbDataVolume = "${Project}_db_data"
    if (docker volume ls | Select-String $dbDataVolume) {
        docker run --rm `
            -v "${dbDataVolume}:/source:ro" `
            -v "${BackupPath}:/backup" `
            ubuntu:20.04 `
            tar czf "/backup/database/db_data_${Timestamp}.tar.gz" -C /source .
        Write-Success "Database data backup completed"
    } else {
        Write-Warning-Log "Database data volume not found"
    }
    
    # Backup database logs
    Write-Log "Backing up database logs..."
    $dbLogsVolume = "${Project}_db_logs"
    if (docker volume ls | Select-String $dbLogsVolume) {
        docker run --rm `
            -v "${dbLogsVolume}:/source:ro" `
            -v "${BackupPath}:/backup" `
            ubuntu:20.04 `
            tar czf "/backup/database/db_logs_${Timestamp}.tar.gz" -C /source .
        Write-Success "Database logs backup completed"
    }
    
    # Backup server data
    Write-Log "Backing up server data..."
    $serverDataVolume = "${Project}_server_data"
    if (docker volume ls | Select-String $serverDataVolume) {
        docker run --rm `
            -v "${serverDataVolume}:/source:ro" `
            -v "${BackupPath}:/backup" `
            ubuntu:20.04 `
            tar czf "/backup/server/server_data_${Timestamp}.tar.gz" -C /source .
        Write-Success "Server data backup completed"
    } else {
        Write-Warning-Log "Server data volume not found"
    }
    
    # Backup agent caches
    Write-Log "Backing up agent caches..."
    $caches = @("maven", "node", "dotnet")
    foreach ($cache in $caches) {
        $volumeName = "${Project}_${cache}_cache"
        if (docker volume ls | Select-String $volumeName) {
            docker run --rm `
                -v "${volumeName}:/source:ro" `
                -v "${BackupPath}:/backup" `
                ubuntu:20.04 `
                tar czf "/backup/server/${cache}_cache_${Timestamp}.tar.gz" -C /source .
            Write-Success "$cache cache backup completed"
        }
    }
}

# Kubernetes backup functions
function Backup-Kubernetes {
    Write-Log "Backing up Kubernetes deployment..."
    
    # Check if namespace exists
    try {
        kubectl get namespace $Namespace | Out-Null
    } catch {
        Write-Error-Log "Namespace $Namespace not found"
        exit 1
    }
    
    # Create backup structure
    New-Item -ItemType Directory -Path "$BackupPath\database" -Force | Out-Null
    New-Item -ItemType Directory -Path "$BackupPath\server" -Force | Out-Null
    New-Item -ItemType Directory -Path "$BackupPath\manifests" -Force | Out-Null
    New-Item -ItemType Directory -Path "$BackupPath\metadata" -Force | Out-Null
    
    # Backup Kubernetes manifests
    Write-Log "Backing up Kubernetes manifests..."
    kubectl get all,pvc,configmap,secret -n $Namespace -o yaml > "$BackupPath\manifests\all_resources_${Timestamp}.yaml"
    
    Write-Success "Kubernetes manifests backup completed"
}

# Backup metadata
function Backup-Metadata {
    Write-Log "Creating backup metadata..."
    
    $metadata = @{
        backup_timestamp = $Timestamp
        backup_date = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssK")
        environment = $Environment
        namespace = $Namespace
        compose_project = $Project
        backup_version = "1.0"
        quickbuild_version = "14.0"
        backup_type = "full"
        compressed = $Compress.IsPresent
        validated = $Validate.IsPresent
    }
    
    $metadata | ConvertTo-Json | Out-File "$BackupPath\metadata\backup_info.json" -Encoding UTF8
    
    # Create backup manifest
    Get-ChildItem -Path $BackupPath -Recurse -File | 
        Select-Object FullName, Length, LastWriteTime | 
        ConvertTo-Json | Out-File "$BackupPath\metadata\file_manifest.json" -Encoding UTF8
    
    Write-Success "Backup metadata created"
}

# Validate backup
function Test-Backup {
    if ($Validate) {
        Write-Log "Validating backup..."
        
        $validationFailed = $false
        
        if ($Environment -eq "docker-compose") {
            $backupFiles = Get-ChildItem "$BackupPath\database\*.tar.gz", "$BackupPath\server\*.tar.gz" -ErrorAction SilentlyContinue
            
            foreach ($file in $backupFiles) {
                try {
                    # Basic file validation (check if file exists and has content)
                    if ($file.Length -gt 0) {
                        Write-Success "Validated: $($file.Name)"
                    } else {
                        Write-Error-Log "Validation failed: $($file.Name) is empty"
                        $validationFailed = $true
                    }
                } catch {
                    Write-Error-Log "Validation failed: $($file.Name)"
                    $validationFailed = $true
                }
            }
        }
        
        if ($validationFailed) {
            Write-Error-Log "Backup validation failed"
            exit 1
        } else {
            Write-Success "Backup validation completed successfully"
        }
    }
}

# Compress backup
function Compress-Backup {
    if ($Compress) {
        Write-Log "Compressing backup..."
        
        $compressedPath = "$BackupDir\${BackupName}.zip"
        Compress-Archive -Path $BackupPath -DestinationPath $compressedPath -Force
        Remove-Item -Path $BackupPath -Recurse -Force
        
        Write-Success "Backup compressed: ${BackupName}.zip"
        return $compressedPath
    }
    return $BackupPath
}

# Main execution
try {
    switch ($Environment) {
        "docker-compose" { Backup-DockerCompose }
        "kubernetes" { Backup-Kubernetes }
    }
    
    Backup-Metadata
    Test-Backup
    $finalPath = Compress-Backup
    
    Write-Success "Backup completed successfully!"
    Write-Success "Backup location: $finalPath"
    
    # Display backup size
    if (Test-Path $finalPath) {
        $size = (Get-Item $finalPath).Length
        $sizeFormatted = if ($size -gt 1GB) { "{0:N2} GB" -f ($size / 1GB) } 
                        elseif ($size -gt 1MB) { "{0:N2} MB" -f ($size / 1MB) }
                        else { "{0:N2} KB" -f ($size / 1KB) }
        Write-Log "Backup size: $sizeFormatted"
    }
} catch {
    Write-Error-Log "Backup failed: $($_.Exception.Message)"
    exit 1
}