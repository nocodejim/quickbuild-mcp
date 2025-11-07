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
    echo '# NPM Configuration for QuickBuild Agent' > /opt/qb-agent/.npmrc && \
    echo 'cache=/opt/qb-agent/.npm' >> /opt/qb-agent/.npmrc && \
    echo 'prefix=/opt/qb-agent/.npm-global' >> /opt/qb-agent/.npmrc && \
    echo 'init-author-name=QuickBuild Agent' >> /opt/qb-agent/.npmrc && \
    echo 'init-license=MIT' >> /opt/qb-agent/.npmrc && \
    echo 'save-exact=true' >> /opt/qb-agent/.npmrc && \
    echo 'engine-strict=true' >> /opt/qb-agent/.npmrc && \
    echo 'fund=false' >> /opt/qb-agent/.npmrc && \
    echo 'audit-level=moderate' >> /opt/qb-agent/.npmrc

# Set up npm global directory
ENV PATH=/opt/qb-agent/.npm-global/bin:$PATH

# Create entrypoint script that sources NVM
RUN echo '#!/bin/bash' > /opt/qb-agent/node-entrypoint.sh && \
    echo '# Node.js Agent Entrypoint - sources NVM and starts agent' >> /opt/qb-agent/node-entrypoint.sh && \
    echo '' >> /opt/qb-agent/node-entrypoint.sh && \
    echo '# Source NVM' >> /opt/qb-agent/node-entrypoint.sh && \
    echo 'export NVM_DIR="/opt/qb-agent/.nvm"' >> /opt/qb-agent/node-entrypoint.sh && \
    echo '[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"' >> /opt/qb-agent/node-entrypoint.sh && \
    echo '[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"' >> /opt/qb-agent/node-entrypoint.sh && \
    echo '' >> /opt/qb-agent/node-entrypoint.sh && \
    echo '# Use default Node version' >> /opt/qb-agent/node-entrypoint.sh && \
    echo 'nvm use default' >> /opt/qb-agent/node-entrypoint.sh && \
    echo '' >> /opt/qb-agent/node-entrypoint.sh && \
    echo '# Display Node.js information' >> /opt/qb-agent/node-entrypoint.sh && \
    echo 'echo "Node.js Version: $(node --version)"' >> /opt/qb-agent/node-entrypoint.sh && \
    echo 'echo "NPM Version: $(npm --version)"' >> /opt/qb-agent/node-entrypoint.sh && \
    echo 'echo "Yarn Version: $(yarn --version)"' >> /opt/qb-agent/node-entrypoint.sh && \
    echo '' >> /opt/qb-agent/node-entrypoint.sh && \
    echo '# Call original agent entrypoint' >> /opt/qb-agent/node-entrypoint.sh && \
    echo 'exec /opt/qb-agent/agent-entrypoint.sh "$@"' >> /opt/qb-agent/node-entrypoint.sh

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