#!/bin/bash
# QuickBuild 14 Agent Scaling Script
# Provides easy scaling of build agents up or down
# Supports different agent types and scaling strategies

set -e

# Configuration
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.scale.yml"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-quickbuild14}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to display usage
usage() {
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  scale <type> <count>    Scale specific agent type to count"
    echo "  up <count>              Scale all agents up by count"
    echo "  down <count>            Scale all agents down by count"
    echo "  status                  Show current agent status"
    echo "  auto                    Auto-scale based on load"
    echo ""
    echo "Agent Types:"
    echo "  base                    Base agents"
    echo "  maven                   Maven agents"
    echo "  node                    Node.js agents"
    echo "  dotnet                  .NET agents"
    echo "  all                     All agent types"
    echo ""
    echo "Examples:"
    echo "  $0 scale maven 3        Scale Maven agents to 3 replicas"
    echo "  $0 up 2                 Scale all agents up by 2"
    echo "  $0 down 1               Scale all agents down by 1"
    echo "  $0 status               Show current scaling status"
    echo ""
}

# Function to get current replica count
get_replica_count() {
    local service="qb-agent-$1"
    docker-compose $COMPOSE_FILES ps --services | grep -q "$service" || return 0
    docker-compose $COMPOSE_FILES ps "$service" 2>/dev/null | grep -c "$service" || echo "0"
}

# Function to scale specific agent type
scale_agent_type() {
    local agent_type="$1"
    local count="$2"
    
    if [ -z "$agent_type" ] || [ -z "$count" ]; then
        echo -e "${RED}Error: Agent type and count are required${NC}"
        return 1
    fi
    
    if ! [[ "$count" =~ ^[0-9]+$ ]]; then
        echo -e "${RED}Error: Count must be a positive integer${NC}"
        return 1
    fi
    
    local service="qb-agent-$agent_type"
    local current_count=$(get_replica_count "$agent_type")
    
    echo -e "${BLUE}Scaling $agent_type agents from $current_count to $count...${NC}"
    
    if [ "$count" -eq 0 ]; then
        echo -e "${YELLOW}Warning: Scaling to 0 will stop all $agent_type agents${NC}"
        read -p "Continue? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Cancelled"
            return 0
        fi
    fi
    
    docker-compose $COMPOSE_FILES up -d --scale "$service=$count" "$service"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Successfully scaled $agent_type agents to $count${NC}"
    else
        echo -e "${RED}✗ Failed to scale $agent_type agents${NC}"
        return 1
    fi
}

# Function to scale all agents
scale_all_agents() {
    local operation="$1"
    local count="$2"
    
    if [ -z "$operation" ] || [ -z "$count" ]; then
        echo -e "${RED}Error: Operation and count are required${NC}"
        return 1
    fi
    
    local agent_types=("base" "maven" "node" "dotnet")
    
    for agent_type in "${agent_types[@]}"; do
        local current_count=$(get_replica_count "$agent_type")
        local new_count
        
        if [ "$operation" = "up" ]; then
            new_count=$((current_count + count))
        elif [ "$operation" = "down" ]; then
            new_count=$((current_count - count))
            if [ $new_count -lt 0 ]; then
                new_count=0
            fi
        else
            echo -e "${RED}Error: Invalid operation $operation${NC}"
            return 1
        fi
        
        scale_agent_type "$agent_type" "$new_count"
    done
}

# Function to show scaling status
show_status() {
    echo -e "${BLUE}QuickBuild 14 Agent Scaling Status${NC}"
    echo "=================================="
    
    local agent_types=("base" "maven" "node" "dotnet")
    local total_agents=0
    
    for agent_type in "${agent_types[@]}"; do
        local count=$(get_replica_count "$agent_type")
        total_agents=$((total_agents + count))
        
        local status_color="$GREEN"
        if [ "$count" -eq 0 ]; then
            status_color="$RED"
        elif [ "$count" -eq 1 ]; then
            status_color="$YELLOW"
        fi
        
        printf "%-10s: ${status_color}%2d${NC} replicas\n" "$agent_type" "$count"
    done
    
    echo "=================================="
    printf "Total:     ${BLUE}%2d${NC} agents\n" "$total_agents"
    echo ""
    
    # Show resource usage if available
    if command -v docker > /dev/null 2>&1; then
        echo "Resource Usage:"
        docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" \
            $(docker-compose $COMPOSE_FILES ps -q) 2>/dev/null | grep qb-agent || true
    fi
}

# Function for auto-scaling based on load
auto_scale() {
    echo -e "${BLUE}Auto-scaling agents based on load...${NC}"
    
    # This is a basic implementation - in production, you'd integrate with
    # QuickBuild's API to get actual build queue metrics
    
    local queue_length=$(curl -s "http://localhost:8810/rest/builds/queue" 2>/dev/null | jq length 2>/dev/null || echo "0")
    local total_agents=$(docker-compose $COMPOSE_FILES ps -q | grep qb-agent | wc -l)
    
    echo "Build queue length: $queue_length"
    echo "Current agents: $total_agents"
    
    if [ "$queue_length" -gt $((total_agents * 2)) ]; then
        echo -e "${YELLOW}High load detected, scaling up...${NC}"
        scale_all_agents "up" 1
    elif [ "$queue_length" -eq 0 ] && [ "$total_agents" -gt 4 ]; then
        echo -e "${YELLOW}Low load detected, scaling down...${NC}"
        scale_all_agents "down" 1
    else
        echo -e "${GREEN}Load is balanced, no scaling needed${NC}"
    fi
}

# Main script logic
case "$1" in
    "scale")
        if [ "$2" = "all" ]; then
            scale_all_agents "set" "$3"
        else
            scale_agent_type "$2" "$3"
        fi
        ;;
    "up")
        scale_all_agents "up" "$2"
        ;;
    "down")
        scale_all_agents "down" "$2"
        ;;
    "status")
        show_status
        ;;
    "auto")
        auto_scale
        ;;
    "help"|"-h"|"--help")
        usage
        ;;
    *)
        echo -e "${RED}Error: Unknown command '$1'${NC}"
        echo ""
        usage
        exit 1
        ;;
esac