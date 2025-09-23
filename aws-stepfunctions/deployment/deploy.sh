#!/bin/bash

# AWS Step Functions Document Processing Deployment Script
# This script builds and deploys the Lambda functions and Step Functions workflow

set -e

# Configuration
ENVIRONMENT=${ENVIRONMENT:-dev}
REGION=${AWS_REGION:-us-east-1}
STACK_NAME="${ENVIRONMENT}-document-processing-pipeline"
TEMPLATE_FILE="infrastructure/cloudformation-template.yaml"
LAMBDA_DIR="lambdas"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting deployment of Document Processing Pipeline${NC}"
echo "Environment: ${ENVIRONMENT}"
echo "Region: ${REGION}"
echo "Stack Name: ${STACK_NAME}"

# Check prerequisites
check_prerequisites() {
    echo -e "${YELLOW}Checking prerequisites...${NC}"
    
    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        echo -e "${RED}Error: AWS CLI is not installed${NC}"
        exit 1
    fi
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}Error: Python 3 is not installed${NC}"
        exit 1
    fi
    
    # Check pip
    if ! command -v pip3 &> /dev/null; then
        echo -e "${RED}Error: pip3 is not installed${NC}"
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        echo -e "${RED}Error: AWS credentials not configured${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}Prerequisites check passed${NC}"
}

# Build Lambda deployment packages
build_lambda_packages() {
    echo -e "${YELLOW}Building Lambda deployment packages...${NC}"
    
    # Create build directory
    mkdir -p build
    rm -rf build/*
    
    # List of Lambda functions
    LAMBDA_FUNCTIONS=(
        "list_documents"
        "extract_text"
        "chunk_text"
        "generate_embeddings"
        "store_vectors"
        "move_processed"
        "cleanup"
        "error_handler"
    )
    
    for func in "${LAMBDA_FUNCTIONS[@]}"; do
        echo "Building ${func}..."
        
        # Create function directory
        func_dir="build/${func}"
        mkdir -p ${func_dir}
        
        # Copy function code
        cp ${LAMBDA_DIR}/${func}.py ${func_dir}/
        cp ${LAMBDA_DIR}/requirements.txt ${func_dir}/
        
        # Install dependencies
        pip3 install -r ${func_dir}/requirements.txt -t ${func_dir}/ --quiet
        
        # Create deployment package
        cd ${func_dir}
        zip -rq ../${func}.zip . -x "*.pyc" "*__pycache__*"
        cd - > /dev/null
        
        echo "  Built ${func}.zip ($(du -h build/${func}.zip | cut -f1))"
    done
    
    echo -e "${GREEN}Lambda packages built successfully${NC}"
}

# Deploy CloudFormation stack
deploy_infrastructure() {
    echo -e "${YELLOW}Deploying infrastructure...${NC}"
    
    # Check if stack exists
    if aws cloudformation describe-stacks --stack-name ${STACK_NAME} --region ${REGION} &> /dev/null; then
        echo "Stack exists, updating..."
        OPERATION="update-stack"
    else
        echo "Stack does not exist, creating..."
        OPERATION="create-stack"
    fi
    
    # Get parameters
    read -p "Enter OpenAI API Key: " -s OPENAI_API_KEY
    echo
    read -p "Enter Source Bucket Name [enterprise-knowledge-base-source]: " SOURCE_BUCKET
    SOURCE_BUCKET=${SOURCE_BUCKET:-enterprise-knowledge-base-source}
    read -p "Enter Qdrant Endpoint [localhost]: " QDRANT_ENDPOINT
    QDRANT_ENDPOINT=${QDRANT_ENDPOINT:-localhost}
    read -p "Enter Notification Email: " NOTIFICATION_EMAIL
    
    # Deploy stack
    aws cloudformation ${OPERATION} \
        --stack-name ${STACK_NAME} \
        --template-body file://${TEMPLATE_FILE} \
        --parameters \
            ParameterKey=Environment,ParameterValue=${ENVIRONMENT} \
            ParameterKey=OpenAIApiKey,ParameterValue=${OPENAI_API_KEY} \
            ParameterKey=SourceBucketName,ParameterValue=${SOURCE_BUCKET} \
            ParameterKey=QdrantEndpoint,ParameterValue=${QDRANT_ENDPOINT} \
            ParameterKey=NotificationEmail,ParameterValue=${NOTIFICATION_EMAIL} \
        --capabilities CAPABILITY_NAMED_IAM \
        --region ${REGION}
    
    echo "Waiting for stack operation to complete..."
    aws cloudformation wait stack-${OPERATION%-*}-complete --stack-name ${STACK_NAME} --region ${REGION}
    
    echo -e "${GREEN}Infrastructure deployed successfully${NC}"
}

# Update Lambda function code
update_lambda_functions() {
    echo -e "${YELLOW}Updating Lambda function code...${NC}"
    
    # Get function names from CloudFormation outputs
    LAMBDA_FUNCTIONS=(
        "${ENVIRONMENT}-document-processor-list-documents"
        "${ENVIRONMENT}-document-processor-extract-text"
        "${ENVIRONMENT}-document-processor-chunk-text"
        "${ENVIRONMENT}-document-processor-generate-embeddings"
        "${ENVIRONMENT}-document-processor-store-vectors"
        "${ENVIRONMENT}-document-processor-move-processed"
        "${ENVIRONMENT}-document-processor-cleanup"
        "${ENVIRONMENT}-document-processor-error-handler"
    )
    
    BUILD_FUNCTIONS=(
        "list_documents"
        "extract_text"
        "chunk_text"
        "generate_embeddings"
        "store_vectors"
        "move_processed"
        "cleanup"
        "error_handler"
    )
    
    for i in "${!LAMBDA_FUNCTIONS[@]}"; do
        func_name="${LAMBDA_FUNCTIONS[$i]}"
        build_name="${BUILD_FUNCTIONS[$i]}"
        
        echo "Updating ${func_name}..."
        
        aws lambda update-function-code \
            --function-name ${func_name} \
            --zip-file fileb://build/${build_name}.zip \
            --region ${REGION} > /dev/null
    done
    
    echo -e "${GREEN}Lambda functions updated successfully${NC}"
}

# Test the deployment
test_deployment() {
    echo -e "${YELLOW}Testing deployment...${NC}"
    
    # Get state machine ARN
    STATE_MACHINE_ARN=$(aws cloudformation describe-stacks \
        --stack-name ${STACK_NAME} \
        --region ${REGION} \
        --query 'Stacks[0].Outputs[?OutputKey==`StateMachineArn`].OutputValue' \
        --output text)
    
    echo "State Machine ARN: ${STATE_MACHINE_ARN}"
    
    # Start test execution
    EXECUTION_NAME="test-execution-$(date +%s)"
    
    aws stepfunctions start-execution \
        --state-machine-arn ${STATE_MACHINE_ARN} \
        --name ${EXECUTION_NAME} \
        --input '{"test": true}' \
        --region ${REGION} > /dev/null
    
    echo "Started test execution: ${EXECUTION_NAME}"
    echo "Monitor at: https://${REGION}.console.aws.amazon.com/states/home?region=${REGION}#/executions"
    
    echo -e "${GREEN}Deployment test initiated${NC}"
}

# Main deployment flow
main() {
    echo -e "${GREEN}Document Processing Pipeline Deployment${NC}"
    echo "========================================"
    
    check_prerequisites
    build_lambda_packages
    deploy_infrastructure
    update_lambda_functions
    
    # Ask if user wants to run test
    read -p "Do you want to run a test execution? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        test_deployment
    fi
    
    echo -e "${GREEN}Deployment completed successfully!${NC}"
    echo
    echo "Next steps:"
    echo "1. Upload test documents to your source bucket"
    echo "2. Configure your Qdrant vector database connection"
    echo "3. Monitor the Step Functions executions in AWS Console"
    echo "4. Check SNS notifications for completion/error alerts"
}

# Run main function
main "$@"