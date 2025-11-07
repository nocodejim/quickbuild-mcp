# QuickBuild 14 Cloud Deployment Specifications

## Overview
Comprehensive specifications for deploying QuickBuild 14 containers in cloud environments (AWS, Azure, GCP).

## Cloud VM Requirements

### Minimum Specifications
- **CPU**: 4 vCPUs
- **RAM**: 8 GB
- **Storage**: 50 GB SSD
- **OS**: Ubuntu 22.04 LTS or Amazon Linux 2023
- **Network**: Public IP with ports 8810, 1433 accessible

### Recommended Specifications
- **CPU**: 8 vCPUs
- **RAM**: 16 GB
- **Storage**: 100 GB SSD
- **OS**: Ubuntu 22.04 LTS
- **Network**: Load balancer + private subnets

## AWS Deployment

### EC2 Instance Setup
```bash
# Launch EC2 instance (t3.xlarge or larger)
# Security Group: Allow ports 22, 8810, 1433

# Connect and install Docker
sudo yum update -y
sudo yum install -y docker git
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -a -G docker ec2-user

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### RDS Alternative
Instead of containerized database, use AWS RDS:
```bash
# Create RDS SQL Server instance
aws rds create-db-instance \
  --db-instance-identifier quickbuild-db \
  --db-instance-class db.t3.medium \
  --engine sqlserver-ex \
  --master-username admin \
  --master-user-password YourSecurePassword123! \
  --allocated-storage 100 \
  --vpc-security-group-ids sg-xxxxxxxxx
```

### ECS Deployment
```yaml
# ecs-task-definition.json
{
  "family": "quickbuild-server",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "2048",
  "memory": "4096",
  "containerDefinitions": [
    {
      "name": "quickbuild-server",
      "image": "your-account.dkr.ecr.region.amazonaws.com/quickbuild-server:latest",
      "portMappings": [
        {
          "containerPort": 8810,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "QB_DB_HOST",
          "value": "your-rds-endpoint.region.rds.amazonaws.com"
        }
      ]
    }
  ]
}
```

## Azure Deployment

### Azure Container Instances
```bash
# Create resource group
az group create --name quickbuild-rg --location eastus

# Create SQL Database
az sql server create \
  --name quickbuild-sql-server \
  --resource-group quickbuild-rg \
  --location eastus \
  --admin-user qbadmin \
  --admin-password YourSecurePassword123!

az sql db create \
  --resource-group quickbuild-rg \
  --server quickbuild-sql-server \
  --name quickbuild \
  --service-objective Basic

# Deploy container
az container create \
  --resource-group quickbuild-rg \
  --name quickbuild-server \
  --image your-registry/quickbuild-server:latest \
  --cpu 4 \
  --memory 8 \
  --ports 8810 \
  --environment-variables \
    QB_DB_HOST=quickbuild-sql-server.database.windows.net \
    QB_DB_NAME=quickbuild \
    QB_DB_USER=qbadmin \
    QB_DB_PASSWORD=YourSecurePassword123!
```

### Azure Kubernetes Service (AKS)
```yaml
# quickbuild-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: quickbuild-server
spec:
  replicas: 1
  selector:
    matchLabels:
      app: quickbuild-server
  template:
    metadata:
      labels:
        app: quickbuild-server
    spec:
      containers:
      - name: quickbuild-server
        image: your-registry/quickbuild-server:latest
        ports:
        - containerPort: 8810
        env:
        - name: QB_DB_HOST
          value: "quickbuild-sql-server.database.windows.net"
        resources:
          requests:
            memory: "4Gi"
            cpu: "2"
          limits:
            memory: "8Gi"
            cpu: "4"
```

## Google Cloud Platform (GCP)

### Compute Engine Setup
```bash
# Create VM instance
gcloud compute instances create quickbuild-vm \
  --zone=us-central1-a \
  --machine-type=e2-standard-4 \
  --boot-disk-size=100GB \
  --boot-disk-type=pd-ssd \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --tags=quickbuild-server

# Configure firewall
gcloud compute firewall-rules create allow-quickbuild \
  --allow tcp:8810,tcp:1433 \
  --source-ranges 0.0.0.0/0 \
  --target-tags quickbuild-server
```

### Cloud SQL Setup
```bash
# Create Cloud SQL instance
gcloud sql instances create quickbuild-db \
  --database-version=SQLSERVER_2019_STANDARD \
  --tier=db-custom-2-8192 \
  --region=us-central1 \
  --root-password=YourSecurePassword123!

# Create database
gcloud sql databases create quickbuild --instance=quickbuild-db
```

### Google Kubernetes Engine (GKE)
```bash
# Create GKE cluster
gcloud container clusters create quickbuild-cluster \
  --zone=us-central1-a \
  --num-nodes=2 \
  --machine-type=e2-standard-4

# Deploy application
kubectl apply -f kubernetes/
```

## Docker Registry Setup

### AWS ECR
```bash
# Create repository
aws ecr create-repository --repository-name quickbuild-server

# Build and push
docker build -t quickbuild-server ./qb-server
docker tag quickbuild-server:latest 123456789012.dkr.ecr.us-east-1.amazonaws.com/quickbuild-server:latest
docker push 123456789012.dkr.ecr.us-east-1.amazonaws.com/quickbuild-server:latest
```

### Azure Container Registry
```bash
# Create registry
az acr create --resource-group quickbuild-rg --name quickbuildregistry --sku Basic

# Build and push
az acr build --registry quickbuildregistry --image quickbuild-server:latest ./qb-server
```

### Google Container Registry
```bash
# Configure Docker
gcloud auth configure-docker

# Build and push
docker build -t gcr.io/your-project-id/quickbuild-server:latest ./qb-server
docker push gcr.io/your-project-id/quickbuild-server:latest
```

## Environment Configuration

### Production Environment Variables
```bash
# Database Configuration
QB_DB_HOST=your-database-host
QB_DB_PORT=1433
QB_DB_NAME=quickbuild
QB_DB_USER=qb_user
QB_DB_PASSWORD=your-secure-password

# Server Configuration
QB_SERVER_PORT=8810
QB_SERVER_URL=https://your-domain.com
QB_LOG_LEVEL=INFO

# Security
QB_ADMIN_PASSWORD=your-admin-password
QB_LICENSE_KEY=your-license-key
```

### SSL/TLS Configuration
```yaml
# nginx-ssl.conf
server {
    listen 443 ssl;
    server_name your-domain.com;
    
    ssl_certificate /etc/ssl/certs/your-cert.pem;
    ssl_certificate_key /etc/ssl/private/your-key.pem;
    
    location / {
        proxy_pass http://localhost:8810;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Monitoring and Logging

### CloudWatch (AWS)
```json
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/opt/quickbuild/logs/server.log",
            "log_group_name": "/aws/ec2/quickbuild",
            "log_stream_name": "server-{instance_id}"
          }
        ]
      }
    }
  }
}
```

### Azure Monitor
```yaml
# azure-monitor.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: container-azm-ms-agentconfig
data:
  schema-version: v1
  config-version: ver1
  log-data-collection-settings: |
    [log_collection_settings]
       [log_collection_settings.stdout]
          enabled = true
```

### Google Cloud Logging
```yaml
# logging-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: fluentd-config
data:
  fluent.conf: |
    <source>
      @type tail
      path /opt/quickbuild/logs/*.log
      pos_file /var/log/fluentd-quickbuild.log.pos
      tag quickbuild.*
      format none
    </source>
```

## Backup and Recovery

### Database Backup
```bash
# SQL Server backup
docker exec qb-database /opt/mssql-tools/bin/sqlcmd \
  -S localhost -U sa -P "TestPassword123!" \
  -Q "BACKUP DATABASE quickbuild TO DISK = '/var/opt/mssql/backup/quickbuild.bak'"

# Copy backup to cloud storage
aws s3 cp /var/opt/mssql/backup/quickbuild.bak s3://your-backup-bucket/
```

### Application Data Backup
```bash
# Backup QuickBuild data volume
docker run --rm -v quickbuild_server_data:/data -v $(pwd):/backup alpine \
  tar czf /backup/quickbuild-data-$(date +%Y%m%d).tar.gz -C /data .

# Upload to cloud storage
aws s3 cp quickbuild-data-$(date +%Y%m%d).tar.gz s3://your-backup-bucket/
```

## Security Considerations

### Network Security
- Use private subnets for database
- Implement security groups/firewall rules
- Enable VPC flow logs
- Use NAT gateways for outbound traffic

### Application Security
- Change default passwords
- Enable HTTPS/SSL
- Implement proper authentication
- Regular security updates
- Vulnerability scanning

### Data Security
- Encrypt data at rest
- Encrypt data in transit
- Regular backups
- Access logging
- Compliance monitoring

## Cost Optimization

### AWS Cost Optimization
- Use Reserved Instances for predictable workloads
- Implement auto-scaling for agents
- Use Spot Instances for build agents
- Regular resource right-sizing

### Azure Cost Optimization
- Use Azure Reserved VM Instances
- Implement auto-shutdown for dev environments
- Use Azure Cost Management
- Optimize storage tiers

### GCP Cost Optimization
- Use Committed Use Discounts
- Implement Preemptible VMs for agents
- Use Google Cloud Cost Management
- Regular resource cleanup

This specification provides comprehensive guidance for deploying QuickBuild 14 in any major cloud environment.