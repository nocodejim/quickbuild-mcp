# QuickBuild 14 Base Agent Container
# Base: Eclipse Temurin JDK 8 (required for QB 14)
# Security: Non-root user execution (qbagent UID 1001)
# Purpose: Foundation for specialized agent images

FROM eclipse-temurin:8-jdk-focal

# Metadata
LABEL maintainer="QuickBuild Containerization Project"
LABEL description="QuickBuild 14 Base Build Agent"
LABEL version="14.0"

# Install required packages
RUN apt-get update && apt-get install -y \
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

# Set QuickBuild version and download URL
ENV QB_VERSION=14.0.11
ENV QB_AGENT_DOWNLOAD_URL=https://www.pmease.com/quickbuild/downloads/quickbuild-${QB_VERSION}.zip

# Create directories
RUN mkdir -p /opt/qb-agent /opt/qb-agent/conf /tmp/qb-install

# Copy real QuickBuild 14.0.32 agent installation
COPY quickbuild-agent/ /opt/qb-agent/

# Copy agent entrypoint script
COPY agent-entrypoint.sh /opt/qb-agent/

# Set proper permissions
RUN chown -R qbagent:qbagent /opt/qb-agent && \
    chmod +x /opt/qb-agent/agent-entrypoint.sh && \
    chmod +x /opt/qb-agent/agent.sh 2>/dev/null || true

# Set environment variables
ENV QB_AGENT_HOME=/opt/qb-agent
ENV JAVA_HOME=/opt/java/openjdk
ENV PATH=$PATH:$QB_AGENT_HOME/bin:$JAVA_HOME/bin

# Default environment variables (can be overridden)
ENV QB_SERVER_URL=http://qb-server:8810
ENV AGENT_PORT=8811
ENV AGENT_NAME=""

# Expose agent port
EXPOSE 8811

# Configure health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD pgrep -f "agent.sh" > /dev/null || exit 1

# Switch to qbagent user
USER qbagent

# Set working directory
WORKDIR /opt/qb-agent

# Use custom entrypoint
ENTRYPOINT ["/opt/qb-agent/agent-entrypoint.sh"]