# QuickBuild 16 Server Container
# Base: Eclipse Temurin JDK 21 on Ubuntu 24.04 (QuickBuild 15+ requires Java 11+; QB 16 supports up to Java 25)
# Security: Non-root user execution (quickbuild UID 1000)
# Data: Consolidated volume approach for persistence
#
# QuickBuild distribution source (first match wins; see qb-server/fetch-quickbuild-dist.sh):
#   1. environment/quickbuild-${QB_VERSION}/            (unpacked; nested quickbuild-X/quickbuild-X/ also accepted)
#   2. environment/quickbuild-${QB_VERSION}.zip         (local zip, verified against QB_DOWNLOAD_SHA256)
#   3. ${QB_DOWNLOAD_URL}                               (downloaded, verified against QB_DOWNLOAD_SHA256)
# When overriding QB_VERSION/QB_DOWNLOAD_URL, also pass the matching QB_DOWNLOAD_SHA256
# (or an empty value to skip verification).
#
# NOTE: Only classic-builder Dockerfile features are used (no BuildKit-only syntax).

ARG JDK_IMAGE=eclipse-temurin:21-jdk-noble

# ---- Stage 1: resolve and patch the QuickBuild distribution ----
FROM ${JDK_IMAGE} AS qb-dist

ARG QB_VERSION=16.0.37
ARG QB_DOWNLOAD_URL=https://pmease.com/artifacts/6371/quickbuild-16.0.37.zip
ARG QB_DOWNLOAD_SHA256=bfbc7e5316de80a54cd007b8e2bca3600ed23f8642d7e5e2f4bcfda4d6001240
# Microsoft SQL Server JDBC driver (jre11 build runs on Java 11+), from Maven Central
ARG MSSQL_JDBC_VERSION=13.6.2.jre11
ARG MSSQL_JDBC_SHA256=5fbc0a70fe4d1d563d431a41b23f493d68807571f0bb49db0bb1737e83e9161f

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

COPY environment/ /tmp/qb-env/
COPY qb-server/fetch-quickbuild-dist.sh /tmp/fetch-quickbuild-dist.sh
RUN sh /tmp/fetch-quickbuild-dist.sh /opt/quickbuild

# Replace the bundled (old, jre8) SQL Server JDBC driver in the OSGi libs bundle.
# Jar names must stay versioned (QuickBuild syncs agent libs by file name) and the
# bundle's Bundle-ClassPath must reference the new jar.
RUN set -eu; \
    libs=/opt/quickbuild/plugins/com.pmease.quickbuild.libs; \
    jar="mssql-jdbc-${MSSQL_JDBC_VERSION}.jar"; \
    curl -fSL --retry 3 -o "$libs/$jar" \
        "https://repo1.maven.org/maven2/com/microsoft/sqlserver/mssql-jdbc/${MSSQL_JDBC_VERSION}/${jar}"; \
    if [ -n "$MSSQL_JDBC_SHA256" ]; then \
        echo "${MSSQL_JDBC_SHA256}  ${libs}/${jar}" | sha256sum -c -; \
    else \
        echo "WARNING: MSSQL_JDBC_SHA256 is empty; skipping checksum verification"; \
    fi; \
    for old in "$libs"/mssql-jdbc-*.jar; do [ "$old" = "$libs/$jar" ] || rm -f "$old"; done; \
    sed -i -E "s#mssql-jdbc-[^,[:space:]]+\.jar#${jar}#" "$libs/META-INF/MANIFEST.MF"; \
    grep -q " ${jar}" "$libs/META-INF/MANIFEST.MF"; \
    echo "Installed SQL Server JDBC driver ${jar}"

# Keep a pristine copy of the shipped conf/ so the entrypoint can seed and refresh the data volume
RUN cp -a /opt/quickbuild/conf /opt/quickbuild/conf.dist

# ---- Stage 2: runtime image ----
FROM ${JDK_IMAGE}

ARG QB_VERSION=16.0.37

# Metadata
LABEL maintainer="QuickBuild Containerization Project"
LABEL description="QuickBuild ${QB_VERSION} Server with Microsoft SQL Server support"
LABEL version="${QB_VERSION}"

# Install required packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    unzip \
    gettext-base \
    netcat-openbsd \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Create quickbuild user (UID/GID 1000 for consistency).
# Ubuntu 24.04 images ship a default "ubuntu" user that already owns UID/GID 1000.
RUN if id -u ubuntu >/dev/null 2>&1; then userdel --remove ubuntu 2>/dev/null; fi && \
    groupadd -r quickbuild --gid=1000 && \
    useradd -r -g quickbuild --uid=1000 --home-dir=/opt/quickbuild --shell=/bin/bash quickbuild

# QuickBuild installation (resolved in stage 1)
COPY --from=qb-dist --chown=1000:1000 /opt/quickbuild/ /opt/quickbuild/

# Configuration templates and container scripts
COPY qb-server/hibernate.properties.template /opt/quickbuild/templates/
COPY qb-server/entrypoint.sh /opt/quickbuild/
COPY qb-server/healthcheck.sh /opt/quickbuild/

# Data volume mount point, and the global storage directory, which QuickBuild requires to be
# outside its install directory (enter QB_STORAGE_DIR in the first-run setup wizard).
RUN mkdir -p /opt/quickbuild/data /var/lib/quickbuild/storage && \
    chown -R quickbuild:quickbuild /opt/quickbuild/data /opt/quickbuild/templates \
        /opt/quickbuild/entrypoint.sh /opt/quickbuild/healthcheck.sh /var/lib/quickbuild && \
    chmod +x /opt/quickbuild/entrypoint.sh /opt/quickbuild/healthcheck.sh && \
    chmod 644 /opt/quickbuild/templates/*.template

# Set environment variables
ENV QB_HOME=/opt/quickbuild
ENV QB_VERSION=${QB_VERSION}
ENV QB_STORAGE_DIR=/var/lib/quickbuild/storage
ENV PATH=$PATH:$QB_HOME/bin

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
HEALTHCHECK --interval=30s --timeout=15s --start-period=180s --retries=3 \
    CMD /opt/quickbuild/healthcheck.sh

# Switch to quickbuild user
USER quickbuild

# Set working directory
WORKDIR /opt/quickbuild

# Use custom entrypoint
ENTRYPOINT ["/opt/quickbuild/entrypoint.sh"]
