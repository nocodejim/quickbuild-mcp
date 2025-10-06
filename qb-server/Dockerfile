# QuickBuild 14 Server Container
# Base: Eclipse Temurin JDK 8 (required for QB 14)
# Security: Non-root user execution (quickbuild UID 1000)
# Data: Consolidated volume approach for persistence

FROM eclipse-temurin:8-jdk-focal

# Metadata
LABEL maintainer="QuickBuild Containerization Project"
LABEL description="QuickBuild 14 Server with Microsoft SQL Server support"
LABEL version="14.0"

# Install required packages
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    unzip \
    gettext-base \
    netcat \
    && rm -rf /var/lib/apt/lists/*

# Create quickbuild user (UID 1000 for consistency)
RUN groupadd -r quickbuild --gid=1000 && \
    useradd -r -g quickbuild --uid=1000 --home-dir=/opt/quickbuild --shell=/bin/bash quickbuild

# Set QuickBuild version and download URL
ENV QB_VERSION=14.0.11
ENV QB_DOWNLOAD_URL=https://www.pmease.com/quickbuild/downloads/quickbuild-${QB_VERSION}.zip

# Create directories
RUN mkdir -p /opt/quickbuild /opt/quickbuild/data /tmp/qb-install

# Copy real QuickBuild 14.0.32 installation
COPY environment/quickbuild-14.0.32/quickbuild-14.0.32/ /opt/quickbuild/

# Download Microsoft SQL Server JDBC driver
ENV MSSQL_JDBC_VERSION=12.4.2.jre8
RUN echo "Downloading SQL Server JDBC driver..." && \
    wget -q "https://github.com/Microsoft/mssql-jdbc/releases/download/v${MSSQL_JDBC_VERSION}/mssql-jdbc-${MSSQL_JDBC_VERSION}.jar" \
    -O /opt/quickbuild/lib/mssql-jdbc.jar || \
    echo "Warning: Could not download JDBC driver, using existing drivers"

# Copy configuration templates and scripts
COPY qb-server/hibernate.properties.template /opt/quickbuild/conf/
COPY qb-server/wrapper.conf.template /opt/quickbuild/conf/
COPY qb-server/entrypoint.sh /opt/quickbuild/
COPY qb-server/healthcheck.sh /opt/quickbuild/

# Set proper permissions
RUN chown -R quickbuild:quickbuild /opt/quickbuild && \
    chmod +x /opt/quickbuild/entrypoint.sh && \
    chmod +x /opt/quickbuild/healthcheck.sh && \
    chmod +x /opt/quickbuild/bin/server.sh && \
    chmod 644 /opt/quickbuild/conf/*.template

# Create data volume mount point with proper ownership
RUN chown quickbuild:quickbuild /opt/quickbuild/data

# Set environment variables
ENV QB_HOME=/opt/quickbuild
ENV JAVA_HOME=/opt/java/openjdk
ENV PATH=$PATH:$QB_HOME/bin:$JAVA_HOME/bin

# Default environment variables (can be overridden)
ENV QB_DB_TYPE=mssql
ENV QB_DB_HOST=qb-database
ENV QB_DB_PORT=1433
ENV QB_DB_NAME=quickbuild
ENV QB_DB_USER=qb_user
ENV QB_SERVER_PORT=8810

# Expose QuickBuild server port
EXPOSE 8810

# Configure health check
HEALTHCHECK --interval=30s --timeout=15s --start-period=120s --retries=3 \
    CMD /opt/quickbuild/healthcheck.sh

# Switch to quickbuild user
USER quickbuild

# Set working directory
WORKDIR /opt/quickbuild

# Use custom entrypoint
ENTRYPOINT ["/opt/quickbuild/entrypoint.sh"]