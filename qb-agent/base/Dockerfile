# QuickBuild 16 Base Agent Container
# Base: Eclipse Temurin JDK 21 on Ubuntu 24.04 (QuickBuild 15+ requires Java 11+; QB 16 supports up to Java 25)
# Security: Non-root user execution (qbagent UID 1001)
# Purpose: Foundation for specialized agent images
#
# Build agent package source (first match wins):
#   1. qb-agent/base/quickbuild-agent/   an extracted buildagent package downloaded from the
#                                        server's Grid page (http://<server>:8810/download/buildagent.tar.gz)
#   2. Assembled from the QuickBuild server distribution, exactly like the server's own
#      agent download (see qb-server/fetch-quickbuild-dist.sh for local copy / download rules)
#
# NOTE: Only classic-builder Dockerfile features are used (no BuildKit-only syntax).

ARG JDK_IMAGE=eclipse-temurin:21-jdk-noble

# ---- Stage 1: assemble the build agent package ----
FROM ${JDK_IMAGE} AS qb-agent-dist

ARG QB_VERSION=16.0.37
ARG QB_DOWNLOAD_URL=https://pmease.com/artifacts/6371/quickbuild-16.0.37.zip
ARG QB_DOWNLOAD_SHA256=bfbc7e5316de80a54cd007b8e2bca3600ed23f8642d7e5e2f4bcfda4d6001240

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

COPY environment/ /tmp/qb-env/
COPY qb-agent/base/ /tmp/qb-agent-src/
COPY qb-server/fetch-quickbuild-dist.sh /tmp/fetch-quickbuild-dist.sh

RUN set -eu; \
    agent=/opt/qb-agent; \
    if [ -f /tmp/qb-agent-src/quickbuild-agent/bin/agent.sh ]; then \
        echo "Using extracted agent package from qb-agent/base/quickbuild-agent/"; \
        mkdir -p "$agent"; \
        cp -a /tmp/qb-agent-src/quickbuild-agent/. "$agent"/; \
    else \
        sh /tmp/fetch-quickbuild-dist.sh /tmp/qb-dist; \
        dist=/tmp/qb-dist; \
        mkdir -p "$agent/asset" "$agent/bin" "$agent/conf" "$agent/logs" "$agent/plugins"; \
        cp -a "$dist/asset/release" "$agent/asset/"; \
        cp -a "$dist"/bin/*wrapper* "$agent/bin/"; \
        cp -a "$dist"/agent/buildagent/agent.sh "$dist"/agent/buildagent/agent.bat \
              "$dist"/agent/config.sh "$dist"/agent/config.bat "$agent/bin/"; \
        cp -a "$dist/agent/buildagent/wrapper.conf" "$agent/conf/wrapper.conf"; \
        cp -a "$dist/conf/wrapper-license.conf" "$dist/conf/log4j2.xml" "$dist/conf/attributes.properties" "$agent/conf/"; \
        cp -a "$dist/plugins/com.pmease.quickbuild.bootstrap" "$agent/plugins/"; \
        rm -f "$agent/plugins/com.pmease.quickbuild.bootstrap/javadoc.zip"; \
        rm -rf "$dist"; \
    fi; \
    touch "$agent/logs/console.log"; \
    chmod +x "$agent"/bin/*.sh "$agent"/bin/wrapper-linux-*; \
    grep -q "^version=${QB_VERSION}$" "$agent/asset/release" || \
        echo "WARNING: agent package version differs from QB_VERSION=${QB_VERSION}: $(grep '^version=' "$agent/asset/release")"

# ---- Stage 2: runtime image ----
FROM ${JDK_IMAGE}

ARG QB_VERSION=16.0.37

# Metadata
LABEL maintainer="QuickBuild Containerization Project"
LABEL description="QuickBuild ${QB_VERSION} Base Build Agent"
LABEL version="${QB_VERSION}"

# Install required packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    wget \
    unzip \
    git \
    gettext-base \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Create qbagent user (UID 1001 for consistency)
RUN groupadd -r qbagent --gid=1001 && \
    useradd -r -g qbagent --uid=1001 --home-dir=/opt/qb-agent --shell=/bin/bash qbagent

# Copy the assembled build agent package and the container entrypoint
COPY --from=qb-agent-dist --chown=1001:1001 /opt/qb-agent/ /opt/qb-agent/
COPY --chown=1001:1001 qb-agent/base/agent-entrypoint.sh /opt/qb-agent/
RUN chmod +x /opt/qb-agent/agent-entrypoint.sh

# Set environment variables
ENV QB_AGENT_HOME=/opt/qb-agent
ENV QB_VERSION=${QB_VERSION}
ENV PATH=$PATH:$QB_AGENT_HOME/bin

# Default environment variables (can be overridden)
ENV QB_SERVER_URL=http://qb-server:8810
ENV AGENT_PORT=8811
ENV AGENT_NAME=""

# Expose agent port
EXPOSE 8811

# Configure health check (the Java Service Wrapper launches WrapperStartStopApp)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD pgrep -f "WrapperStartStopApp" > /dev/null || exit 1

# Switch to qbagent user
USER qbagent

# Set working directory
WORKDIR /opt/qb-agent

# Use custom entrypoint
ENTRYPOINT ["/opt/qb-agent/agent-entrypoint.sh"]
