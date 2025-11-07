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
RUN mkdir -p /opt/qb-agent/.npm
COPY --chown=qbagent:qbagent ./qb-agent/node/config/.npmrc /opt/qb-agent/.npmrc

# Set up npm global directory
ENV PATH=/opt/qb-agent/.npm-global/bin:$PATH

# Create entrypoint script that sources NVM
COPY --chown=qbagent:qbagent --chmod=755 ./qb-agent/node/config/node-entrypoint.sh /opt/qb-agent/node-entrypoint.sh

# Verify installations
RUN bash -c "source $NVM_DIR/nvm.sh && \
    nvm use ${NODE_VERSION} && \
    node --version && \
    npm --version && \
    yarn --version"

WORKDIR /opt/qb-agent

# Use Node.js-specific entrypoint
ENTRYPOINT ["/opt/qb-agent/node-entrypoint.sh"]