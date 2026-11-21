# QuickBuild 16 Node.js Agent Container
# Base: QB Base Agent + Node.js 24 LTS via NVM
# Purpose: Node.js/npm/yarn build capabilities
# Build qb-agent-base first: docker compose build qb-agent-base

ARG BASE_IMAGE=qb-agent-base:latest
FROM ${BASE_IMAGE}

# Metadata
LABEL maintainer="QuickBuild Containerization Project"
LABEL description="QuickBuild 16 Node.js Build Agent"
LABEL version="16.0"
LABEL toolchain="nodejs"

# Switch to root for installation
USER root

# Install Node.js dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Switch to qbagent user for NVM installation
USER qbagent

# Install NVM (Node Version Manager). NODE_VERSION must be an exact version (used in PATH).
ARG NVM_VERSION=v0.41.0
ARG NODE_VERSION=24.22.3
ENV NVM_VERSION=${NVM_VERSION}
ENV NODE_VERSION=${NODE_VERSION}
ENV NVM_DIR=/opt/qb-agent/.nvm

RUN set -eu; \
    echo "Installing NVM ${NVM_VERSION}..."; \
    mkdir -p "$NVM_DIR"; \
    curl -fsSL -o /tmp/nvm-install.sh "https://raw.githubusercontent.com/nvm-sh/nvm/${NVM_VERSION}/install.sh"; \
    bash /tmp/nvm-install.sh; \
    rm -f /tmp/nvm-install.sh; \
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

# Install common global packages (deprecated create-react-app and @vue/cli removed)
RUN bash -c "source $NVM_DIR/nvm.sh && \
    nvm use ${NODE_VERSION} && \
    echo 'Installing common global packages...' && \
    npm install -g \
        typescript \
        @angular/cli \
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
COPY --chown=qbagent:qbagent ./qb-agent/node/config/node-entrypoint.sh /opt/qb-agent/node-entrypoint.sh
RUN chmod 755 /opt/qb-agent/node-entrypoint.sh

# Verify installations
RUN bash -c "source $NVM_DIR/nvm.sh && \
    nvm use ${NODE_VERSION} && \
    node --version && \
    npm --version && \
    yarn --version"

WORKDIR /opt/qb-agent

# Use Node.js-specific entrypoint
ENTRYPOINT ["/opt/qb-agent/node-entrypoint.sh"]
