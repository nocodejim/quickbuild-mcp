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
