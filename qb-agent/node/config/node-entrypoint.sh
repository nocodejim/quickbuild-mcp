#!/bin/bash
# Node.js Agent Entrypoint - sources NVM and starts agent

# Source NVM
export NVM_DIR="/opt/qb-agent/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"

# Use default Node version
nvm use default

# Display Node.js information
echo "Node.js Version: $(node --version)"
echo "NPM Version: $(npm --version)"
echo "Yarn Version: $(yarn --version)"

# Call original agent entrypoint
exec /opt/qb-agent/agent-entrypoint.sh "$@"
