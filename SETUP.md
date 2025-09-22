# Complete RAG Chatbot Setup Guide

This guide provides comprehensive instructions for setting up and deploying the Enterprise Knowledge RAG (Retrieval Augmented Generation) chatbot system.

## 📋 Table of Contents

1. [Quick Start](#quick-start)
2. [System Requirements](#system-requirements)
3. [Local Development Setup](#local-development-setup)
4. [AWS Lambda Deployment](#aws-lambda-deployment)
5. [Testing](#testing)
6. [Frontend Examples](#frontend-examples)
7. [Configuration](#configuration)
8. [Troubleshooting](#troubleshooting)
9. [Monitoring and Maintenance](#monitoring-and-maintenance)

## 🚀 Quick Start

### Option 1: Docker Compose (Recommended for Local Development)

```bash
# Clone the repository
git clone https://github.com/MohdIbrahim1795/Enterprise-Knowledge-RAG.git
cd Enterprise-Knowledge-RAG

# Copy and configure environment variables
cp .env_example .env
# Edit .env file with your OpenAI API key and other settings

# Start all services
./scripts/docker/manage.sh start

# Access the application
open http://localhost:8501  # Streamlit UI
```

### Option 2: AWS Lambda Deployment

```bash
# Prerequisites: AWS CLI, SAM CLI, Docker installed
# Configure AWS credentials: aws configure

# Deploy to AWS
./scripts/aws/deploy.sh --environment dev --openai-key YOUR_OPENAI_KEY --guided

# The script will output API URLs after deployment
```

## 🔧 System Requirements

### Local Development
- Docker Desktop 4.0+
- Docker Compose 2.0+
- 8GB RAM minimum (16GB recommended)
- 10GB free disk space

### AWS Deployment
- AWS CLI 2.0+
- SAM CLI 1.0+
- Docker (for SAM build)
- AWS Account with appropriate permissions

### Python Development
- Python 3.9+
- pip package manager
- Virtual environment (recommended)

## 🏗️ Local Development Setup

### Step 1: Environment Configuration

1. Copy the example environment file:
```bash
cp .env_example .env
```

2. Edit `.env` with your configuration:
```bash
# Essential settings
OPENAI_API_KEY=sk-your-openai-key-here
POSTGRES_USER=raguser
POSTGRES_PASSWORD=ragpassword123
POSTGRES_DB=rag_chat_db
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin123
```

### Step 2: Start Services

Using the management script:
```bash
# Start all services
./scripts/docker/manage.sh start

# Check service status
./scripts/docker/manage.sh status

# View logs
./scripts/docker/manage.sh logs

# Run health checks
./scripts/docker/manage.sh health
```

### Step 3: Upload Documents

1. Access MinIO console: http://localhost:9001
2. Login with credentials from .env file
3. Upload documents to the `source/` directory
4. Airflow will automatically process new documents daily

### Step 4: Test the System

1. **Streamlit UI**: http://localhost:8501
2. **FastAPI Backend**: http://localhost:8000
3. **Airflow UI**: http://localhost:8080 (admin/admin)

## ☁️ AWS Lambda Deployment

### Prerequisites Setup

1. **Install AWS CLI**:
```bash
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
```

2. **Install SAM CLI**:
```bash
# Linux/macOS
pip install aws-sam-cli

# Or using brew (macOS)
brew tap aws/tap
brew install aws-sam-cli
```

3. **Configure AWS Credentials**:
```bash
aws configure
# Enter your AWS Access Key ID, Secret Access Key, region, and output format
```

### Deployment Steps

1. **Basic Deployment**:
```bash
./scripts/aws/deploy.sh \
  --environment dev \
  --openai-key sk-your-key-here \
  --guided
```

2. **Production Deployment**:
```bash
./scripts/aws/deploy.sh \
  --environment prod \
  --region us-west-2 \
  --openai-key sk-your-key-here \
  --qdrant-url https://your-qdrant-instance.com \
  --bucket-name your-prod-bucket
```

3. **Test Deployment**:
```bash
# Test only (skip actual deployment)
./scripts/aws/deploy.sh --test-only --stack-name existing-stack-name
```

### Post-Deployment Setup

After successful deployment:

1. **Note the API URLs** from the deployment output
2. **Upload documents** to the created S3 bucket
3. **Set up monitoring** in CloudWatch
4. **Configure custom domain** (optional)

## 🧪 Testing

### Running the Test Suite

```bash
# Install test dependencies
pip install -r tests/requirements.txt

# Run all tests
pytest

# Run specific test categories
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only
pytest -m e2e           # End-to-end tests only

# Run with coverage
pytest --cov=aws_lambda --cov=fastapi_app --cov-report=html
```

### Test Configuration

Tests use environment variables for configuration:
```bash
export TEST_API_URL="http://localhost:8000"
export OPENAI_API_KEY="test-key"
export QDRANT_URL="http://localhost:6333"
```

### Manual Testing

1. **Health Check**:
```bash
curl http://localhost:8000/health
```

2. **Chat Endpoint**:
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "What is machine learning?"}'
```

## 🖥️ Frontend Examples

### 1. Command Line Interface (CLI)

```bash
# Interactive mode
python frontend_examples/cli/rag_cli.py --api-url http://localhost:8000

# Single query
python frontend_examples/cli/rag_cli.py \
  --api-url http://localhost:8000 \
  --query "What is AI?"

# Batch processing
python frontend_examples/cli/rag_cli.py \
  --api-url http://localhost:8000 \
  --batch queries.txt
```

### 2. GUI Application

```bash
# Install GUI dependencies
pip install tkinter

# Run GUI application
python frontend_examples/gui/rag_gui.py
```

### 3. Python API Client

```python
from frontend_examples.api_client.rag_client import RAGAPIClient

# Create client
client = RAGAPIClient("http://localhost:8000")

# Send query
response = client.chat("What is machine learning?")
print(response.answer)

# Batch queries
queries = ["What is AI?", "How does ML work?"]
responses = client.batch_chat(queries)
```

### 4. Jupyter Notebook

Open `frontend_examples/jupyter/RAG_Chatbot_Example.ipynb` in Jupyter Lab or Notebook for interactive examples with data visualization.

## ⚙️ Configuration

### Environment Variables Reference

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `OPENAI_API_KEY` | OpenAI API key | Yes | - |
| `OPENAI_EMBEDDING_MODEL` | Embedding model | No | text-embedding-3-small |
| `OPENAI_LLM_MODEL` | Chat completion model | No | gpt-3.5-turbo |
| `QDRANT_URL` | Qdrant database URL | No | http://qdrant:6333 |
| `COLLECTION_NAME` | Vector collection name | No | enterprise-knowledge-base |
| `POSTGRES_*` | PostgreSQL settings | Yes | - |
| `REDIS_*` | Redis settings | No | localhost:6379 |
| `MINIO_*` | MinIO/S3 settings | Yes | - |

### Service Configuration

1. **FastAPI Backend** (`fastapi_app/app/main.py`):
   - Modify model parameters
   - Adjust similarity thresholds
   - Configure caching behavior

2. **Airflow Processing** (`Airflow/processing_logic/indexer.py`):
   - Document processing settings
   - Batch sizes and chunking parameters
   - Embedding generation configuration

3. **Streamlit Frontend** (`App/app.py`):
   - UI customization
   - Display preferences
   - Connection settings

### Advanced Configuration

For production deployments, consider:

1. **Vector Database Scaling**: Use managed Qdrant Cloud
2. **Load Balancing**: Configure multiple API instances
3. **Caching Strategy**: Implement Redis Cluster
4. **Security**: Enable authentication and HTTPS
5. **Monitoring**: Set up comprehensive logging

## 🔍 Troubleshooting

### Common Issues

#### 1. OpenAI API Errors
```bash
# Check API key validity
curl -H "Authorization: Bearer $OPENAI_API_KEY" https://api.openai.com/v1/models

# Verify quota and billing
# Visit: https://platform.openai.com/usage
```

#### 2. Docker Issues
```bash
# Check Docker daemon
docker version

# Free up space
docker system prune -a

# Restart Docker services
./scripts/docker/manage.sh restart
```

#### 3. Vector Database Issues
```bash
# Check Qdrant status
curl http://localhost:6333/health

# View collections
curl http://localhost:6333/collections

# Reset collection (if needed)
curl -X DELETE http://localhost:6333/collections/enterprise-knowledge-base
```

#### 4. Document Processing Issues
```bash
# Check Airflow logs
./scripts/docker/manage.sh logs airflow-scheduler

# Manual trigger
curl -X POST http://localhost:8080/api/v1/dags/knowledge_base_indexing_daily_opensource/dagRuns \
  -H "Content-Type: application/json" \
  -d '{"conf": {}}'
```

### Debug Mode

Enable debug mode for detailed logging:

```bash
# Add to .env file
LOG_LEVEL=DEBUG
DEBUG=true

# Restart services
./scripts/docker/manage.sh restart
```

### Performance Issues

1. **Slow Responses**:
   - Check Qdrant collection size
   - Monitor OpenAI API latency
   - Verify Redis caching is working

2. **High Memory Usage**:
   - Adjust Docker memory limits
   - Optimize vector search parameters
   - Monitor embedding batch sizes

3. **Storage Issues**:
   - Clean up old document versions
   - Monitor MinIO storage usage
   - Archive processed documents

## 📊 Monitoring and Maintenance

### Health Monitoring

1. **Automated Health Checks**:
```bash
# Schedule regular health checks
./scripts/docker/manage.sh health

# Set up monitoring script
cat > monitor.sh << 'EOF'
#!/bin/bash
while true; do
  ./scripts/docker/manage.sh health
  sleep 300  # Check every 5 minutes
done
EOF
```

2. **Service Monitoring**:
   - FastAPI: `/health` endpoint
   - Qdrant: `/health` endpoint
   - PostgreSQL: Connection tests
   - Redis: PING command

### Log Management

1. **Centralized Logging**:
```bash
# View all service logs
./scripts/docker/manage.sh logs

# Export logs
docker-compose logs > system_logs_$(date +%Y%m%d).log
```

2. **Log Rotation**:
Configure Docker log rotation in `daemon.json`:
```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

### Backup Strategy

1. **Data Backup**:
```bash
# Create backup
./scripts/docker/manage.sh backup

# Schedule daily backups
crontab -e
# Add: 0 2 * * * /path/to/project/scripts/docker/manage.sh backup
```

2. **Configuration Backup**:
```bash
# Backup configuration files
tar -czf config_backup_$(date +%Y%m%d).tar.gz .env docker-compose.yml template.yaml
```

### Performance Optimization

1. **Vector Database**:
   - Monitor collection sizes
   - Optimize search parameters
   - Consider index optimization

2. **Caching**:
   - Monitor Redis hit rates
   - Adjust TTL values
   - Implement cache warming

3. **API Performance**:
   - Monitor response times
   - Track error rates
   - Optimize query patterns

### Security Maintenance

1. **Regular Updates**:
```bash
# Update Docker images
./scripts/docker/manage.sh update

# Update dependencies
pip-compile requirements.in
```

2. **Security Scanning**:
```bash
# Scan Docker images
docker scan your-image:tag

# Check for vulnerabilities
safety check -r requirements.txt
```

3. **Access Control**:
   - Rotate API keys regularly
   - Review user permissions
   - Monitor access logs

## 📞 Support and Contribution

- **Documentation**: [README.md](README.md)
- **Issues**: GitHub Issues
- **Contributions**: Pull requests welcome
- **Community**: Discussions tab

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

For additional help or questions, please refer to the troubleshooting section or create an issue in the GitHub repository.