# QuickBuild 14 Maven Agent Container
# Base: QB Base Agent + Apache Maven 3.8.x
# Purpose: Java/Maven build capabilities

FROM qb-agent-base:latest

# Metadata
LABEL maintainer="QuickBuild Containerization Project"
LABEL description="QuickBuild 14 Maven Build Agent"
LABEL version="14.0"
LABEL toolchain="maven"

# Switch to root for installation
USER root

# Install Maven
ENV MAVEN_VERSION=3.8.8
ENV MAVEN_HOME=/opt/maven
ENV PATH=$PATH:$MAVEN_HOME/bin

RUN echo "Installing Apache Maven ${MAVEN_VERSION}..." && \
    wget -q "https://archive.apache.org/dist/maven/maven-3/${MAVEN_VERSION}/binaries/apache-maven-${MAVEN_VERSION}-bin.tar.gz" -O /tmp/maven.tar.gz && \
    mkdir -p $MAVEN_HOME && \
    tar -xzf /tmp/maven.tar.gz -C $MAVEN_HOME --strip-components=1 && \
    rm /tmp/maven.tar.gz && \
    echo "✓ Maven installed successfully"

# Install additional build tools commonly used with Maven
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create Maven local repository directory
RUN mkdir -p /opt/qb-agent/.m2 && \
    chown -R qbagent:qbagent /opt/qb-agent/.m2

# Create Maven settings.xml with optimized configuration
RUN mkdir -p /opt/qb-agent/.m2 && \
    cat > /opt/qb-agent/.m2/settings.xml << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.0.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.0.0 
                              http://maven.apache.org/xsd/settings-1.0.0.xsd">
  
  <!-- Local repository path -->
  <localRepository>/opt/qb-agent/.m2/repository</localRepository>
  
  <!-- Offline mode -->
  <offline>false</offline>
  
  <!-- Plugin groups -->
  <pluginGroups>
    <pluginGroup>org.apache.maven.plugins</pluginGroup>
    <pluginGroup>org.codehaus.mojo</pluginGroup>
  </pluginGroups>
  
  <!-- Profiles for different environments -->
  <profiles>
    <profile>
      <id>quickbuild</id>
      <properties>
        <maven.compiler.source>8</maven.compiler.source>
        <maven.compiler.target>8</maven.compiler.target>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
      </properties>
    </profile>
  </profiles>
  
  <!-- Active profiles -->
  <activeProfiles>
    <activeProfile>quickbuild</activeProfile>
  </activeProfiles>
  
</settings>
EOF

# Set proper ownership
RUN chown -R qbagent:qbagent /opt/qb-agent/.m2

# Verify Maven installation
RUN mvn --version

# Switch back to qbagent user
USER qbagent

# Set Maven-specific environment variables
ENV M2_HOME=$MAVEN_HOME
ENV MAVEN_OPTS="-Xmx1024m -XX:MaxPermSize=256m"

# Pre-download common Maven plugins to speed up builds
RUN cd /tmp && \
    mvn archetype:generate \
        -DgroupId=com.example \
        -DartifactId=test-project \
        -DarchetypeArtifactId=maven-archetype-quickstart \
        -DinteractiveMode=false && \
    cd test-project && \
    mvn compile && \
    cd / && \
    rm -rf /tmp/test-project

WORKDIR /opt/qb-agent