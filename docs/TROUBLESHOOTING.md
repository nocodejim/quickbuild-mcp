# QuickBuild 14 Troubleshooting Guide

Comprehensive troubleshooting guide for common issues, solutions, and diagnostic procedures for the QuickBuild 14 containerization solution.

## Table of Contents

- [Quick Diagnostics](#quick-diagnostics)
- [Database Issues](#database-issues)
- [Server Issues](#server-issues)
- [Agent Issues](#agent-issues)
- [Network Issues](#network-issues)
- [Performance Issues](#performance-issues)
- [Storage Issues](#storage-issues)
- [Security Issues](#security-issues)
- [Deployment Issues](#deployment-issues)
- [Monitoring and Logging](#monitoring-and-logging)

## Quick Diagnostics

### First Steps for Any Issue

1. **Run Validation Script**
   ```bash
   ./scripts/validate-deployment.sh -e <environment>
   ```

2. **Check Component Health**
   ```bash
   ./scripts/health-check.sh all
   ```

3. **Monitor System Status**
   ```bash
   ./scripts/monitor.sh -e <environment> --once
   ```

4. **Check Logs**
   ```bash
   # Docker Compose
   docker-compose logs --tail=50

   # Kubernetes
   kubectl logs -l app.kubernetes.io/name=quickbuild -n quickbuild --tail=50
   ```

### Common Commands

| Environment | Check Status | View Logs | Restart Service |
|-------------|--------------|-----------|-----------------|
| Docker Compose | `docker-compose ps` | `docker-compose logs <service>` | `docker-compose restart <service>` |
| Kubernetes | `kubectl get pods -n quickbuild` | `kubectl logs <pod> -n quickbuild` | `kubectl rollout restart deployment/<name> -n quickbuild` |

## Database Issues

### Issue: Database Container Won't Start

**Symptoms:**
- Database container exits immediately
- Error: "EULA not accepted"
- Error: "Password validation failed"

**Solutions:**

1. **Check EULA Acceptance**
   ```bash
   # Verify ACCEPT_EULA is set to Y
   docker-compose config | grep ACCEPT_EULA
   ```

2. **Validate Password Complexity**
   ```bash
   # SA password must meet SQL Server requirements:
   # - At least 8 characters
   # - Contains uppercase, lowercase, number, and special character
   echo "YourPassword123!" | grep -E '^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$'
   ```

3. **Check Container Logs**
   ```bash
   docker-compose logs qb-database
   ```

4. **Verify Volume Permissions**
   ```bash
   # Check if volumes are accessible
   docker volume inspect quickbuild14_db_data
   ```

### Issue: Database Connection Refused

**Symptoms:**
- Server can't connect to database
- Error: "Connection refused" or "Host unreachable"

**Solutions:**

1. **Check Database Status**
   ```bash
   ./scripts/health-check.sh database
   ```

2. **Test Network Connectivity**
   ```bash
   # Docker Compose
   docker-compose exec qb-server nc -z qb-database 1433

   # Kubernetes
   kubectl exec -it <server-pod> -n quickbuild -- nc -z qb-database-service 1433
   ```

3. **Verify Database Initialization**
   ```bash
   # Check if database and user were created
   docker-compose exec qb-database /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P "$SA_PASSWORD" -Q "SELECT name FROM sys.databases WHERE name='quickbuild'"
   ```

4. **Check Service Discovery**
   ```bash
   # Docker Compose - verify network
   docker network ls | grep qb-net

   # Kubernetes - verify service
   kubectl get service qb-database-service -n quickbuild
   ```

### Issue: Database Performance Problems

**Symptoms:**
- Slow query responses
- High CPU usage on database container
- Connection timeouts

**Solutions:**

1. **Check Resource Usage**
   ```bash
   # Monitor database container resources
   docker stats qb-database
   ```

2. **Optimize Connection Pool**
   ```properties
   # In hibernate.properties.template
   hibernate.c3p0.max_size=30
   hibernate.c3p0.min_size=10
   hibernate.c3p0.timeout=600
   ```

3. **Increase Container Resources**
   ```yaml
   # In docker-compose.yml
   qb-database:
     deploy:
       resources:
         limits:
           memory: 8G
           cpus: '4'
   ```

## Server Issues

### Issue: QuickBuild Server Won't Start

**Symptoms:**
- Server container starts but web interface not accessible
- Error: "Port already in use"
- Error: "Database connection failed"

**Solutions:**

1. **Check Server Logs**
   ```bash
   docker-compose logs qb-server | tail -50
   ```

2. **Verify Database Connectivity**
   ```bash
   # Wait for database to be ready
   ./scripts/health-check.sh database
   ```

3. **Check Port Conflicts**
   ```bash
   # Verify port 8810 is not in use
   netstat -tulpn | grep 8810
   ```

4. **Validate Configuration**
   ```bash
   # Check environment variables
   docker-compose exec qb-server env | grep QB_
   ```

5. **Check Java Process**
   ```bash
   # Verify Java process is running
   docker-compose exec qb-server ps aux | grep java
   ```

### Issue: Web Interface Returns 500 Error

**Symptoms:**
- Server starts but returns HTTP 500 errors
- Database connection errors in logs
- Configuration errors

**Solutions:**

1. **Check Application Logs**
   ```bash
   # View QuickBuild application logs
   docker-compose exec qb-server tail -f /opt/quickbuild/data/logs/console.log
   ```

2. **Verify Database Schema**
   ```bash
   # Check if QuickBuild tables exist
   docker-compose exec qb-database /opt/mssql-tools/bin/sqlcmd -S localhost -U qb_user -P "$QB_DB_PASSWORD" -d quickbuild -Q "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES"
   ```

3. **Reset Configuration**
   ```bash
   # Regenerate configuration files
   docker-compose restart qb-server
   ```

### Issue: Server Memory Issues

**Symptoms:**
- OutOfMemoryError in logs
- Server becomes unresponsive
- High memory usage

**Solutions:**

1. **Increase JVM Memory**
   ```properties
   # In wrapper.conf.template
   wrapper.java.initmemory=2048
   wrapper.java.maxmemory=6144
   ```

2. **Optimize Garbage Collection**
   ```properties
   # Add GC options
   wrapper.java.additional.10=-XX:+UseG1GC
   wrapper.java.additional.11=-XX:MaxGCPauseMillis=200
   ```

3. **Monitor Memory Usage**
   ```bash
   # Check container memory usage
   docker stats qb-server
   ```

## Agent Issues

### Issue: Build Agents Not Connecting

**Symptoms:**
- No agents visible in QuickBuild web interface
- Agent containers running but not registered
- Connection timeout errors

**Solutions:**

1. **Check Agent Status**
   ```bash
   ./scripts/health-check.sh agent
   ```

2. **Verify Server Accessibility**
   ```bash
   # Test from agent container
   docker-compose exec qb-agent-maven curl -f http://qb-server:8810
   ```

3. **Check Agent Logs**
   ```bash
   docker-compose logs qb-agent-maven
   ```

4. **Verify Network Configuration**
   ```bash
   # Check if agents are on the same network
   docker network inspect quickbuild14_qb_net
   ```

5. **Check Agent Configuration**
   ```bash
   # Verify node.properties
   docker-compose exec qb-agent-maven cat /opt/qb-agent/conf/node.properties
   ```

### Issue: Agent Registration Fails

**Symptoms:**
- Agent starts but fails to register
- Authentication errors
- Server rejects agent connection

**Solutions:**

1. **Check Server URL Configuration**
   ```bash
   # Verify QB_SERVER_URL is correct
   docker-compose exec qb-agent-maven env | grep QB_SERVER_URL
   ```

2. **Test Server Connectivity**
   ```bash
   # Test REST API access
   docker-compose exec qb-agent-maven curl -f http://qb-server:8810/rest/version
   ```

3. **Check Agent Name Conflicts**
   ```bash
   # Ensure agent names are unique
   docker-compose exec qb-agent-maven cat /opt/qb-agent/conf/node.properties | grep name
   ```

### Issue: Build Failures on Agents

**Symptoms:**
- Builds fail with tool not found errors
- Permission denied errors
- Environment issues

**Solutions:**

1. **Verify Tool Installation**
   ```bash
   # Maven agent
   docker-compose exec qb-agent-maven mvn --version

   # Node.js agent
   docker-compose exec qb-agent-node node --version

   # .NET agent
   docker-compose exec qb-agent-dotnet dotnet --version
   ```

2. **Check File Permissions**
   ```bash
   # Verify agent user permissions
   docker-compose exec qb-agent-maven whoami
   docker-compose exec qb-agent-maven ls -la /opt/qb-agent
   ```

3. **Test Build Environment**
   ```bash
   # Test basic build commands
   docker-compose exec qb-agent-maven mvn help:system
   docker-compose exec qb-agent-node npm --version
   docker-compose exec qb-agent-dotnet dotnet --info
   ```

## Network Issues

### Issue: Service Discovery Problems

**Symptoms:**
- Services can't reach each other
- DNS resolution failures
- Connection timeouts between containers

**Solutions:**

1. **Check Network Configuration**
   ```bash
   # Docker Compose
   docker network ls | grep qb-net
   docker network inspect quickbuild14_qb_net

   # Kubernetes
   kubectl get services -n quickbuild
   ```

2. **Test DNS Resolution**
   ```bash
   # Docker Compose
   docker-compose exec qb-server nslookup qb-database

   # Kubernetes
   kubectl exec -it <pod> -n quickbuild -- nslookup qb-database-service
   ```

3. **Verify Service Endpoints**
   ```bash
   # Kubernetes
   kubectl get endpoints -n quickbuild
   ```

### Issue: Port Conflicts

**Symptoms:**
- "Port already in use" errors
- Services not accessible on expected ports
- Binding failures

**Solutions:**

1. **Check Port Usage**
   ```bash
   # Check what's using port 8810
   netstat -tulpn | grep 8810
   lsof -i :8810
   ```

2. **Change Port Configuration**
   ```bash
   # Update .env file
   QB_SERVER_PORT=8811
   ```

3. **Stop Conflicting Services**
   ```bash
   # Find and stop conflicting processes
   sudo kill $(lsof -t -i:8810)
   ```

## Performance Issues

### Issue: Slow Build Performance

**Symptoms:**
- Builds take longer than expected
- High resource usage during builds
- Agent timeouts

**Solutions:**

1. **Monitor Resource Usage**
   ```bash
   # Check system resources
   ./scripts/monitor.sh -e docker-compose --once
   ```

2. **Scale Build Agents**
   ```bash
   # Add more agents
   ./scripts/scale-agents.sh up 2
   ```

3. **Optimize Agent Resources**
   ```yaml
   # Increase agent memory
   qb-agent-maven:
     deploy:
       resources:
         limits:
           memory: 4G
           cpus: '2'
   ```

4. **Check Cache Usage**
   ```bash
   # Verify build caches are working
   docker volume ls | grep cache
   ```

### Issue: High Memory Usage

**Symptoms:**
- System becomes slow
- Out of memory errors
- Container restarts

**Solutions:**

1. **Identify Memory Usage**
   ```bash
   # Check container memory usage
   docker stats --no-stream
   ```

2. **Optimize JVM Settings**
   ```properties
   # Reduce initial memory allocation
   wrapper.java.initmemory=512
   wrapper.java.maxmemory=2048
   ```

3. **Implement Memory Limits**
   ```yaml
   # Set container memory limits
   deploy:
     resources:
       limits:
         memory: 2G
   ```

## Storage Issues

### Issue: Disk Space Problems

**Symptoms:**
- "No space left on device" errors
- Build artifacts not saved
- Database write failures

**Solutions:**

1. **Check Disk Usage**
   ```bash
   # Check overall disk usage
   df -h

   # Check Docker space usage
   docker system df
   ```

2. **Clean Up Docker Resources**
   ```bash
   # Remove unused containers, networks, images
   docker system prune -a

   # Remove unused volumes (CAUTION: This removes data)
   docker volume prune
   ```

3. **Configure Log Rotation**
   ```yaml
   # In docker-compose.yml
   logging:
     driver: "json-file"
     options:
       max-size: "10m"
       max-file: "3"
   ```

### Issue: Volume Mount Problems

**Symptoms:**
- Data not persisting between container restarts
- Permission denied errors
- Volume not found errors

**Solutions:**

1. **Check Volume Status**
   ```bash
   # Docker Compose
   docker volume ls | grep quickbuild
   docker volume inspect quickbuild14_server_data

   # Kubernetes
   kubectl get pvc -n quickbuild
   ```

2. **Verify Permissions**
   ```bash
   # Check volume permissions
   docker-compose exec qb-server ls -la /opt/quickbuild/data
   ```

3. **Recreate Volumes**
   ```bash
   # CAUTION: This will delete data
   docker-compose down -v
   docker-compose up -d
   ```

## Security Issues

### Issue: Authentication Problems

**Symptoms:**
- Can't log into QuickBuild web interface
- Database authentication failures
- Agent authentication issues

**Solutions:**

1. **Reset Admin Password**
   ```bash
   # Access QuickBuild container and reset password
   docker-compose exec qb-server /opt/quickbuild/bin/server.sh -reset-admin-password
   ```

2. **Check Database Credentials**
   ```bash
   # Test database connection
   docker-compose exec qb-database /opt/mssql-tools/bin/sqlcmd -S localhost -U qb_user -P "$QB_DB_PASSWORD" -Q "SELECT 1"
   ```

3. **Verify Secret Configuration**
   ```bash
   # Kubernetes - check secrets
   kubectl get secrets -n quickbuild
   kubectl describe secret quickbuild-database-secrets -n quickbuild
   ```

### Issue: TLS/SSL Problems

**Symptoms:**
- Certificate errors
- HTTPS not working
- SSL handshake failures

**Solutions:**

1. **Check Certificate Validity**
   ```bash
   # Verify certificate
   openssl x509 -in secrets/qb_server.crt -text -noout
   ```

2. **Test TLS Configuration**
   ```bash
   # Test HTTPS endpoint
   curl -k https://localhost:8810
   ```

3. **Regenerate Certificates**
   ```bash
   # Create new self-signed certificate
   openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
     -keyout secrets/qb_server.key \
     -out secrets/qb_server.crt
   ```

## Deployment Issues

### Issue: Docker Compose Deployment Fails

**Symptoms:**
- Services fail to start
- Image pull errors
- Configuration errors

**Solutions:**

1. **Check Docker Compose Version**
   ```bash
   docker-compose --version
   # Ensure version 2.0+
   ```

2. **Validate Compose File**
   ```bash
   docker-compose config
   ```

3. **Check Image Availability**
   ```bash
   # Build images locally if needed
   docker-compose build
   ```

4. **Review Environment Variables**
   ```bash
   # Check .env file
   cat .env | grep -v '^#'
   ```

### Issue: Kubernetes Deployment Fails

**Symptoms:**
- Pods stuck in Pending state
- ImagePullBackOff errors
- Resource constraints

**Solutions:**

1. **Check Pod Status**
   ```bash
   kubectl get pods -n quickbuild
   kubectl describe pod <pod-name> -n quickbuild
   ```

2. **Verify Resource Availability**
   ```bash
   kubectl top nodes
   kubectl describe nodes
   ```

3. **Check Storage Classes**
   ```bash
   kubectl get storageclass
   kubectl describe storageclass standard
   ```

4. **Review Events**
   ```bash
   kubectl get events -n quickbuild --sort-by='.lastTimestamp'
   ```

## Monitoring and Logging

### Centralized Logging

#### Docker Compose
```bash
# View all logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f qb-server

# View logs with timestamps
docker-compose logs -f -t
```

#### Kubernetes
```bash
# View all pod logs
kubectl logs -l app.kubernetes.io/name=quickbuild -n quickbuild

# View specific pod logs
kubectl logs <pod-name> -n quickbuild -f

# View previous container logs
kubectl logs <pod-name> -n quickbuild --previous
```

### Health Monitoring

#### Automated Health Checks
```bash
# Run comprehensive health check
./scripts/health-check.sh all -f json

# Monitor continuously
./scripts/monitor.sh -e <environment>

# Get Prometheus metrics
./scripts/health-check.sh all -f prometheus
```

#### Manual Health Verification
```bash
# Check service endpoints
curl -f http://localhost:8810/rest/version
curl -f http://localhost:8810/rest/system/health

# Verify database connectivity
nc -z localhost 1433

# Check agent connectivity
curl -f http://localhost:8810/rest/agents
```

### Performance Monitoring

#### Resource Usage
```bash
# Docker Compose
docker stats --no-stream

# Kubernetes
kubectl top pods -n quickbuild
kubectl top nodes
```

#### Application Metrics
```bash
# QuickBuild metrics
curl -s http://localhost:8810/rest/system/status | jq

# Build queue status
curl -s http://localhost:8810/rest/builds/queue | jq length
```

## Getting Additional Help

### Log Analysis
1. **Always check logs first** - they contain the most detailed error information
2. **Look for stack traces** - they show exactly where errors occur
3. **Check timestamps** - they help correlate events across services
4. **Search for ERROR and WARN messages** - they highlight problems

### Community Resources
- QuickBuild Documentation: https://wiki.pmease.com/display/QB14
- Docker Documentation: https://docs.docker.com/
- Kubernetes Documentation: https://kubernetes.io/docs/

### Escalation Path
1. Run all diagnostic scripts and collect output
2. Gather relevant logs from all affected services
3. Document exact steps to reproduce the issue
4. Include environment details (OS, Docker version, etc.)
5. Create detailed issue report with all collected information

This troubleshooting guide covers the most common issues encountered with QuickBuild 14 containerization. For issues not covered here, use the diagnostic tools provided and follow the systematic approach outlined above.