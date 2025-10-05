# QuickBuild 14 Deployment Guide

This guide provides detailed deployment procedures for QuickBuild 14 containerization solution in both Docker Compose and Kubernetes environments.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Docker Compose Deployment](#docker-compose-deployment)
- [Kubernetes Deployment](#kubernetes-deployment)
- [Initial Setup](#initial-setup)
- [Validation](#validation)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### System Requirements

- **CPU:** 4+ cores recommended
- **Memory:** 8GB+ RAM (16GB+ for production)
- **Storage:** 50GB+ available disk space
- **Network:** Internet access for image downloads

### Software Requirements

#### For Docker Compose
- Docker Engine 20.10+
- Docker Compose 2.0+
- Git
- curl (for validation scripts)

#### For Kubernetes
- Kubernetes cluster 1.20+
- kubectl configured for your cluster
- Helm 3.0+ (optional, for advanced deployments)
- Storage class supporting ReadWriteOnce and ReadWriteMany

### Network Requirements

- Port 8810: QuickBuild web interface
- Port 1433: SQL Server (internal only)
- Port 8811: Build agents (internal only)

## Docker Compose Deployment

### Development Environment

Perfect for development, testing, and small teams.

#### 1. Environment Setup

```bash
# Clone repository
git clone <repository-url>
cd quickbuild14-containerization

# Configure environment
cp .env.example .env
```

#### 2. Configure Passwords

Edit `.env` file with strong passwords:

```bash
# Required: Set strong passwords
MSSQL_SA_PASSWORD=YourStrongSAPassword123!
QB_DB_PASSWORD=YourStrongQBPassword123!

# Optional: Customize other settings
COMPOSE_PROJECT_NAME=quickbuild14
QB_SERVER_PORT=8810
```

#### 3. Deploy Development Stack

```bash
# Start with development configuration
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Check status
docker-compose ps
```

#### 4. Validate Deployment

```bash
# Run validation script
./scripts/validate-deployment.sh -e docker-compose

# Check QuickBuild is accessible
curl -f http://localhost:8810
```

### Production Environment

For production deployments with enhanced security and performance.

#### 1. Create Secrets

```bash
# Create secrets directory
mkdir -p secrets

# Generate strong passwords
echo "YourProductionSAPassword123!" > secrets/mssql_sa_password.txt
echo "YourProductionQBPassword123!" > secrets/qb_db_password.txt

# Set proper permissions
chmod 600 secrets/*.txt
```

#### 2. Configure Production Environment

```bash
# Use production configuration
cp .env.example .env

# Edit .env for production
QB_ENABLE_TLS=true
BACKUP_RETENTION_DAYS=30
QB_LOG_LEVEL=WARN
```

#### 3. Deploy Production Stack

```bash
# Start with production configuration
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Verify all services are healthy
docker-compose ps
./scripts/validate-deployment.sh -e docker-compose
```

## Kubernetes Deployment

### Cluster Preparation

#### 1. Verify Cluster Access

```bash
# Check cluster connectivity
kubectl cluster-info

# Verify storage classes
kubectl get storageclass

# Check available resources
kubectl top nodes
```

#### 2. Create Namespace

```bash
# Apply namespace and RBAC
kubectl apply -f kubernetes/namespace.yaml
kubectl apply -f kubernetes/rbac.yaml
```

### Configuration Setup

#### 1. Create Secrets

```bash
# Create database secrets
kubectl create secret generic quickbuild-database-secrets \
  --from-literal=SA_PASSWORD='YourStrongSAPassword123!' \
  --from-literal=QB_DB_PASSWORD='YourStrongQBPassword123!' \
  -n quickbuild

# Create TLS secrets (if using HTTPS)
kubectl create secret tls quickbuild-tls-secrets \
  --cert=path/to/tls.crt \
  --key=path/to/tls.key \
  -n quickbuild
```

#### 2. Apply Configuration

```bash
# Apply ConfigMaps and remaining secrets
kubectl apply -f kubernetes/configmap.yaml
kubectl apply -f kubernetes/secrets.yaml  # Template only, customize first
```

### Storage Setup

#### 1. Create Persistent Volumes

```bash
# Apply PVC definitions
kubectl apply -f kubernetes/pvc.yaml

# Verify PVCs are bound
kubectl get pvc -n quickbuild
```

### Application Deployment

#### 1. Deploy Database

```bash
# Deploy SQL Server StatefulSet
kubectl apply -f kubernetes/mssql-statefulset.yaml
kubectl apply -f kubernetes/mssql-service.yaml

# Wait for database to be ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/component=database -n quickbuild --timeout=300s
```

#### 2. Deploy QuickBuild Server

```bash
# Deploy server StatefulSet
kubectl apply -f kubernetes/qb-server-statefulset.yaml
kubectl apply -f kubernetes/qb-server-service.yaml

# Wait for server to be ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/component=server -n quickbuild --timeout=600s
```

#### 3. Deploy Build Agents

```bash
# Deploy all agent types
kubectl apply -f kubernetes/qb-agents-deployment.yaml

# Verify agents are running
kubectl get pods -n quickbuild -l app.kubernetes.io/component=agent
```

#### 4. Configure External Access

```bash
# Apply ingress configuration (customize domain first)
kubectl apply -f kubernetes/ingress.yaml

# Or use port forwarding for testing
kubectl port-forward service/qb-server-service 8810:8810 -n quickbuild
```

## Initial Setup

### First-Time Configuration

#### 1. Access QuickBuild

- **Docker Compose:** http://localhost:8810
- **Kubernetes:** http://your-domain.com or via port-forward

#### 2. Initial Login

- **Username:** admin
- **Password:** admin
- **⚠️ Change immediately after first login**

#### 3. Basic Configuration

1. **Change Admin Password**
2. **Configure System Settings**
3. **Verify Agent Connectivity**
4. **Create First Build Configuration**

## Validation

### Automated Validation

```bash
# Complete system validation
./scripts/validate-deployment.sh -e <environment>

# Component-specific health checks
./scripts/health-check.sh all
```

### Manual Validation Checklist

- [ ] All containers/pods are running
- [ ] Database is accessible and initialized
- [ ] QuickBuild web interface loads
- [ ] Build agents are connected
- [ ] Can create and run a test build

## Troubleshooting

### Common Issues

#### Database Connection Issues
```bash
# Check database status
./scripts/health-check.sh database
```

#### Server Startup Issues
```bash
# Check server logs and status
./scripts/validate-deployment.sh -e <environment> --verbose
```

For detailed troubleshooting, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).