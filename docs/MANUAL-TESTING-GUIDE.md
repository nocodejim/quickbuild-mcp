# QuickBuild 14 Containerization - Manual Testing Guide

## Overview
This guide provides step-by-step instructions for manually testing and troubleshooting the QuickBuild 14 containerized deployment.

## Prerequisites
- Docker and Docker Compose installed
- QuickBuild 14.0.32 installation files in `environment/quickbuild-14.0.32/`
- At least 8GB RAM and 4 CPU cores recommended
- Windows/Linux/macOS with Docker Desktop

## Quick Start Testing

### 1. Database-Only Testing
Test the database container independently:

```bash
# Build and start only the database
docker-compose build qb-database
docker-compose up -d qb-database

# Check database logs
docker-compose logs -f qb-database

# Test database connectivity
docker exec -it qb-database /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P "TestPassword123!" -Q "SELECT @@VERSION"
```

### 2. Server-Only Testing (with external DB)
If database issues persist, test with external SQL Server:

```bash
# Use external SQL Server (modify .env file)
QB_DB_HOST=your-sql-server-host
QB_DB_PASSWORD=your-password

# Build and start server only
docker-compose build qb-server
docker-compose up qb-server
```

### 3. Full Stack Testing
```bash
# Build all containers
docker-compose build

# Start with verbose logging
docker-compose up --verbose

# Check all container status
docker-compose ps
docker-compose logs
```

## Troubleshooting Common Issues

### Database Initialization Hanging

**Problem**: Database container hangs during SQL Server startup

**Solutions**:
1. **Increase memory allocation**:
   ```bash
   # In docker-compose.yml, increase memory limits
   deploy:
     resources:
       limits:
         memory: 6G
   ```

2. **Use simpler database approach**:
   ```bash
   # Replace custom database with standard SQL Server
   docker run -d --name qb-db \
     -e ACCEPT_EULA=Y \
     -e SA_PASSWORD=TestPassword123! \
     -p 1433:1433 \
     mcr.microsoft.com/mssql/server:2022-latest
   ```

3. **Manual database setup**:
   ```sql
   -- Connect to SQL Server and run manually:
   CREATE DATABASE quickbuild;
   GO
   USE quickbuild;
   GO
   CREATE LOGIN qb_user WITH PASSWORD = 'QBTestPassword123!';
   CREATE USER qb_user FOR LOGIN qb_user;
   ALTER ROLE db_owner ADD MEMBER qb_user;
   GO
   ```

### QuickBuild Server Issues

**Problem**: Server fails to start or connect to database

**Solutions**:
1. **Check Java classpath**:
   ```bash
   docker exec -it qb-server ls -la /opt/quickbuild/lib/
   docker exec -it qb-server ls -la /opt/quickbuild/plugins/
   ```

2. **Test database connectivity from server**:
   ```bash
   docker exec -it qb-server nc -zv qb-database 1433
   ```

3. **Check QuickBuild logs**:
   ```bash
   docker exec -it qb-server tail -f /opt/quickbuild/logs/server.log
   ```

## Manual Configuration Steps

### 1. Database Setup (Manual)
If automated setup fails:

```bash
# Start basic SQL Server
docker run -d --name manual-qb-db \
  -e ACCEPT_EULA=Y \
  -e SA_PASSWORD=TestPassword123! \
  -p 1433:1433 \
  mcr.microsoft.com/mssql/server:2022-latest

# Wait for startup, then create database
docker exec -it manual-qb-db /opt/mssql-tools/bin/sqlcmd \
  -S localhost -U sa -P "TestPassword123!" \
  -Q "CREATE DATABASE quickbuild; CREATE LOGIN qb_user WITH PASSWORD = 'QBTestPassword123!'; USE quickbuild; CREATE USER qb_user FOR LOGIN qb_user; ALTER ROLE db_owner ADD MEMBER qb_user;"
```

### 2. Server Configuration
```bash
# Build server with manual config
docker build -t qb-server-manual ./qb-server

# Run with environment variables
docker run -d --name qb-server-manual \
  -e QB_DB_HOST=host.docker.internal \
  -e QB_DB_PORT=1433 \
  -e QB_DB_NAME=quickbuild \
  -e QB_DB_USER=qb_user \
  -e QB_DB_PASSWORD=QBTestPassword123! \
  -p 8810:8810 \
  qb-server-manual
```

## Performance Optimization

### Resource Requirements
- **Minimum**: 4GB RAM, 2 CPU cores
- **Recommended**: 8GB RAM, 4 CPU cores
- **Production**: 16GB RAM, 8 CPU cores

### Docker Settings
```yaml
# In docker-compose.yml
services:
  qb-database:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 6G
        reservations:
          cpus: '2'
          memory: 4G
  
  qb-server:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 6G
        reservations:
          cpus: '2'
          memory: 4G
```

## Testing Checklist

### Database Tests
- [ ] SQL Server container starts successfully
- [ ] Database `quickbuild` is created
- [ ] User `qb_user` exists with proper permissions
- [ ] Port 1433 is accessible
- [ ] Health check passes

### Server Tests
- [ ] QuickBuild server container starts
- [ ] Database connection successful
- [ ] Web interface accessible on port 8810
- [ ] Initial setup wizard appears
- [ ] Can create first admin user

### Integration Tests
- [ ] Server connects to database
- [ ] Web UI loads completely
- [ ] Can create and run a simple build
- [ ] Agents can connect to server
- [ ] Build artifacts are stored

## Alternative Deployment Options

### 1. Kubernetes Deployment
Use the provided Kubernetes manifests:
```bash
kubectl apply -f kubernetes/
```

### 2. Docker Swarm
```bash
docker stack deploy -c docker-compose.yml quickbuild
```

### 3. Separate Host Deployment
- Database on dedicated SQL Server instance
- QuickBuild server in container pointing to external DB
- Agents as separate containers or VMs

## Validation Commands

### Quick Health Check
```bash
# Check all containers
docker-compose ps

# Test database
curl -f http://localhost:1433 || echo "DB not ready"

# Test QuickBuild web interface
curl -f http://localhost:8810 || echo "QB not ready"

# Check logs for errors
docker-compose logs | grep -i error
```

### Detailed Diagnostics
```bash
# Container resource usage
docker stats

# Network connectivity
docker network ls
docker network inspect quickbuild14-test_qb_net

# Volume usage
docker volume ls
docker volume inspect quickbuild14-test_server_data
```

## Support Information

### Log Locations
- Database logs: `docker-compose logs qb-database`
- Server logs: `docker exec qb-server tail -f /opt/quickbuild/logs/server.log`
- Container logs: `docker-compose logs -f`

### Configuration Files
- Database: `qb-database/docker-entrypoint.sh`
- Server: `qb-server/entrypoint.sh`
- Compose: `docker-compose.yml`
- Environment: `.env`

### Common Ports
- QuickBuild Web: 8810
- SQL Server: 1433
- Agent Communication: 8811

This guide should help you manually test and troubleshoot the containerized QuickBuild deployment.