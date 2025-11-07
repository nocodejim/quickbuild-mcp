# QuickBuild 14 Agent Scaling Script (PowerShell)
# Provides easy scaling of build agents up or down
# Supports different agent types and scaling strategies

param(
    [Parameter(Position=0)]
    [string]$Command,
    
    [Parameter(Position=1)]
    [string]$Type,
    
    [Parameter(Position=2)]
    [int]$Count
)

# Configuration
$ComposeFiles = "-f docker-compose.yml -f docker-compose.scale.yml"
$ProjectName = $env:COMPOSE_PROJECT_NAME ?? "quickbuild14"

# Function to display usage
function Show-Usage {
    Write-Host "Usage: .\scale-agents.ps1 [COMMAND] [OPTIONS]"
    Write-Host ""
    Write-Host "Commands:"
    Write-Host "  scale <type> <count>    Scale specific agent type to count"
    Write-Host "  up <count>              Scale all agents up by count"
    Write-Host "  down <count>            Scale all agents down by count"
    Write-Host "  status                  Show current agent status"
    Write-Host "  auto                    Auto-scale based on load"
    Write-Host ""
    Write-Host "Agent Types:"
    Write-Host "  base                    Base agents"
    Write-Host "  maven                   Maven agents"
    Write-Host "  node                    Node.js agents"
    Write-Host "  dotnet                  .NET agents"
    Write-Host "  all                     All agent types"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  .\scale-agents.ps1 scale maven 3        Scale Maven agents to 3 replicas"
    Write-Host "  .\scale-agents.ps1 up 2                 Scale all agents up by 2"
    Write-Host "  .\scale-agents.ps1 down 1               Scale all agents down by 1"
    Write-Host "  .\scale-agents.ps1 status               Show current scaling status"
}

# Function to get current replica count
function Get-ReplicaCount {
    param([string]$AgentType)
    
    $Service = "qb-agent-$AgentType"
    try {
        $Output = docker-compose $ComposeFiles.Split(' ') ps $Service 2>$null
        if ($Output) {
            return ($Output | Where-Object { $_ -match $Service }).Count
        }
        return 0
    }
    catch {
        return 0
    }
}

# Function to scale specific agent type
function Scale-AgentType {
    param(
        [string]$AgentType,
        [int]$Count
    )
    
    if (-not $AgentType -or $Count -lt 0) {
        Write-Host "Error: Agent type and valid count are required" -ForegroundColor Red
        return $false
    }
    
    $Service = "qb-agent-$AgentType"
    $CurrentCount = Get-ReplicaCount $AgentType
    
    Write-Host "Scaling $AgentType agents from $CurrentCount to $Count..." -ForegroundColor Blue
    
    if ($Count -eq 0) {
        Write-Host "Warning: Scaling to 0 will stop all $AgentType agents" -ForegroundColor Yellow
        $Response = Read-Host "Continue? (y/N)"
        if ($Response -ne 'y' -and $Response -ne 'Y') {
            Write-Host "Cancelled"
            return $true
        }
    }
    
    try {
        $Args = $ComposeFiles.Split(' ') + @("up", "-d", "--scale", "$Service=$Count", $Service)
        docker-compose @Args
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Successfully scaled $AgentType agents to $Count" -ForegroundColor Green
            return $true
        }
        else {
            Write-Host "✗ Failed to scale $AgentType agents" -ForegroundColor Red
            return $false
        }
    }
    catch {
        Write-Host "✗ Error scaling $AgentType agents: $_" -ForegroundColor Red
        return $false
    }
}

# Function to scale all agents
function Scale-AllAgents {
    param(
        [string]$Operation,
        [int]$Count
    )
    
    if (-not $Operation -or $Count -lt 0) {
        Write-Host "Error: Operation and valid count are required" -ForegroundColor Red
        return $false
    }
    
    $AgentTypes = @("base", "maven", "node", "dotnet")
    $Success = $true
    
    foreach ($AgentType in $AgentTypes) {
        $CurrentCount = Get-ReplicaCount $AgentType
        $NewCount = 0
        
        switch ($Operation) {
            "up" { $NewCount = $CurrentCount + $Count }
            "down" { 
                $NewCount = $CurrentCount - $Count
                if ($NewCount -lt 0) { $NewCount = 0 }
            }
            default {
                Write-Host "Error: Invalid operation $Operation" -ForegroundColor Red
                return $false
            }
        }
        
        if (-not (Scale-AgentType $AgentType $NewCount)) {
            $Success = $false
        }
    }
    
    return $Success
}

# Function to show scaling status
function Show-Status {
    Write-Host "QuickBuild 14 Agent Scaling Status" -ForegroundColor Blue
    Write-Host "=================================="
    
    $AgentTypes = @("base", "maven", "node", "dotnet")
    $TotalAgents = 0
    
    foreach ($AgentType in $AgentTypes) {
        $Count = Get-ReplicaCount $AgentType
        $TotalAgents += $Count
        
        $Color = "Green"
        if ($Count -eq 0) { $Color = "Red" }
        elseif ($Count -eq 1) { $Color = "Yellow" }
        
        Write-Host ("{0,-10}: {1,2} replicas" -f $AgentType, $Count) -ForegroundColor $Color
    }
    
    Write-Host "=================================="
    Write-Host ("Total:     {0,2} agents" -f $TotalAgents) -ForegroundColor Blue
    Write-Host ""
    
    # Show resource usage if available
    try {
        $Services = docker-compose $ComposeFiles.Split(' ') ps -q 2>$null
        if ($Services) {
            Write-Host "Resource Usage:"
            docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" $Services 2>$null | Where-Object { $_ -match "qb-agent" }
        }
    }
    catch {
        # Ignore errors for resource usage display
    }
}

# Function for auto-scaling based on load
function Start-AutoScale {
    Write-Host "Auto-scaling agents based on load..." -ForegroundColor Blue
    
    # Basic implementation - in production, integrate with QuickBuild's API
    try {
        $QueueLength = 0
        try {
            $Response = Invoke-RestMethod -Uri "http://localhost:8810/rest/builds/queue" -TimeoutSec 5
            $QueueLength = $Response.Count ?? 0
        }
        catch {
            $QueueLength = 0
        }
        
        $TotalAgents = 0
        $AgentTypes = @("base", "maven", "node", "dotnet")
        foreach ($AgentType in $AgentTypes) {
            $TotalAgents += Get-ReplicaCount $AgentType
        }
        
        Write-Host "Build queue length: $QueueLength"
        Write-Host "Current agents: $TotalAgents"
        
        if ($QueueLength -gt ($TotalAgents * 2)) {
            Write-Host "High load detected, scaling up..." -ForegroundColor Yellow
            Scale-AllAgents "up" 1
        }
        elseif ($QueueLength -eq 0 -and $TotalAgents -gt 4) {
            Write-Host "Low load detected, scaling down..." -ForegroundColor Yellow
            Scale-AllAgents "down" 1
        }
        else {
            Write-Host "Load is balanced, no scaling needed" -ForegroundColor Green
        }
    }
    catch {
        Write-Host "Error during auto-scaling: $_" -ForegroundColor Red
    }
}

# Main script logic
switch ($Command) {
    "scale" {
        if ($Type -eq "all") {
            Scale-AllAgents "set" $Count
        }
        else {
            Scale-AgentType $Type $Count
        }
    }
    "up" {
        Scale-AllAgents "up" $Type
    }
    "down" {
        Scale-AllAgents "down" $Type
    }
    "status" {
        Show-Status
    }
    "auto" {
        Start-AutoScale
    }
    { $_ -in @("help", "-h", "--help", "") } {
        Show-Usage
    }
    default {
        Write-Host "Error: Unknown command '$Command'" -ForegroundColor Red
        Write-Host ""
        Show-Usage
        exit 1
    }
}