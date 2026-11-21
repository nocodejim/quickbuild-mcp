# QuickBuild 16 Maven Agent Container
# Base: QB Base Agent (Eclipse Temurin JDK 21) + Apache Maven 3.9.x
# Purpose: Java/Maven build capabilities
# Build qb-agent-base first: docker compose build qb-agent-base

ARG BASE_IMAGE=qb-agent-base:latest
FROM ${BASE_IMAGE}

# Metadata
LABEL maintainer="QuickBuild Containerization Project"
LABEL description="QuickBuild 16 Maven Build Agent"
LABEL version="16.0"
LABEL toolchain="maven"

# Switch to root for installation
USER root

# Install Maven (checksum-verified)
ARG MAVEN_VERSION=3.9.16
ARG MAVEN_SHA512=831a8591fe20c8243b1dbe7d71e3244f31d1665b0804b2e825e38cbbe5ce0cafb8338851f90780735568773e0a6cd07bbec107cda0b896b008b861075358b6f6
ENV MAVEN_VERSION=${MAVEN_VERSION}
ENV MAVEN_HOME=/opt/maven
ENV PATH=$PATH:$MAVEN_HOME/bin

RUN set -eu; \
    echo "Installing Apache Maven ${MAVEN_VERSION}..."; \
    curl -fSL --retry 3 -o /tmp/maven.tar.gz \
        "https://archive.apache.org/dist/maven/maven-3/${MAVEN_VERSION}/binaries/apache-maven-${MAVEN_VERSION}-bin.tar.gz"; \
    echo "${MAVEN_SHA512}  /tmp/maven.tar.gz" | sha512sum -c -; \
    mkdir -p "$MAVEN_HOME"; \
    tar -xzf /tmp/maven.tar.gz -C "$MAVEN_HOME" --strip-components=1; \
    rm /tmp/maven.tar.gz; \
    echo "✓ Maven installed successfully"

# Install additional build tools commonly used with Maven
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create Maven local repository directory
RUN mkdir -p /opt/qb-agent/.m2 && \
    chown -R qbagent:qbagent /opt/qb-agent/.m2

# Maven settings.xml with optimized configuration (compiles for Java 21 by default)
COPY --chown=qbagent:qbagent ./qb-agent/maven/config/settings.xml /opt/qb-agent/.m2/settings.xml

# Verify Maven installation
RUN mvn --version

# Switch back to qbagent user
USER qbagent

# Set Maven-specific environment variables
ENV M2_HOME=$MAVEN_HOME
ENV MAVEN_OPTS="-Xmx1024m"

# Pre-download common Maven plugins to speed up builds
RUN cd /tmp && \
    mvn -B archetype:generate \
        -DgroupId=com.example \
        -DartifactId=test-project \
        -DarchetypeArtifactId=maven-archetype-quickstart \
        -DarchetypeVersion=1.5 \
        -DinteractiveMode=false && \
    cd test-project && \
    mvn -B compile -Dmaven.compiler.release=21 && \
    cd / && \
    rm -rf /tmp/test-project

WORKDIR /opt/qb-agent
