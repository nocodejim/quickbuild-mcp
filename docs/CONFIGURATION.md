# QuickBuild 16 Configuration Reference

Complete reference for all configuration options, environment variables, and customization settings for the QuickBuild 16 containerization solution.

## Table of Contents

- [Environment Variables](#environment-variables)
- [Image Build Arguments](#image-build-arguments)
- [Configuration Files](#configuration-files)
- [Docker Compose Configuration](#docker-compose-configuration)
- [Kubernetes Configuration](#kubernetes-configuration)
- [Agent Configuration](#agent-configuration)
- [Security Configuration](#security-configuration)
- [Performance Tuning](#performance-tuning)

## Environment Variables

### MCP Server Configuration

All MCP server settings are read and validated once at startup (`src/config.py`); an invalid
value stops the server with a message naming the variable. Secrets are never logged.

#### Connecting to QuickBuild

| Variable | Default | Description |
|----------|---------|-------------|
| `QB_URL` | `http://localhost:8810` | QuickBuild server URL (`http://qb-server:8810` inside the compose network, `https://...` for a corporate server) |
| `QB_USER` | `admin` | QuickBuild account used by the MCP server (a dedicated service account is recommended) |
| `QB_AUTH_MODE` | `basic` | `basic`: HTTP Basic `QB_USER:QB_PASSWORD` on every request (the QuickBuild REST API scheme). `token`: HTTP Basic `QB_USER:QB_TOKEN` with the user's QuickBuild access token. `session`: legacy login via `POST /rest/authentication` (only for proxies that provide it) |
| `QB_PASSWORD` / `QB_PASSWORD_FILE` | *Required* unless `QB_AUTH_MODE=token` | Password for `QB_USER`. `QB_PASSWORD_FILE` (a mounted Docker/Kubernetes secret) wins over `QB_PASSWORD`; one trailing newline is stripped |
| `QB_TOKEN` / `QB_TOKEN_FILE` | *Required* with `QB_AUTH_MODE=token` | QuickBuild access token of `QB_USER` (*My Setting > Access Token*, 40 characters). File form as above |
| `QB_TIMEOUT` | `30` | Seconds to wait for QuickBuild per request (connect and read) |
| `QB_VERIFY_SSL` | `true` | Verify QuickBuild's TLS certificate. `false` is for testing only and logs a warning |
| `QB_CA_BUNDLE` | *unset* | PEM file (or directory) with the CA certificates that signed QuickBuild's certificate, e.g. the corporate root CA. Added to the public CA roots, not a replacement |
| `HTTPS_PROXY` / `HTTP_PROXY` / `ALL_PROXY` / `NO_PROXY` | *unset* | Standard proxy variables (see below) |
| `QB_BACKUP_DIR` | `/opt/quickbuild/data/backup` | Server-side directory for `system.backup_database` when no `backup_path` is given |
| `QB_CACHE_TTL_CONFIGS` | `300` | Configuration list (and configuration path lookup) cache TTL in seconds (`0` disables) |
| `QB_CACHE_TTL_AGENTS` | `30` | Agent list cache TTL in seconds (`0` disables) |

#### Safety

| Variable | Default | Description |
|----------|---------|-------------|
| `QB_READ_ONLY` | `false` | `true` hides the write tools (`builds.trigger`, `build_requests.cancel`, `system.backup_database`) from `tools/list` **and** refuses them by name with an error, without contacting QuickBuild |

Every tool carries MCP annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`), so
clients and gateways can apply their own policy too. A tool without a read-only annotation is
treated as a write tool.

#### MCP transport

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_TRANSPORT` | `stdio` | `stdio` (a client starts the server as a subprocess) or `http` (Streamable HTTP, for a gateway). The compose service uses `http` |
| `MCP_HOST` | `127.0.0.1` | Address the HTTP server binds to. The container image sets `0.0.0.0`, which is required for a published port |
| `MCP_PORT` | `14002` | HTTP port. In compose, `MCP_PORT` is the published host port; the container always listens on 14002 |
| `MCP_HTTP_PATH` | `/mcp` | Path of the MCP endpoint |
| `MCP_HTTP_STATELESS` | `true` | Stateless Streamable HTTP (no session affinity needed behind a gateway or with several replicas). `false` keeps MCP sessions in memory |
| `MCP_ALLOWED_HOSTS` | *unset* | Comma-separated `Host` header values the HTTP server accepts (DNS-rebinding protection), e.g. `quickbuild-mcp.corp:*,localhost:*`; other hosts get HTTP 421. Unset: loopback binds are protected by the MCP SDK, other binds accept any host (a warning is logged) |
| `MCP_ALLOWED_ORIGINS` | *unset* | Comma-separated `Origin` values accepted when a client sends one (browsers). Requires `MCP_ALLOWED_HOSTS` |
| `LOG_LEVEL` | `INFO` | Python log level (logs go to stderr) |

HTTP endpoints: `POST/GET /mcp` (MCP Streamable HTTP), `GET /health` (liveness; never contacts
QuickBuild) and `GET /ready` (200 when QuickBuild answers `/rest/version` within 5 s, else 503).
The container `HEALTHCHECK` runs `python -m src.healthcheck`, which probes `/health` in HTTP mode.

> Inbound authentication of MCP clients (OAuth 2.1 resource-server mode) is planned for the
> hardening phase (see TODO.md). Until then, expose port 14002 only to the gateway (cluster
> network policy / firewall) and let the gateway authenticate users.

#### Corporate deployment example

A FastMCP gateway reaching the MCP server in Kubernetes, which reaches an HTTPS QuickBuild
signed by the corporate CA through the egress proxy, read-only, with credentials from secrets:

```env
QB_URL=https://quickbuild.corp.example
QB_USER=svc-quickbuild-mcp
QB_AUTH_MODE=token
QB_TOKEN_FILE=/var/run/secrets/quickbuild/token
QB_CA_BUNDLE=/etc/ssl/corp/ca-bundle.pem
HTTPS_PROXY=http://proxy.corp.example:3128
NO_PROXY=quickbuild.corp.example,.svc.cluster.local
QB_READ_ONLY=true
QB_TIMEOUT=20
MCP_TRANSPORT=http
MCP_HOST=0.0.0.0
MCP_ALLOWED_HOSTS=quickbuild-mcp.quickbuild.svc.cluster.local:*,quickbuild-mcp:*
```

#### Proxies

The QuickBuild client honours `HTTPS_PROXY` (for `https://` URLs), `HTTP_PROXY` (for `http://`),
`ALL_PROXY` and `NO_PROXY`, read when the server starts. HTTPS goes through the proxy as a
`CONNECT` tunnel, so certificate verification (and `QB_CA_BUNDLE`) still applies end to end.
`NO_PROXY` accepts `*`, host names, domain suffixes (`corp.example` matches `corp.example`
and `qb.corp.example`; `.corp.example` only subdomains), exact IP addresses and `localhost`.
**CIDR ranges such as `10.0.0.0/8` are not supported** (requests to those addresses still use
the proxy, and the server logs a warning); list the QuickBuild host name or IP instead.

#### QuickBuild 16 specifics the client relies on

Verified against QuickBuild 16.0.37 by `scripts/e2e.sh`:

- Access tokens are sent as the HTTP Basic password; a `Bearer` header is rejected (401).
- Configuration arguments accept a numeric id or a path (`root/team/app`), resolved with
  `GET /rest/ids?configuration_path=`.
- Build logs come from `GET /download/{build id}/log` and only once a build has finished
  (no live log, no `Range` support); `builds.get_log` keeps just the tail in memory.
- Missing builds, configurations and requests come back as HTTP 500 with a "not found" body;
  they are reported as not found, not retried.
- `DELETE /rest/build_requests/{request id}` stops a running build (status `CANCELLED`);
  QuickBuild removes the request from the queue a moment later.
- Request ids and numeric ids are validated before they are placed in a URL path, and POST
  requests are only retried when the connection was never established (no duplicate builds).

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
| `QB_STORAGE_DIR` | `/var/lib/quickbuild/storage` | Global storage directory to enter in the setup wizard (must be outside `/opt/quickbuild`; mounted as its own volume) |
| `QB_JAVA_MAX_MEMORY_MB` | *(wrapper.conf: 2048)* | Optional JVM max heap override passed to the Java Service Wrapper |

### Build Agent Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_PORT` | `8811` | Agent communication port |
| `AGENT_NAME` | *Auto-generated* | Display name in container logs (QuickBuild identifies agents by host name and port) |
| `QB_AGENT_TOKEN` | *Generated* | Agent token written to `node.properties`. QuickBuild 16 agents require one; set it per agent to keep an authorized identity across container recreation |
| `AGENT_REPLICAS` | `2` | Number of agents to start |

#### Maven Agent Specific

| Variable | Default | Description |
|----------|---------|-------------|
| `MAVEN_OPTS` | `-Xmx1024m` | Maven JVM options |

#### .NET Agent Specific

| Variable | Default | Description |
|----------|---------|-------------|
| `DOTNET_CLI_TELEMETRY_OPTOUT` | `1` | Disable .NET telemetry |
| `DOTNET_SKIP_FIRST_TIME_EXPERIENCE` | `1` | Skip first-time setup |
| `DOTNET_NOLOGO` | `1` | Disable .NET logo |

### Docker Compose Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `COMPOSE_PROJECT_NAME` | `quickbuild` | Docker Compose project name (prefixes volume/network names; set `quickbuild14` to keep volumes from older deployments) |
| `QB_NETWORK_SUBNET` | `172.20.0.0/16` | Custom network subnet (change it if `docker compose up` reports `Pool overlaps with other one on this address space`) |

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

## Image Build Arguments

Versions are pinned in the Dockerfiles. Compose forwards these build args from your shell/`.env`
when set; otherwise the Dockerfile defaults apply.

| Build arg | Default | Used by |
|-----------|---------|---------|
| `JDK_IMAGE` | `eclipse-temurin:21-jdk-noble` | `qb-server`, `qb-agent-base` |
| `QB_VERSION` | `16.0.37` | `qb-server`, `qb-agent-base` |
| `QB_DOWNLOAD_URL` | `https://pmease.com/artifacts/6371/quickbuild-16.0.37.zip` | `qb-server`, `qb-agent-base` |
| `QB_DOWNLOAD_SHA256` | SHA-256 of the 16.0.37 zip | `qb-server`, `qb-agent-base` (empty = skip check) |
| `MSSQL_JDBC_VERSION` | `13.6.2.jre11` | `qb-server` (from Maven Central) |
| `MSSQL_JDBC_SHA256` | SHA-256 of that jar | `qb-server` (empty = skip check) |
| `MSSQL_IMAGE` | `mcr.microsoft.com/mssql/server:2025-CU11-ubuntu-24.04` | `qb-database` |
| `BASE_IMAGE` | `qb-agent-base:latest` | `qb-agent-{maven,node,dotnet}` |
| `MAVEN_VERSION` / `MAVEN_SHA512` | `3.9.16` / its SHA-512 | `qb-agent-maven` |
| `NODE_VERSION` / `NVM_VERSION` | `24.22.3` / `v0.41.0` | `qb-agent-node` (exact Node version required) |
| `DOTNET_SDK_IMAGE` | `mcr.microsoft.com/dotnet/sdk:10.0-noble` | `qb-agent-dotnet` |

The QuickBuild distribution comes from `environment/quickbuild-${QB_VERSION}/` (unpacked) or
`environment/quickbuild-${QB_VERSION}.zip` when present, otherwise from `QB_DOWNLOAD_URL`
(see `qb-server/fetch-quickbuild-dist.sh`). When changing `QB_VERSION`, also set `QB_DOWNLOAD_URL`
and `QB_DOWNLOAD_SHA256`. The images only use classic-builder Dockerfile features (no BuildKit needed).

## Configuration Files

### Hibernate Configuration Template

Location: `qb-server/hibernate.properties.template`

Rendered into `conf/hibernate.properties` on every container start. It mirrors the SQL Server
section shipped with QuickBuild 16 (Hibernate 5.4, where `SQLServer2012Dialect` is the newest SQL
Server dialect; it works with SQL Server 2016-2025):

```properties
hibernate.dialect=org.hibernate.dialect.SQLServer2012Dialect
hibernate.connection.driver_class=com.microsoft.sqlserver.jdbc.SQLServerDriver
hibernate.connection.url=jdbc:sqlserver://${QB_DB_HOST}:${QB_DB_PORT};databaseName=${QB_DB_NAME};encrypt=true;trustServerCertificate=true;loginTimeout=30

# Connection pool (HikariCP, as shipped with QuickBuild 16)
hibernate.connection.provider_class=org.hibernate.hikaricp.internal.HikariCPConnectionProvider
hibernate.hikari.maximumPoolSize=25
hibernate.hbm2ddl.auto=update
```

### Java Service Wrapper

The server and agents run QuickBuild's bundled Java Service Wrapper with the `conf/wrapper.conf`
shipped in the distribution (main class, classpath and the `--add-opens` flags required on
Java 17+). The entrypoint starts the wrapper in the foreground as PID 1 (equivalent to
`bin/server.sh console`), so `docker stop` shuts QuickBuild down gracefully. `wrapper.conf` and
`wrapper-license.conf` are refreshed from the image on every start because they reference
versioned jar names; set `QB_JAVA_MAX_MEMORY_MB` to change the heap size.

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
  MAVEN_OPTS: "-Xmx1024m"
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
ip=<auto-detected container IP>
token=<QB_AGENT_TOKEN, or kept from a previous start, or generated>
```

### Specialized Agent Configurations

#### Maven Agent
- Pre-installed Maven 3.9.16 (SHA-512 verified), compiling for Java 21 (`maven.compiler.release=21`)
- Optimized `settings.xml` with local repository configuration
- Build tools for native compilation
- Pre-cached common plugins

#### Node.js Agent
- Node.js 24.22.3 LTS via NVM v0.41.0
- Global packages: TypeScript, Angular CLI, ESLint, Prettier, Jest, webpack (deprecated `create-react-app` and `@vue/cli` removed)
- Yarn package manager
- Optimized npm configuration

#### .NET Agent
- .NET SDK 10.0 LTS (Ubuntu 24.04), `global.json` pinned to `10.0.100` with `rollForward: latestFeature`
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
# HikariCP (QuickBuild 16), set in qb-server/hibernate.properties.template
hibernate.hikari.maximumPoolSize=25                       # Maximum connections
hibernate.hikari.transactionIsolation=TRANSACTION_READ_COMMITTED
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

This configuration reference provides comprehensive coverage of all customization options available in the QuickBuild 16 containerization solution.