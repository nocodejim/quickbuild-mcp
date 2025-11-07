# QuickBuild 14 .NET Agent Container
# Base: QB Base Agent + .NET SDK 6.0
# Purpose: .NET Core/Framework build capabilities

FROM qb-agent-base:latest

# Metadata
LABEL maintainer="QuickBuild Containerization Project"
LABEL description="QuickBuild 14 .NET Build Agent"
LABEL version="14.0"
LABEL toolchain="dotnet"

# Switch to root for installation
USER root

# Install .NET SDK dependencies
RUN apt-get update && apt-get install -y \
    libc6 \
    libgcc1 \
    libgssapi-krb5-2 \
    libicu66 \
    libssl1.1 \
    libstdc++6 \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

# Install Microsoft package repository
RUN wget https://packages.microsoft.com/config/ubuntu/20.04/packages-microsoft-prod.deb -O packages-microsoft-prod.deb && \
    dpkg -i packages-microsoft-prod.deb && \
    rm packages-microsoft-prod.deb

# Install .NET SDK 6.0
ENV DOTNET_VERSION=6.0
RUN apt-get update && \
    apt-get install -y dotnet-sdk-6.0 && \
    rm -rf /var/lib/apt/lists/*

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
RUN mkdir -p /opt/qb-agent/.nuget && \
    cat > /opt/qb-agent/.nuget/NuGet.Config << 'EOF'
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <packageSources>
    <add key="nuget.org" value="https://api.nuget.org/v3/index.json" protocolVersion="3" />
  </packageSources>
  <config>
    <add key="globalPackagesFolder" value="/opt/qb-agent/.nuget/packages" />
    <add key="repositoryPath" value="/opt/qb-agent/.nuget/packages" />
  </config>
</configuration>
EOF

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
RUN cat > /opt/qb-agent/global.json << 'EOF'
{
  "sdk": {
    "version": "6.0.0",
    "rollForward": "latestMinor"
  }
}
EOF

# Create .NET-specific entrypoint script
RUN cat > /opt/qb-agent/dotnet-entrypoint.sh << 'EOF'
#!/bin/bash
# .NET Agent Entrypoint - sets up .NET environment and starts agent

# Display .NET information
echo ".NET SDK Version: $(dotnet --version)"
echo ".NET Runtime Versions:"
dotnet --list-runtimes
echo ".NET SDK Versions:"
dotnet --list-sdks

# Set up .NET environment
export DOTNET_CLI_HOME=/opt/qb-agent/.dotnet
export NUGET_PACKAGES=/opt/qb-agent/.nuget/packages

# Call original agent entrypoint
exec /opt/qb-agent/agent-entrypoint.sh "$@"
EOF

RUN chmod +x /opt/qb-agent/dotnet-entrypoint.sh

# Verify .NET installation
RUN dotnet --version && \
    dotnet --list-sdks && \
    dotnet --list-runtimes

WORKDIR /opt/qb-agent

# Use .NET-specific entrypoint
ENTRYPOINT ["/opt/qb-agent/dotnet-entrypoint.sh"]