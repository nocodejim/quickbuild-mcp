# Kiro Specification: QuickBuild 14 Multi-Container Deployment with Microsoft SQL Server

## Project Overview

This specification guides Kiro to build a production-ready, multi-tiered containerized deployment of QuickBuild 14 with Microsoft SQL Server as the database backend. The project will include complete Docker infrastructure, proper security configurations, and comprehensive documentation.

**Primary Reference Document**: The architectural blueprint in this conversation provides detailed requirements for QuickBuild 14 containerization. Additionally, consult the official QuickBuild 14 documentation at https://wiki.pmease.com/display/QB14 for specific configuration details.

**Key Deliverables**:
- Multi-container Docker setup with QB Server, MSSQL Database, and scalable Build Agents
- Complete Dockerfiles with security best practices
- Docker Compose orchestration file
- Kubernetes manifests for production deployment
- Entrypoint scripts with dynamic configuration
- Configuration templates for all services
- Comprehensive documentation and operational guides

---

## Kiro Agent Instructions

### How to Use This Specification

**For Kiro**: This document follows Kiro's spec-driven development approach. You should:

1. **Read the entire specification first** to understand the project scope
2. **Use the JIRA MCP integration** to create and track work items for complete transparency
3. **Execute tasks sequentially** as defined in the tasks.md file (do NOT execute all at once)
4. **Create a `.kiro/issues-lessons-learned.md` file** at project start to document:
   - Any errors encountered and how they were resolved
   - Unexpected challenges or edge cases discovered
   - Decisions made that deviated from the spec (with rationale)
   - Performance insights or optimization opportunities
   - Suggestions for spec improvements
5. **Update the issues document after each task** to maintain a living retrospective
6. **Reference the architectural document** provided in the conversation for technical depth

### JIRA Integration Requirements

**CRITICAL**: Kiro MUST use the JIRA MCP tools to maintain full project transparency:

**At Project Start**:
- Create an Epic in JIRA: "QuickBuild 14 Containerization with MSSQL"
- Use the `create_work_item` tool with type="Epic"

**For Each Major Component** (Server, Database, Agent):
- Create a Story in JIRA linked to the Epic
- Use the `create_work_item` tool with type="Story"

**For Each Task in tasks.md**:
- Create a Sub-task in JIRA linked to the appropriate Story
- Use the `create_work_item` tool with type="Sub-task"
- Update status as you progress: "To Do" → "In Progress" → "Done"
- Use `update_work_item` tool to change status and add comments

**Documentation Pattern**:
```
Task: [Task Name]
JIRA Ticket: [AUTO-GENERATED-ID]
Status: [In Progress/Done]
Notes: [Any relevant implementation details]
```

### Repository Structure

Create the following structure:

```
quickbuild14-mssql/
├── .kiro/
│   ├── steering/
│   │   ├── product.md
│   │   ├── tech.md
│   │   ├── structure.md
│   │   ├── docker-conventions.md
│   │   └── security-guidelines.md
│   ├── hooks/
│   │   └── documentation-update.json
│   └── issues-lessons-learned.md
├── qb-server/
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── hibernate.properties.template
│   └── wrapper.conf.template
├── qb-database/
│   ├── Dockerfile
│   ├── init-scripts/
│   │   ├── 01-create-database.sql
│   │   ├── 02-create-user.sql
│   │   └── 03-grant-permissions.sql
│   └── healthcheck.sh
├── qb-agent/
│   ├── base/
│   │   ├── Dockerfile
│   │   └── agent-entrypoint.sh
│   ├── maven/
│   │   └── Dockerfile
│   ├── node/
│   │   └── Dockerfile
│   └── dotnet/
│       └── Dockerfile
├── docker-compose.yml
├── kubernetes/
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── secrets.yaml
│   ├── pvc.yaml
│   ├── mssql-statefulset.yaml
│   ├── mssql-service.yaml
│   ├── qb-server-statefulset.yaml
│   ├── qb-server-service.yaml
│   ├── rbac.yaml
│   └── ingress.yaml
├── docs/
│   ├── DEPLOYMENT.md
│   ├── CONFIGURATION.md
│   ├── BACKUP-RESTORE.md
│   ├── TROUBLESHOOTING.md
│   └── SECURITY.md
├── scripts/
│   ├── backup.sh
│   ├── restore.sh
│   └── validate-deployment.sh
├── .env.example
├── .gitignore
└── README.md
```

### Steering Files to Create

Kiro should generate the following steering files in `.kiro/steering/`:

#### docker-conventions.md
```markdown
---
inclusion_mode: "always"
---

# Docker Best Practices for QuickBuild 14

## Base Image Selection
- Use specific version tags, never `:latest`
- Prefer Alpine-based images for smaller footprint where possible
- Use eclipse-temurin for Java base images (JDK 8 required for QB14)

## Security Standards
- Always run containers as non-root users
- Use multi-stage builds to minimize final image size
- Never include secrets in images - use environment variables
- Scan images with Trivy before deployment

## Layer Optimization
- Combine RUN commands to reduce layers
- Order commands from least to most frequently changing
- Clean up package manager caches in the same RUN command

## Health Checks
- Every service must include HEALTHCHECK directive
- Health checks should verify actual service functionality, not just process existence
```

#### security-guidelines.md
```markdown
---
inclusion_mode: "always"
---

# Security Guidelines for QuickBuild 14 Deployment

## Secrets Management
- Never commit secrets to Git
- Use Docker secrets or Kubernetes secrets for sensitive data
- Database passwords must be generated, not hardcoded
- Document required secrets in .env.example

## Network Security
- Use dedicated Docker networks for service isolation
- Expose only necessary ports
- Use TLS/SSL for all inter-service communication in production

## File Permissions
- Entrypoint scripts: 755
- Configuration templates: 644
- Generated configurations: 600 (readable only by owner)

## SQL Server Security
- Use SQL authentication with strong passwords
- Create dedicated database user with minimal required permissions
- Enable connection encryption
- Restrict network access to database port
```

### Agent Hook Configuration

Create a documentation update hook that automatically updates docs when code changes:

**.kiro/hooks/documentation-update.json**:
```json
{
  "name": "Update Documentation",
  "description": "Automatically updates relevant documentation when Dockerfiles or scripts are modified",
  "event": "fileSaved",
  "filePattern": "**/{Dockerfile,*.sh,docker-compose.yml}",
  "instructions": "When a Dockerfile, shell script, or docker-compose.yml is modified:\n1. Identify which documentation file would be affected\n2. Update the relevant sections in docs/ to reflect the changes\n3. Ensure examples match the actual code\n4. Add a changelog entry if significant changes were made",
  "autoApprove": false
}
```

---

## Technical Requirements Summary

### Database: Microsoft SQL Server (Linux Container)

**Key Differences from PostgreSQL** (as specified in architectural document):
- Use `mcr.microsoft.com/mssql/server:2022-latest` official image
- Requires `ACCEPT_EULA=Y` environment variable
- Uses port 1433 (default MSSQL port) instead of 5432
- SA account instead of POSTGRES_USER for initial setup
- Different JDBC URL format: `jdbc:sqlserver://host:port;databaseName=dbname;encrypt=true`
- Requires SQL Server JDBC driver in QuickBuild installation

**Required Configuration**:
```yaml
Environment Variables:
  - ACCEPT_EULA=Y (required)
  - SA_PASSWORD: Strong password (min 8 chars, upper, lower, number, special char)
  - MSSQL_PID: Express (free edition) or specific license key
  - MSSQL_COLLATION: SQL_Latin1_General_CP1_CI_AS

Volume Mounts:
  - /var/opt/mssql: Database files
  - /var/opt/mssql/log: Transaction logs
  - /opt/mssql-scripts: Init scripts

Health Check:
  - Use sqlcmd: /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P $SA_PASSWORD -Q "SELECT 1"
```

**Database Initialization Requirements**:
1. Create database: `quickbuild`
2. Create dedicated user: `qb_user` with strong password
3. Grant permissions:
   - db_owner role on quickbuild database
   - Or minimum: CREATE TABLE, ALTER, SELECT, INSERT, UPDATE, DELETE
4. Configure connection pooling settings for performance

**Hibernate Configuration for MSSQL**:
```properties
hibernate.connection.driver_class=com.microsoft.sqlserver.jdbc.SQLServerDriver
hibernate.dialect=org.hibernate.dialect.SQLServer2012Dialect
hibernate.connection.url=jdbc:sqlserver://qb-database:1433;databaseName=quickbuild;encrypt=true;trustServerCertificate=true
hibernate.connection.username=qb_user
hibernate.connection.password=${QB_DB_PASSWORD}
hibernate.c3p0.max_size=20
hibernate.c3p0.min_size=5
```

### QuickBuild Server

**Base Requirements** (from architectural document):
- JDK 8 or higher (use eclipse-temurin:8-jdk-focal)
- QuickBuild 14.0 server distribution
- Default port: 8810
- Critical files:
  - `conf/hibernate.properties`: Database connection
  - `conf/wrapper.conf`: Java wrapper configuration
  - `logs/`: Application logs
  - `artifacts/`: Build artifacts storage

**Dynamic Configuration via Environment Variables**:
```bash
QB_DB_TYPE=mssql
QB_DB_HOST=qb-database
QB_DB_PORT=1433
QB_DB_NAME=quickbuild
QB_DB_USER=qb_user
QB_DB_PASSWORD=<from-secret>
```

**Persistent Data Strategy**:
- Single consolidated volume: `/opt/quickbuild/data`
- Entrypoint script moves conf, logs, artifacts to data volume on first run
- Creates symlinks back to expected locations
- Ensures state survives container recreation

### QuickBuild Build Agents

**Base Requirements**:
- JDK 8 or higher
- QuickBuild 14.0 agent distribution
- Default port: 8811
- Configuration: `conf/node.properties`

**Critical Agent Configuration**:
```properties
serverUrl=http://qb-server:8810
ip=<auto-detected-container-ip>
port=8811
```

**Agent Specialization Strategy**:
- Base agent image with QB agent only
- Derived images for specific toolchains:
  - `qb-agent-maven`: Base + Maven
  - `qb-agent-node`: Base + Node.js 16.x via NVM
  - `qb-agent-dotnet`: Base + .NET SDK (for Windows builds compatibility)

### Networking Requirements

**Critical**: Bi-directional communication required between server and agents.

**Solution**: Dedicated bridge network `qb-net`
- DNS-based service discovery
- All containers attached to same network
- Server can resolve agent IPs and initiate connections
- Agents can discover server by service name

**Docker Compose Network**:
```yaml
networks:
  qb-net:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
```

**Kubernetes Network**: Use ClusterIP services with stable DNS names

---

## Security Requirements

### Non-Root User Execution
- All containers MUST run as non-root users
- Server: user `quickbuild` (UID 1000)
- Database: default MSSQL user
- Agents: user `qbagent` (UID 1001)

### Secrets Management
- Database passwords via Docker secrets or K8s secrets
- Never commit secrets to repository
- Provide `.env.example` with placeholder values
- Document secret generation in README

### Image Scanning
- All custom images must be scanned for vulnerabilities
- Include Trivy scan in CI/CD pipeline
- Document known acceptable vulnerabilities if any

### Network Isolation
- Database should NOT be exposed outside cluster
- Only QB Server port 8810 exposed externally
- Agent ports only accessible within qb-net network

---

## Performance Considerations

### Database Connection Pooling
Configure Hibernate C3P0 settings based on expected load:
- `hibernate.c3p0.max_size=20` (max connections)
- `hibernate.c3p0.min_size=5` (min connections)
- `hibernate.c3p0.timeout=300` (connection timeout)
- `hibernate.c3p0.max_statements=50` (prepared statement cache)

### Resource Limits (Docker Compose)
```yaml
qb-server:
  deploy:
    resources:
      limits:
        cpus: '2'
        memory: 4G
      reservations:
        cpus: '1'
        memory: 2G

qb-database:
  deploy:
    resources:
      limits:
        cpus: '2'
        memory: 4G
      reservations:
        cpus: '1'
        memory: 2G
```

### Kubernetes Resource Requests/Limits
Define appropriate values based on production workload testing.

---

## Documentation Requirements

### README.md
Must include:
- Project overview
- Quick start guide (< 5 minutes to running stack)
- Architecture diagram (Mermaid)
- Prerequisites
- Environment variable reference table
- Common troubleshooting steps
- Links to detailed docs

### DEPLOYMENT.md
Detailed deployment procedures for:
- Docker Compose (development/small deployments)
- Kubernetes (production)
- Initial setup steps
- Validation procedures

### CONFIGURATION.md
Complete reference for:
- All environment variables with defaults
- Configuration file templates
- Database initialization options
- Agent scaling procedures

### BACKUP-RESTORE.md
Step-by-step procedures for:
- Backing up QB data and database
- Restoring from backup
- Migration from existing QB installation
- Disaster recovery scenarios

### TROUBLESHOOTING.md
Common issues and solutions:
- Agent connection problems
- Database connectivity issues
- Performance problems
- Log analysis guidance

### SECURITY.md
Security considerations:
- Secrets management best practices
- Network security configuration
- Vulnerability scanning procedures
- Access control recommendations

---

## Testing and Validation Requirements

### Validation Script (scripts/validate-deployment.sh)
Must verify:
1. All containers are running and healthy
2. Database is accessible and initialized
3. QB Server UI is accessible on port 8810
4. At least one agent is connected
5. Network connectivity between all services
6. Persistent volumes are properly mounted

### Test Scenarios
Document procedures for:
1. Fresh installation
2. Backup and restore
3. Agent scaling (add/remove agents)
4. Configuration updates
5. Version upgrade (QB 14.0.x updates)

---

## Migration Path from Existing QuickBuild

For users with existing QB installations:

1. **Pre-Migration**:
   - Document current QB version and configuration
   - Perform full backup via QB admin UI
   - Export configuration if needed

2. **Data Migration**:
   - Deploy new containerized stack
   - Copy backup file into qb-server container
   - Execute restore script
   - Restart server to load restored data

3. **Validation**:
   - Verify all configurations present
   - Check build history
   - Test agent connectivity
   - Run sample build

4. **Cutover**:
   - Update DNS/load balancer to point to new deployment
   - Decommission old instance after validation period

---

## Operational Procedures

### Backup Strategy

**Docker Compose Environment**:
```bash
# Stop services
docker-compose down

# Backup volumes
docker run --rm -v qb-server-data:/data -v $(pwd)/backups:/backup \
  ubuntu tar czf /backup/qb-server-$(date +%Y%m%d).tar.gz /data

docker run --rm -v qb-db-data:/data -v $(pwd)/backups:/backup \
  ubuntu tar czf /backup/qb-db-$(date +%Y%m%d).tar.gz /data

# Restart services
docker-compose up -d
```

**Kubernetes Environment**:
- Use VolumeSnapshot resources
- Automate with Velero or cloud provider tools
- Schedule regular snapshots

### Monitoring

Recommended metrics to track:
- Container health status
- Database connection pool usage
- Build queue depth
- Agent availability
- Disk space usage for artifacts
- Memory and CPU utilization

### Log Management

Centralized logging strategy:
- Use Docker logging drivers or K8s log aggregation
- Retain logs for minimum 30 days
- Index by service and timestamp
- Alert on error patterns

---

## CRITICAL NOTES FOR KIRO

1. **Reference Architecture Document**: The architectural specification in this conversation is your primary technical reference. Consult it for detailed technical decisions.

2. **MSSQL-Specific Considerations**: 
   - Pay special attention to JDBC driver requirements
   - MSSQL has different initialization patterns than PostgreSQL
   - Connection string format is different
   - License acceptance (EULA) is required

3. **Testing as You Go**: After completing each major component (database, server, agent), create a simple test to verify functionality before proceeding.

4. **Documentation First**: Update relevant documentation immediately after implementing each component. Don't wait until the end.

5. **Issues & Lessons Learned**: This is NOT just an error log. Document:
   - "Why" decisions were made
   - Alternative approaches considered
   - Performance observations
   - Integration surprises
   - User experience insights

6. **JIRA Transparency**: Every task execution should have a corresponding JIRA update. This creates a complete audit trail of the AI agent's work.

7. **Security Review**: Before marking tasks complete, review for security implications. Use the security-guidelines.md steering file.

8. **Incremental Testing**: Don't wait until everything is built to test. Test each component as it's completed:
   - Database: Can connect? Can create tables?
   - Server: Can start? Can connect to DB?
   - Agent: Can connect to server?

---

## Success Criteria

The project is complete when:

✅ All Docker images build successfully without errors
✅ All containers start and pass health checks
✅ QB Server accessible on http://localhost:8810
✅ Database initialized with quickbuild schema
✅ At least one agent connects to server
✅ Complete documentation set in docs/ folder
✅ All JIRA tickets created and updated to "Done"
✅ `.kiro/issues-lessons-learned.md` contains comprehensive retrospective
✅ Validation script passes all checks
✅ Security scan shows no critical vulnerabilities
✅ README quick start successfully deploys stack in < 5 minutes

---

## Post-Implementation Retrospective

After project completion, Kiro should:

1. Review the `.kiro/issues-lessons-learned.md` file
2. Create a summary report of:
   - What went well
   - What was challenging
   - Recommendations for similar projects
   - Specification improvements needed
3. Update JIRA Epic with final summary
4. Generate a lessons-learned artifact for future reference

---

## Additional Resources

- Official QuickBuild 14 Documentation: https://wiki.pmease.com/display/QB14
- Microsoft SQL Server on Docker: https://learn.microsoft.com/en-us/sql/linux/quickstart-install-connect-docker
- Hibernate SQL Server Dialect: https://docs.jboss.org/hibernate/orm/5.6/javadocs/org/hibernate/dialect/SQLServer2012Dialect.html
- Docker Best Practices: https://docs.docker.com/develop/dev-best-practices/
- Kubernetes StatefulSets: https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/

---

**Version**: 1.0
**Created**: 2025-10-05
**Author**: AI Development Agent
**Project**: QuickBuild 14 Containerization with Microsoft SQL Server
