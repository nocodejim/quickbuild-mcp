# QuickBuild 14 - Simplified Quick Start

## TL;DR - Get Running Fast

### Option 1: Skip Database Issues - Use External SQL Server
```bash
# Start with external database (easiest)
docker run -d --name qb-db \
  -e ACCEPT_EULA=Y \
  -e SA_PASSWORD=TestPassword123! \
  -p 1433:1433 \
  mcr.microsoft.com/mssql/server:2022-latest

# Wait 30 seconds, then create QuickBuild database
docker exec qb-db /opt/mssql-tools/bin/sqlcmd \
  -S localhost -U sa -P "TestPassword123!" \
  -Q "CREATE DATABASE quickbuild; CREATE LOGIN qb_user WITH PASSWORD = 'QBTestPassword123!'; USE quickbuild; CREATE USER qb_user FOR LOGIN qb_user; ALTER ROLE db_owner ADD MEMBER qb_user;"

# Build and run QuickBuild server
docker-compose build qb-server
docker run -d --name qb-server \
  --link qb-db:qb-database \
  -e QB_DB_HOST=qb-database \
  -e QB_DB_PASSWORD=QBTestPassword123! \
  -p 8810:8810 \
  quickbuild14-test-qb-server

# Check if it's working
curl http://localhost:8810
```

### Option 2: Cloud VM Testing (Recommended for Jules)
```bash
# On a fresh Ubuntu 22.04 VM with 8GB+ RAM:

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
newgrp docker

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Clone and setup
git clone <your-repo>
cd quickbuild-mcp

# Quick test with simplified setup
docker-compose -f docker-compose.simple.yml up -d
```

### Option 3: Kubernetes Testing
```bash
# If you have a Kubernetes cluster available
kubectl apply -f kubernetes/
kubectl get pods -w
kubectl port-forward svc/quickbuild-server 8810:8810
```

## Troubleshooting the Current Issue

The database initialization is hanging. Here's what to check:

### 1. Memory Issue
```bash
# Check available memory
free -h
# If less than 6GB available, SQL Server may fail to start

# Increase Docker memory limit to 6GB+ in Docker Desktop settings
```

### 2. SQL Server Startup Issue
```bash
# Check if SQL Server process is actually running
docker exec qb-database ps aux | grep sql

# Check SQL Server error logs
docker exec qb-database cat /var/opt/mssql/log/errorlog

# Try connecting directly
docker exec qb-database /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P "TestPassword123!" -Q "SELECT @@VERSION"
```

### 3. Custom Entrypoint Issue
The custom entrypoint might be interfering. Try bypassing it:

```bash
# Stop current container
docker-compose down

# Start with standard SQL Server image
docker run -d --name test-db \
  -e ACCEPT_EULA=Y \
  -e SA_PASSWORD=TestPassword123! \
  -p 1433:1433 \
  mcr.microsoft.com/mssql/server:2022-latest

# Test if this works
sleep 30
docker exec test-db /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P "TestPassword123!" -Q "SELECT 1"
```

## For Jules - Cloud VM Specs

### Minimum VM Requirements
- **Instance Type**: 
  - AWS: t3.xlarge (4 vCPU, 16GB RAM)
  - Azure: Standard_D4s_v3 (4 vCPU, 16GB RAM)
  - GCP: e2-standard-4 (4 vCPU, 16GB RAM)
- **Storage**: 50GB SSD
- **OS**: Ubuntu 22.04 LTS
- **Ports**: 22 (SSH), 8810 (QuickBuild), 1433 (SQL Server)

### One-Liner Setup Script
```bash
#!/bin/bash
# Save as setup-quickbuild.sh and run on fresh Ubuntu VM

set -e

echo "Installing Docker..."
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

echo "Installing Docker Compose..."
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

echo "Setting up QuickBuild..."
# You'll need to upload the project files or clone from git

echo "Starting simplified deployment..."
# Use external database approach
docker run -d --name qb-db \
  -e ACCEPT_EULA=Y \
  -e SA_PASSWORD=TestPassword123! \
  -p 1433:1433 \
  mcr.microsoft.com/mssql/server:2022-latest

echo "Waiting for SQL Server to start..."
sleep 60

echo "Creating QuickBuild database..."
docker exec qb-db /opt/mssql-tools/bin/sqlcmd \
  -S localhost -U sa -P "TestPassword123!" \
  -Q "CREATE DATABASE quickbuild; CREATE LOGIN qb_user WITH PASSWORD = 'QBTestPassword123!'; USE quickbuild; CREATE USER qb_user FOR LOGIN qb_user; ALTER ROLE db_owner ADD MEMBER qb_user;"

echo "Setup complete! Database is ready."
echo "Now build and start QuickBuild server manually."
```

## Expected Results

### Success Indicators
- SQL Server responds to `SELECT 1` query
- QuickBuild web interface loads on port 8810
- Initial setup wizard appears
- Can create admin user

### Common Failure Points
1. **Memory**: SQL Server needs 4GB+ RAM
2. **Startup Time**: SQL Server can take 2-3 minutes to fully start
3. **Database Creation**: Manual database setup is more reliable
4. **Network**: Ensure containers can communicate

## Next Steps After Success

1. **Test Basic Functionality**:
   - Create a simple build configuration
   - Run a test build
   - Verify build artifacts are stored

2. **Add Build Agents**:
   ```bash
   docker-compose up -d qb-agent-base
   ```

3. **Configure Production Settings**:
   - Set up SSL/HTTPS
   - Configure proper authentication
   - Set up backup procedures

## Support Commands

```bash
# Check everything is running
docker ps
docker-compose ps

# View all logs
docker-compose logs

# Test database connectivity
docker exec qb-database /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P "TestPassword123!" -Q "SELECT 1"

# Test QuickBuild web interface
curl -I http://localhost:8810

# Clean restart
docker-compose down -v
docker system prune -f
docker-compose up -d
```

This simplified approach should get you running much faster by avoiding the complex database initialization issues.