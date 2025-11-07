# QuickBuild 14 Configuration Reference

Complete reference for all configuration options, environment variables, and customization settings for the QuickBuild 14 containerization solution.

## Table of Contents

- [Environment Variables](#environment-variables)
- [Configuration Files](#configuration-files)
- [Docker Compose Configuration](#docker-compose-configuration)
- [Kubernetes Configuration](#kubernetes-configuration)
- [Agent Configuration](#agent-configuration)
- [Security Configuration](#security-configuration)
- [Performance Tuning](#performance-tuning)

## Environment Variables

### Database Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MSSQL_SA_PASSWORD` | *Required* | SQL Server SA account password (min 8 chars, complex) |
| `QB_DB_PASSWORD` | *Required* | QuickBuild database user password |
| `MSSQL_PID` | `Express` | SQL Server edition (Express, Developer, Standard, Enterprise) |
| `MSSQL_COLLATION` | `SQL_Latin1_General_CP1_CI_AS` | Database collation |

### QuickBuild Server Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `QB_DB_TYPE` | `mssql` | Database type (always mssql for this deployment) |
| `QB_DB_HOST` | `qb-database` | Database hostname |
| `QB_DB_PORT` | `1433` | Database port |
| `QB_DB_NAME` | `quickbuild` | Database name |
| `QB_DB_USER` | `qb_user` | Database username |
| `QB_SERVER_PORT` | `8810` | QuickBuild server HTTP port |
| `QB_SERVER_URL` | `http://qb-server:8810` | Server URL for agent connections |
| `QB_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARN, ERROR) |

### Build Agent Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_PORT` | `8811` | Agent communication port |
| `AGENT_NAME` | *Auto-generated* | Agent name (hostname-timestamp) |
| `AGENT_REPLICAS` | `2` | Number of agents to start |

#### Maven Agent Specific

| Variable | Default | Description |
|----------|---------|-------------|
| `MAVEN_OPTS` | `-Xmx1024m -XX:MaxPermSize=256m` | Maven JVM options |

#### .NET Agent Specific

| Variable | Default | Description |
|----------|---------|-------------|
| `DOTNET_CLI_TELEMETRY_OPTOUT` | `1` | Disable .NET telemetry |
| `DOTNET_SKIP_FIRST_TIME_EXPERIENCE` | `1` | Skip first-time setup |
| `DOTNET_NOLOGO` | `1` | Disable .NET logo |

### Docker Compose Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `COMPOSE_PROJECT_NAME` | `quickbuild14` | Docker Compose project name |
| `QB_NETWORK_SUBNET` | `172.20.0.0/16` | Custom network subnet |

### Kubernetes Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `QB_NAMESPACE` | `quickbuild` | Kubernetes namespace |
| `QB_STORAGE_CLASS` | `standard` | Storage class for PVCs |
| `DB_STORAGE_SIZE` | `10Gi` | Database storage size |
| `SERVER_STORAGE_SIZE` | `20Gi` | Server storage size |

### Security Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `QB_ENABLE_TLS` | `false` | Enable TLS/SSL (set to true for production) |
| `QB_TLS_CERT_PATH` | `/etc/ssl/certs/qb-server.crt` | TLS certificate path |
| `QB_TLS_KEY_PATH` | `/etc/ssl/private/qb-server.key` | TLS private key path |

### Monitoring and Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `QB_ENABLE_HEALTH_CHECKS` | `true` | Enable health check endpoints |
| `QB_HEALTH_CHECK_INTERVAL` | `30` | Health check interval (seconds) |

### Backup Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKUP_RETENTION_DAYS` | `30` | Backup retention period |
| `BACKUP_PATH` | `./backups` | Backup storage path |

### Development/Testing Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `QB_DEBUG_MODE` | `false` | Enable debug mode (development only) |
| `SKIP_SECURITY_SCAN` | `false` | Skip vulnerability scanning |
| `USE_LOCAL_IMAGES` | `false` | Use local images instead of pulling |

## Configuration Files

### Hibernate Configuration Template

Location: `qb-server/hibernate.properties.template`

Key settings for Microsoft SQL Server:

```properties
# Database connection
hibernate.connection.driver_class=com.microsoft.sqlserver.jdbc.SQLServerDriver
hibernate.dialect=org.hibernate.dialect.SQLServer2012Dialect
hibernate.connection.url=jdbc:sqlserver://${QB_DB_HOST}:${QB_DB_PORT};databaseName=${QB_DB_NAME};encrypt=true;trustServerCertificate=true

# Connection pooling (C3P0)
hibernate.c3p0.max_size=20
hibernate.c3p0.min_size=5
hibernate.c3p0.timeout=300
hibernate.c3p0.max_statements=50

# Performance settings
hibernate.jdbc.batch_size=20
hibernate.jdbc.fetch_size=100
hibernate.cache.use_second_level_cache=true
```

### Java Wrapper Configuration Template

Location: `qb-server/wrapper.conf.template`

Key settings for containerized deployment:

```properties
# Java settings
wrapper.java.command=${JAVA_HOME}/bin/java
wrapper.java.additional.1=-server
wrapper.java.additional.2=-Dfile.encoding=UTF-8
wrapper.java.additional.3=-Djava.awt.headless=true

# Memory settings
wrapper.java.initmemory=512
wrapper.java.maxmemory=2048

# Application settings
wrapper.app.parameter.1=server
```

## Docker Compose Configuration

### Multi-Environment Setup

The solution supports multiple Docker Compose configurations:

#### Base Configuration (`docker-compose.yml`)
- Core service definitions
- Basic networking and volumes
- Default resource limits

#### Development Override (`docker-compose.dev.yml`)
- Debug port exposure (5005 for JVM debugging)
- Local volume mounts for development
- Reduced resource limits
- Database port exposure for direct access

#### Production Override (`docker-compose.prod.yml`)
- Docker secrets integration
- Enhanced resource limits
- Restart policies with failure handling
- Bind mount volumes for production data

#### Scaling Configuration (`docker-compose.scale.yml`)
- Advanced replica management
- Rolling update strategies
- Node placement constraints
- Failure handling policies

### Usage Examples

```bash
# Development deployment
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Production deployment
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Scaling deployment
docker-compose -f docker-compose.yml -f docker-compose.scale.yml up -d
```

## Kubernetes Configuration

### ConfigMaps

#### Server ConfigMap (`quickbuild-server-config`)
```yaml
data:
  QB_DB_TYPE: "mssql"
  QB_DB_HOST: "qb-database-service"
  QB_SERVER_PORT: "8810"
  JAVA_OPTS: "-Xmx2048m -Xms1024m"
```

#### Database ConfigMap (`quickbuild-database-config`)
```yaml
data:
  ACCEPT_EULA: "Y"
  MSSQL_PID: "Express"
  MSSQL_COLLATION: "SQL_Latin1_General_CP1_CI_AS"
```

#### Agent ConfigMap (`quickbuild-agent-config`)
```yaml
data:
  QB_SERVER_URL: "http://qb-server-service:8810"
  AGENT_PORT: "8811"
  MAVEN_OPTS: "-Xmx1024m -XX:MaxPermSize=256m"
```

### Secrets

#### Database Secrets (`quickbuild-database-secrets`)
```yaml
data:
  SA_PASSWORD: <base64-encoded-password>
  QB_DB_PASSWORD: <base64-encoded-password>
```

#### TLS Secrets (`quickbuild-tls-secrets`)
```yaml
type: kubernetes.io/tls
data:
  tls.crt: <base64-encoded-certificate>
  tls.key: <base64-encoded-private-key>
```

### Persistent Volume Claims

| PVC Name | Size | Access Mode | Purpose |
|----------|------|-------------|---------|
| `qb-database-data-pvc` | 10Gi | ReadWriteOnce | Database files |
| `qb-database-logs-pvc` | 5Gi | ReadWriteOnce | Database logs |
| `qb-server-data-pvc` | 20Gi | ReadWriteOnce | Server data |
| `qb-maven-cache-pvc` | 5Gi | ReadWriteMany | Maven cache |
| `qb-node-cache-pvc` | 3Gi | ReadWriteMany | Node.js cache |
| `qb-dotnet-cache-pvc` | 3Gi | ReadWriteMany | .NET packages |

## Agent Configuration

### Base Agent Configuration

All agents inherit from the base configuration:

```properties
# Server connection
serverUrl=http://qb-server:8810
port=8811

# Agent identification
name=<auto-generated>
ip=<auto-detected>

# Performance settings
maxConcurrentBuilds=2
buildTimeout=3600
```

### Specialized Agent Configurations

#### Maven Agent
- Pre-installed Maven 3.8.8
- Optimized `settings.xml` with local repository configuration
- Build tools for native compilation
- Pre-cached common plugins

#### Node.js Agent
- Node.js 16.20.2 via NVM
- Global packages: TypeScript, Angular CLI, Vue CLI, React tools
- Yarn package manager
- Optimized npm configuration

#### .NET Agent
- .NET SDK 6.0
- Global tools: Entity Framework, Code Generator
- NuGet configuration with package caching
- Cross-platform compatibility

### Agent Scaling

#### Docker Compose Scaling
```bash
# Scale specific agent type
./scripts/scale-agents.sh scale maven 5

# Scale all agents
./scripts/scale-agents.sh up 2

# Check status
./scripts/scale-agents.sh status
```

#### Kubernetes Scaling
```bash
# Scale deployment
kubectl scale deployment qb-agent-maven --replicas=5 -n quickbuild

# Check status
kubectl get pods -n quickbuild -l app.kubernetes.io/variant=maven
```

## Security Configuration

### Password Requirements

#### SQL Server SA Password
- Minimum 8 characters
- Must contain uppercase letters
- Must contain lowercase letters
- Must contain numbers
- Must contain special characters

#### QuickBuild Database Password
- Minimum 12 characters recommended
- Mixed case letters, numbers, and symbols
- Avoid dictionary words

### TLS Configuration

#### Development (Self-Signed)
```bash
# Generate self-signed certificate
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout secrets/qb_server.key \
  -out secrets/qb_server.crt \
  -subj "/CN=localhost"
```

#### Production (CA-Signed)
```bash
# Use certificates from your Certificate Authority
# Place certificate files in secrets/ directory
# Update docker-compose.prod.yml or Kubernetes secrets
```

### Network Security

#### Docker Compose
- Custom bridge network (`qb-net`) for service isolation
- Database port not exposed externally
- Only QuickBuild server port (8810) exposed

#### Kubernetes
- Network policies for pod-to-pod communication
- Services with ClusterIP for internal access
- Ingress for controlled external access

### File Permissions

| File Type | Permissions | Description |
|-----------|-------------|-------------|
| Entrypoint scripts | 755 | Executable by owner, readable by all |
| Configuration templates | 644 | Readable by owner and group |
| Generated configurations | 600 | Readable only by owner |
| Secret files | 600 | Readable only by owner |

## Performance Tuning

### Database Performance

#### Connection Pool Settings
```properties
hibernate.c3p0.max_size=20          # Maximum connections
hibernate.c3p0.min_size=5           # Minimum connections
hibernate.c3p0.timeout=300          # Connection timeout (seconds)
hibernate.c3p0.max_statements=50    # Prepared statement cache
hibernate.c3p0.idle_test_period=3000 # Idle connection test interval
```

#### SQL Server Configuration
```yaml
# Resource limits for database container
resources:
  requests:
    memory: "2Gi"
    cpu: "1000m"
  limits:
    memory: "4Gi"
    cpu: "2000m"
```

### Server Performance

#### JVM Settings
```properties
# Memory allocation
wrapper.java.initmemory=1024        # Initial heap size (MB)
wrapper.java.maxmemory=4096         # Maximum heap size (MB)

# Performance options
wrapper.java.additional.1=-server
wrapper.java.additional.2=-XX:+UseG1GC
wrapper.java.additional.3=-XX:MaxGCPauseMillis=200
```

#### Resource Limits
```yaml
resources:
  requests:
    memory: "2Gi"
    cpu: "1000m"
  limits:
    memory: "4Gi"
    cpu: "2000m"
```

### Agent Performance

#### Maven Agent Optimization
```xml
<!-- settings.xml configuration -->
<settings>
  <localRepository>/opt/qb-agent/.m2/repository</localRepository>
  <offline>false</offline>
  <!-- Parallel builds -->
  <profiles>
    <profile>
      <properties>
        <maven.compiler.fork>true</maven.compiler.fork>
        <maven.compiler.maxmem>1024m</maven.compiler.maxmem>
      </properties>
    </profile>
  </profiles>
</settings>
```

#### Node.js Agent Optimization
```bash
# NPM configuration for performance
npm config set cache /opt/qb-agent/.npm
npm config set registry https://registry.npmjs.org/
npm config set audit-level moderate
```

#### .NET Agent Optimization
```xml
<!-- NuGet.Config for performance -->
<configuration>
  <config>
    <add key="globalPackagesFolder" value="/opt/qb-agent/.nuget/packages" />
    <add key="http_proxy" value="" />
    <add key="https_proxy" value="" />
  </config>
</configuration>
```

### Monitoring and Alerting

#### Health Check Configuration
```bash
# Health check intervals
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3

# Custom thresholds
ALERT_THRESHOLD_CPU=80
ALERT_THRESHOLD_MEMORY=85
ALERT_THRESHOLD_DISK=90
```

#### Metrics Collection
```bash
# Prometheus metrics endpoint
./scripts/health-check.sh all -f prometheus

# JSON metrics for custom monitoring
./scripts/health-check.sh all -f json
```

## Customization Examples

### Custom Agent Image

```dockerfile
# Extend base agent with custom tools
FROM qb-agent-base:latest

# Install custom tools
RUN apt-get update && apt-get install -y \
    custom-tool \
    another-tool \
    && rm -rf /var/lib/apt/lists/*

# Configure custom environment
ENV CUSTOM_TOOL_HOME=/opt/custom-tool
ENV PATH=$PATH:$CUSTOM_TOOL_HOME/bin
```

### Custom Configuration

```yaml
# docker-compose.override.yml
version: '3.8'
services:
  qb-server:
    environment:
      - CUSTOM_SETTING=value
    volumes:
      - ./custom-config:/opt/quickbuild/custom-config:ro
```

### Environment-Specific Overrides

```bash
# Create environment-specific .env files
cp .env.example .env.development
cp .env.example .env.staging
cp .env.example .env.production

# Use with Docker Compose
docker-compose --env-file .env.production up -d
```

This configuration reference provides comprehensive coverage of all customization options available in the QuickBuild 14 containerization solution.