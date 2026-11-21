# QuickBuild 16 .NET Agent Container
# Base: QB Base Agent (Ubuntu 24.04) + .NET SDK 10.0 LTS
# Purpose: .NET build capabilities
# Build qb-agent-base first: docker compose build qb-agent-base

ARG BASE_IMAGE=qb-agent-base:latest
ARG DOTNET_SDK_IMAGE=mcr.microsoft.com/dotnet/sdk:10.0-noble

# .NET SDK from Microsoft's official Ubuntu 24.04 image (no apt repository setup needed)
FROM ${DOTNET_SDK_IMAGE} AS dotnet-sdk

FROM ${BASE_IMAGE}

# Metadata
LABEL maintainer="QuickBuild Containerization Project"
LABEL description="QuickBuild 16 .NET Build Agent"
LABEL version="16.0"
LABEL toolchain="dotnet"

# Switch to root for installation
USER root

# Install .NET runtime dependencies (Ubuntu 24.04 package names)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libc6 \
    libgcc-s1 \
    libgssapi-krb5-2 \
    libicu74 \
    libssl3t64 \
    libstdc++6 \
    tzdata \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

# Install .NET SDK 10.0
ENV DOTNET_VERSION=10.0
COPY --from=dotnet-sdk /usr/share/dotnet /usr/share/dotnet
RUN ln -sf /usr/share/dotnet/dotnet /usr/bin/dotnet

# Set .NET environment variables
ENV DOTNET_ROOT=/usr/share/dotnet
ENV PATH=$PATH:$DOTNET_ROOT:$DOTNET_ROOT/tools
ENV DOTNET_CLI_TELEMETRY_OPTOUT=1
ENV DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
ENV DOTNET_NOLOGO=1

# Create .NET configuration directory
RUN mkdir -p /opt/qb-agent/.dotnet && \
    chown -R qbagent:qbagent /opt/qb-agent/.dotnet

# Switch to qbagent user
USER qbagent

# Set .NET user-specific environment
ENV DOTNET_CLI_HOME=/opt/qb-agent/.dotnet
ENV NUGET_PACKAGES=/opt/qb-agent/.nuget/packages

# Create NuGet configuration
RUN mkdir -p /opt/qb-agent/.nuget
COPY --chown=qbagent:qbagent ./qb-agent/dotnet/config/NuGet.Config /opt/qb-agent/.nuget/NuGet.Config

# Install common .NET tools
RUN dotnet tool install --global dotnet-ef && \
    dotnet tool install --global dotnet-aspnet-codegenerator && \
    dotnet tool install --global dotnet-reportgenerator-globaltool

# Update PATH for .NET tools
ENV PATH=$PATH:/opt/qb-agent/.dotnet/tools

# Pre-warm .NET by creating and building a sample project
RUN cd /tmp && \
    dotnet new console -n SampleApp && \
    cd SampleApp && \
    dotnet build && \
    dotnet run && \
    cd / && \
    rm -rf /tmp/SampleApp

# Create global.json for consistent SDK version
COPY --chown=qbagent:qbagent ./qb-agent/dotnet/config/global.json /opt/qb-agent/global.json

# Create .NET-specific entrypoint script
COPY --chown=qbagent:qbagent ./qb-agent/dotnet/config/dotnet-entrypoint.sh /opt/qb-agent/dotnet-entrypoint.sh
RUN chmod 755 /opt/qb-agent/dotnet-entrypoint.sh

# Verify .NET installation
RUN dotnet --version && \
    dotnet --list-sdks && \
    dotnet --list-runtimes

WORKDIR /opt/qb-agent

# Use .NET-specific entrypoint
ENTRYPOINT ["/opt/qb-agent/dotnet-entrypoint.sh"]
