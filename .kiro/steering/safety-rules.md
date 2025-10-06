---
inclusion: always
---

# CRITICAL SAFETY RULES - ALWAYS FOLLOW

## NEVER Execute Destructive Commands

**ABSOLUTELY FORBIDDEN - Never suggest or execute:**

### Docker System-Wide Destructive Commands
- `docker system prune -f` (removes ALL unused Docker resources)
- `docker system prune -a -f` (removes ALL Docker resources)
- `docker volume prune -f` (removes ALL unused volumes)
- `docker image prune -a -f` (removes ALL unused images)
- `docker container prune -f` (removes ALL stopped containers)
- `docker network prune -f` (removes ALL unused networks)

### Filesystem Destructive Commands
- `rm -rf /` or any variant
- `rm -rf ~` or any variant
- `rm -rf *` in system directories
- `chmod -R 777 /` or similar
- `chown -R` on system directories
- Any command that modifies system files or directories

### Process/Service Destructive Commands
- `killall -9` (kills all processes by name)
- `pkill -f` without specific targeting
- `systemctl stop` on critical services
- `service stop` on critical services

## SAFE ALTERNATIVES - Always Use Targeted Commands

### Docker - Target Specific Resources
```bash
# GOOD: Target specific containers
docker stop container-name
docker rm container-name

# GOOD: Target specific images
docker rmi specific-image:tag

# GOOD: Target specific volumes
docker volume rm specific-volume-name

# GOOD: Target specific networks
docker network rm specific-network-name
```

### File Operations - Be Specific
```bash
# GOOD: Target specific files/directories
rm -f specific-file.txt
rm -rf ./project-directory

# GOOD: Use relative paths in project context
rm -rf ./build/
rm -rf ./node_modules/
```

## VERIFICATION REQUIREMENTS

Before suggesting ANY command that could affect the system:

1. **Ask yourself**: "Could this affect anything outside the current project?"
2. **If yes**: Find a more targeted alternative
3. **If unsure**: Ask the user for confirmation and explain the risks
4. **Always**: Prefer specific resource names over wildcards

## PROJECT-SAFE PATTERNS

### Docker Cleanup (Project-Specific)
```bash
# Target only project containers
docker-compose down -v
docker rm $(docker ps -aq --filter "name=project-prefix")

# Target only project images
docker rmi $(docker images -q --filter "reference=project-name/*")
```

### File Cleanup (Project-Specific)
```bash
# Only in project directory
rm -rf ./build/
rm -rf ./dist/
rm -rf ./node_modules/

# Never use absolute paths for cleanup
```

## EMERGENCY PROTOCOLS

If a destructive command is accidentally suggested:
1. **Immediately warn the user**
2. **Provide safe alternatives**
3. **Explain the potential damage**
4. **Update this document if needed**

## REMEMBER

**The user's system and other projects are sacred. Never risk damaging them for convenience.**