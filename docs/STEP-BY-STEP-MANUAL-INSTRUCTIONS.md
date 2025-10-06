# QuickBuild 14 - Step-by-Step Manual Instructions

## Prerequisites
- Docker and Docker Compose installed
- At least 8GB RAM available
- Ports 8810 and 1433 available
- QuickBuild 14.0.32 files in `environment/quickbuild-14.0.32/`

## Step 1: Clean Environment
```bash
# Stop any existing containers
docker-compose down -v

# Clean up Docker system
docker system prune -f

# Verify clean state
docker ps -a
```

## Step 2: Start Database (Simple Approach)
```bash
# Start standard SQL Server container
docker run -d \
  --name qb-database \
  --network bridge \
  -e ACCEPT_EULA=Y \
  -e SA_PASSWORD=TestPassword123! \
  -p 1433:1433 \
  mcr.microsoft.com/mssql/server:2022-latest

# Wait for SQL Server to start (important!)
echo "Waiting 90 seconds for SQL Server to fully start..."
sleep 90

# Verify SQL Server is running
docker logs qb-database | tail -10
```

## Step 3: Create QuickBuild Database
```bash
# Test SQL Server connectivity first
docker exec qb-database /opt/mssql-tools/bin/sqlcmd \
  -S localhost -U sa -P "TestPassword123!" \
  -Q "SELECT @@VERSION"

# If the above works, create the QuickBuild database
docker exec qb-database /opt/mssql-tools/bin/sqlcmd \
  -S localhost -U sa -P "TestPassword123!" \
  -Q "CREATE DATABASE quickbuild COLLATE SQL_Latin1_General_CP1_CI_AS;"

# Create QuickBuild user
docker exec qb-database /opt/mssql-tools/bin/sqlcmd \
  -S localhost -U sa -P "TestPassword123!" \
  -Q "CREATE LOGIN qb_user WITH PASSWORD = 'QBTestPassword123!';"

# Grant permissions
docker exec qb-database /opt/mssql-tools/bin/sqlcmd \
  -S localhost -U sa -P "TestPassword123!" \
  -Q "USE quickbuild; CREATE USER qb_user FOR LOGIN qb_user; ALTER ROLE db_owner ADD MEMBER qb_user;"

# Verify database setup
docker exec qb-database /opt/mssql-tools/bin/sqlcmd \
  -S localhost -U qb_user -P "QBTestPassword123!" \
  -Q "USE quickbuild; SELECT DB_NAME();"
```

## Step 4: Build QuickBuild Server
```bash
# Build the server container
docker-compose build qb-server

# Verify the build succeeded
docker images | grep quickbuild
```

## Step 5: Start QuickBuild Server
```bash
# Create a custom network for communication
docker network create qb-network

# Connect database to the network
docker network connect qb-network qb-database

# Start QuickBuild server with proper environment
docker run -d \
  --name qb-server \
  --network qb-network \
  -e QB_DB_HOST=qb-database \
  -e QB_DB_PORT=1433 \
  -e QB_DB_NAME=quickbuild \
  -e QB_DB_USER=qb_user \
  -e QB_DB_PASSWORD=QBTestPassword123! \
  -e QB_SERVER_PORT=8810 \
  -p 8810:8810 \
  quickbuild14-test-qb-server

# Monitor server startup
docker logs -f qb-server
```

## Step 6: Verify Everything is Working
```bash
# Check container status
docker ps

# Check server logs for any errors
docker logs qb-server | grep -i error

# Test database connectivity from server
docker exec qb-server nc -zv qb-database 1433

# Test web interface
curl -I http://localhost:8810

# If curl shows HTTP response, open browser to:
# http://localhost:8810
```

## Step 7: Initial QuickBuild Setup
1. Open browser to `http://localhost:8810`
2. You should see QuickBuild setup wizard
3. Follow the setup wizard to:
   - Create admin user
   - Configure basic settings
   - Complete initial setup

## Troubleshooting Commands

### If Database Connection Fails:
```bash
# Check if database is accessible from server
docker exec qb-server ping qb-database

# Check database logs
docker logs qb-database

# Test direct database connection
docker exec qb-server /opt/mssql-tools/bin/sqlcmd \
  -S qb-database -U qb_user -P "QBTestPassword123!" \
  -Q "SELECT 1"
```

### If Server Won't Start:
```bash
# Check server logs in detail
docker logs qb-server

# Check if QuickBuild files are present
docker exec qb-server ls -la /opt/quickbuild/

# Check Java version
docker exec qb-server java -version

# Check server script permissions
docker exec qb-server ls -la /opt/quickbuild/bin/server.sh
```

### If Web Interface Not Accessible:
```bash
# Check if server is listening on port 8810
docker exec qb-server netstat -tlnp | grep 8810

# Check server process
docker exec qb-server ps aux | grep java

# Check firewall/port forwarding
netstat -tlnp | grep 8810
```

## Alternative: Use Docker Compose (If Manual Steps Work)
Once you've verified the manual steps work, you can use docker-compose:

```bash
# Stop manual containers
docker stop qb-server qb-database
docker rm qb-server qb-database

# Use docker-compose with external database
docker run -d \
  --name qb-database \
  -e ACCEPT_EULA=Y \
  -e SA_PASSWORD=TestPassword123! \
  -p 1433:1433 \
  mcr.microsoft.com/mssql/server:2022-latest

# Wait and setup database (repeat Step 3)
sleep 90
# ... database setup commands from Step 3 ...

# Then start with compose
docker-compose up -d qb-server
```

## Expected Timeline
- **Step 1-2**: 2 minutes
- **Step 3**: 5 minutes (including wait time)
- **Step 4**: 5-10 minutes (depending on build speed)
- **Step 5**: 2-5 minutes
- **Step 6**: 2 minutes
- **Step 7**: 5-10 minutes

**Total**: 20-35 minutes

## Success Indicators
✅ SQL Server responds to queries  
✅ QuickBuild database exists  
✅ qb_user can connect to database  
✅ QuickBuild server starts without errors  
✅ Web interface loads on http://localhost:8810  
✅ Setup wizard appears  

## Common Issues and Solutions

### "SQL Server not ready"
- **Solution**: Wait longer (SQL Server can take 2-3 minutes)
- **Check**: `docker logs qb-database | grep "ready for client connections"`

### "Database connection failed"
- **Solution**: Verify database setup in Step 3
- **Check**: Test connection manually with sqlcmd

### "QuickBuild won't start"
- **Solution**: Check if QuickBuild files are properly copied
- **Check**: `docker exec qb-server ls -la /opt/quickbuild/bin/`

### "Web interface not loading"
- **Solution**: Check if server is actually listening
- **Check**: `docker exec qb-server netstat -tlnp | grep 8810`

## Next Steps After Success
1. Create a simple build configuration
2. Test running a build
3. Add build agents: `docker-compose up -d qb-agent-base`
4. Configure SSL/HTTPS for production use

## Clean Up (When Done Testing)
```bash
# Stop all containers
docker stop qb-server qb-database

# Remove containers
docker rm qb-server qb-database

# Remove network
docker network rm qb-network

# Remove images (optional)
docker rmi quickbuild14-test-qb-server
```

Follow these steps in order, and you should have a working QuickBuild 14 containerized environment!