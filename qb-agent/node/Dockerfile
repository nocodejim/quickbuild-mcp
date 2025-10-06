# QuickBuild 14 Node.js Agent Container
# Base: QB Base Agent + Node.js 16.x via NVM
# Purpose: Node.js/npm/yarn build capabilities

FROM qb-agent-base:latest

# Metadata
LABEL maintainer="QuickBuild Containerization Project"
LABEL description="QuickBuild 14 Node.js Build Agent"
LABEL version="14.0"
LABEL toolchain="nodejs"

# Switch to root for installation
USER root

# Install Node.js dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Switch to qbagent user for NVM installation
USER qbagent

# Install NVM (Node Version Manager)
ENV NVM_VERSION=v0.39.0
ENV NODE_VERSION=16.20.2
ENV NVM_DIR=/opt/qb-agent/.nvm

RUN echo "Installing NVM ${NVM_VERSION}..." && \
    curl -o- "https://raw.githubusercontent.com/nvm-sh/nvm/${NVM_VERSION}/install.sh" | bash && \
    echo "✓ NVM installed successfully"

# Install Node.js via NVM
RUN bash -c "source $NVM_DIR/nvm.sh && \
    echo 'Installing Node.js ${NODE_VERSION}...' && \
    nvm install ${NODE_VERSION} && \
    nvm use ${NODE_VERSION} && \
    nvm alias default ${NODE_VERSION} && \
    echo '✓ Node.js installed successfully'"

# Set up Node.js environment
ENV PATH=$NVM_DIR/versions/node/v$NODE_VERSION/bin:$PATH
ENV NODE_PATH=$NVM_DIR/versions/node/v$NODE_VERSION/lib/node_modules

# Create .nvmrc file for consistent Node version
RUN echo "${NODE_VERSION}" > /opt/qb-agent/.nvmrc

# Install Yarn package manager
RUN bash -c "source $NVM_DIR/nvm.sh && \
    nvm use ${NODE_VERSION} && \
    echo 'Installing Yarn...' && \
    npm install -g yarn && \
    echo '✓ Yarn installed successfully'"

# Install common global packages
RUN bash -c "source $NVM_DIR/nvm.sh && \
    nvm use ${NODE_VERSION} && \
    echo 'Installing common global packages...' && \
    npm install -g \
        typescript \
        @angular/cli \
        @vue/cli \
        create-react-app \
        eslint \
        prettier \
        jest \
        webpack \
        webpack-cli && \
    echo '✓ Global packages installed successfully'"

# Create npm configuration for optimized builds
RUN mkdir -p /opt/qb-agent/.npm && \
    cat > /opt/qb-agent/.npmrc << 'EOF'
# NPM Configuration for QuickBuild Agent
cache=/opt/qb-agent/.npm
prefix=/opt/qb-agent/.npm-global
init-author-name=QuickBuild Agent
init-license=MIT
save-exact=true
engine-strict=true
fund=false
audit-level=moderate
EOF

# Set up npm global directory
ENV PATH=/opt/qb-agent/.npm-global/bin:$PATH

# Create entrypoint script that sources NVM
RUN cat > /opt/qb-agent/node-entrypoint.sh << 'EOF'
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
EOF

RUN chmod +x /opt/qb-agent/node-entrypoint.sh

# Verify installations
RUN bash -c "source $NVM_DIR/nvm.sh && \
    nvm use ${NODE_VERSION} && \
    node --version && \
    npm --version && \
    yarn --version"

WORKDIR /opt/qb-agent

# Use Node.js-specific entrypoint
ENTRYPOINT ["/opt/qb-agent/node-entrypoint.sh"]