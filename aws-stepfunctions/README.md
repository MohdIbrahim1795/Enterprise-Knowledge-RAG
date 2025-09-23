# AWS Step Functions Document Processing Workflow

This directory contains the complete AWS Step Functions implementation for automating document processing until storing it in a vector database, as an alternative to the existing Airflow-based pipeline.

## 🏗️ Architecture Overview

The Step Functions workflow replaces the Airflow DAG with a serverless, cloud-native approach that provides better scalability, reliability, and monitoring.

### Workflow Steps

```
📄 Source Documents (S3/MinIO)
    ↓
1️⃣ List New Documents (Lambda)
    ↓
2️⃣ Process Documents in Parallel (Step Functions Map)
    ↓
    ├── Extract Text (Lambda)
    ├── Chunk Text (Lambda) 
    ├── Generate Embeddings (Lambda)
    ├── Store in Vector DB (Lambda)
    └── Move to Processed (Lambda)
    ↓
3️⃣ Cleanup & Notification (Lambda)
```

## 📁 Directory Structure

```
aws-stepfunctions/
├── lambdas/                    # Lambda function implementations
│   ├── list_documents.py      # List new documents to process
│   ├── extract_text.py        # Extract text from PDFs
│   ├── chunk_text.py          # Split text into chunks
│   ├── generate_embeddings.py # Generate OpenAI embeddings
│   ├── store_vectors.py       # Store in Qdrant vector DB
│   ├── move_processed.py      # Move processed documents
│   ├── cleanup.py             # Cleanup and notifications
│   ├── error_handler.py       # Error handling
│   └── requirements.txt       # Python dependencies
├── state-machine/             # Step Functions definitions
│   └── document-processing-workflow.json
├── infrastructure/            # Infrastructure as Code
│   └── cloudformation-template.yaml
└── deployment/                # Deployment scripts
    └── deploy.sh             # Automated deployment script
```

## 🚀 Quick Start

### Prerequisites

- AWS CLI configured with appropriate permissions
- Python 3.9+
- OpenAI API Key
- Qdrant vector database accessible from AWS

### Deployment

1. **Clone and navigate to the Step Functions directory:**
   ```bash
   cd aws-stepfunctions
   ```

2. **Run the deployment script:**
   ```bash
   ./deployment/deploy.sh
   ```

3. **Follow the prompts to configure:**
   - Environment (dev/staging/prod)
   - OpenAI API Key
   - Source S3 bucket name
   - Qdrant endpoint
   - Notification email

### Manual Deployment

If you prefer manual deployment:

```bash
# Build Lambda packages
cd lambdas
pip install -r requirements.txt -t ./
zip -r ../lambda-package.zip .

# Deploy CloudFormation stack
aws cloudformation create-stack \
  --stack-name document-processing-pipeline \
  --template-body file://infrastructure/cloudformation-template.yaml \
  --parameters file://parameters.json \
  --capabilities CAPABILITY_NAMED_IAM

# Update Lambda functions with code
aws lambda update-function-code \
  --function-name document-processor-list-documents \
  --zip-file fileb://lambda-package.zip
```

## 🔧 Configuration

### Environment Variables

Each Lambda function uses environment variables for configuration:

| Variable | Description | Default |
|----------|-------------|---------|
| `SOURCE_BUCKET` | S3 bucket for source documents | `enterprise-data` |
| `SOURCE_PREFIX` | Prefix for source documents | `source/` |
| `PROCESSED_PREFIX` | Prefix for processed documents | `processed/` |
| `OPENAI_API_KEY` | OpenAI API key | Required |
| `QDRANT_HOST` | Qdrant host | `qdrant` |
| `QDRANT_PORT` | Qdrant port | `6333` |
| `COLLECTION_NAME` | Vector collection name | `enterprise-knowledge-base` |

### Step Functions Configuration

The workflow supports customization through input parameters:

```json
{
  "bucketName": "my-custom-bucket",
  "sourcePrefix": "documents/",
  "processedPrefix": "completed/",
  "chunkSize": 1500,
  "chunkOverlap": 300
}
```

## 🔍 Monitoring & Debugging

### CloudWatch Integration

All Lambda functions log to CloudWatch with structured logging:

```python
logger.info(f"Processing document: {filename}")
logger.error(f"WORKFLOW_ERROR: {json.dumps(error_details)}")
```

### Step Functions Visualization

Monitor execution in the AWS Step Functions console:
- View execution history
- Debug failed steps
- Inspect input/output of each step

### SNS Notifications

The workflow sends notifications for:
- Successful completion
- Processing errors
- Individual document failures

## 📊 Performance Optimization

### Parallel Processing

- Documents are processed in parallel using Step Functions Map state
- Configurable concurrency limit (default: 5 documents)
- Batch processing for embeddings and vector storage

### Cost Optimization

- Lambda functions sized appropriately for each task
- Timeout settings prevent runaway executions
- Retry logic with exponential backoff

### Error Handling

- Comprehensive retry policies for transient failures
- Dead letter queues for failed executions
- Partial failure handling - successful documents still processed

## 🔄 Migration from Airflow

### Key Differences

| Aspect | Airflow | Step Functions |
|--------|---------|---------------|
| Infrastructure | Self-managed containers | Serverless |
| Scaling | Manual configuration | Automatic |
| Monitoring | Custom dashboards | Native AWS integration |
| Cost | Fixed compute costs | Pay-per-execution |
| Reliability | Depends on infrastructure | AWS-managed |

### Migration Steps

1. **Deploy Step Functions workflow**
2. **Test with sample documents**
3. **Run parallel processing** (both systems)
4. **Validate results** match between systems
5. **Gradually migrate** document processing
6. **Decommission Airflow** when confident

### Compatibility

The Step Functions implementation maintains compatibility with:
- Same S3/MinIO storage structure
- Same Qdrant vector database
- Same FastAPI query interface
- Same document formats and chunking logic

## 🧪 Testing

### Local Testing

Each Lambda function includes local testing capability:

```bash
cd lambdas
python list_documents.py
python extract_text.py
# etc.
```

### Integration Testing

```bash
# Start test execution
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:region:account:stateMachine:name \
  --name test-execution \
  --input file://test-input.json
```

### Load Testing

For production readiness, test with:
- Large documents (>100 pages)
- Multiple concurrent executions
- Various document formats
- Network failures and timeouts

## 🔐 Security

### IAM Permissions

The CloudFormation template creates minimal required permissions:
- Lambda execution roles
- S3 bucket access
- Step Functions execution permissions
- SNS publishing rights

### API Key Management

- OpenAI API key stored as CloudFormation parameter (NoEcho)
- Consider using AWS Secrets Manager for production
- Rotate keys regularly

### Network Security

- VPC deployment supported
- Security groups for database access
- Encrypted data in transit and at rest

## 📈 Scaling Considerations

### Document Volume

- Current configuration: Up to 5 concurrent documents
- Increase `MaxConcurrency` for higher throughput
- Monitor Lambda concurrent execution limits

### Embedding Costs

- OpenAI charges per token
- Implement cost monitoring and alerts
- Consider batching optimization

### Vector Database

- Ensure Qdrant can handle concurrent writes
- Consider sharding for very large collections
- Monitor storage and query performance

## 🆘 Troubleshooting

### Common Issues

1. **Lambda Timeout Errors**
   - Increase timeout for large documents
   - Optimize code for performance
   - Consider async processing for very large files

2. **OpenAI Rate Limits**
   - Implement exponential backoff
   - Reduce batch sizes
   - Monitor API usage

3. **Vector Database Connection**
   - Check network connectivity
   - Verify credentials
   - Monitor connection pools

4. **S3 Permissions**
   - Verify IAM roles
   - Check bucket policies
   - Ensure regional consistency

### Debug Commands

```bash
# Check Lambda logs
aws logs tail /aws/lambda/document-processor-extract-text --follow

# Check Step Functions execution
aws stepfunctions describe-execution \
  --execution-arn arn:aws:states:region:account:execution:name

# Test individual Lambda
aws lambda invoke \
  --function-name document-processor-list-documents \
  --payload file://test-event.json \
  response.json
```

## 🔮 Future Enhancements

### Planned Features

- [ ] Support for additional document formats (DOCX, TXT, etc.)
- [ ] OCR integration for scanned documents
- [ ] Multi-language support
- [ ] Real-time processing triggers
- [ ] Advanced error recovery
- [ ] Cost optimization analytics

### Integration Opportunities

- [ ] SQS integration for document queues
- [ ] EventBridge for document events
- [ ] API Gateway for manual triggers
- [ ] CloudWatch Dashboards for monitoring
- [ ] AWS Config for compliance tracking

## 📞 Support

For issues and questions:

1. **Check CloudWatch logs** for detailed error information
2. **Review Step Functions execution** history
3. **Validate configuration** parameters
4. **Test individual components** in isolation
5. **Check AWS service status** for regional issues

## 📝 License

This implementation follows the same license as the main Enterprise Knowledge RAG project.