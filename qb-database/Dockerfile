# Microsoft SQL Server Database Container for QuickBuild 14
# Base: Microsoft SQL Server 2022 Linux Container
# Security: Runs with default MSSQL user, volume-based persistence
# Health: sqlcmd-based health checks

FROM mcr.microsoft.com/mssql/server:2022-latest

# Set environment variables for SQL Server
ENV ACCEPT_EULA=Y
ENV MSSQL_PID=Express
ENV MSSQL_COLLATION=SQL_Latin1_General_CP1_CI_AS

# Create directory for initialization scripts
RUN mkdir -p /opt/mssql-scripts

# Copy initialization scripts
COPY init-scripts/ /opt/mssql-scripts/
COPY healthcheck.sh /opt/mssql-scripts/

# Set proper permissions for scripts
RUN chmod +x /opt/mssql-scripts/*.sh
RUN chmod 644 /opt/mssql-scripts/*.sql

# Create custom entrypoint script to run initialization
COPY docker-entrypoint.sh /opt/mssql-scripts/
RUN chmod +x /opt/mssql-scripts/docker-entrypoint.sh

# Expose SQL Server port (internal network only)
EXPOSE 1433

# Configure health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD /opt/mssql-scripts/healthcheck.sh

# Use custom entrypoint for initialization
ENTRYPOINT ["/opt/mssql-scripts/docker-entrypoint.sh"]