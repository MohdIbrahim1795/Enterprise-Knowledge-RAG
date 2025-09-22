#!/bin/bash
set -e

# AWS Lambda Deployment Script for RAG Chatbot
# This script deploys the RAG chatbot to AWS using SAM CLI

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
ENVIRONMENT="dev"
STACK_NAME=""
REGION="us-east-1"
OPENAI_API_KEY=""
QDRANT_URL=""
BUCKET_NAME=""

# Function to print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check prerequisites
check_prerequisites() {
    print_info "Checking prerequisites..."
    
    # Check if SAM CLI is installed
    if ! command_exists sam; then
        print_error "AWS SAM CLI is not installed. Please install it first:"
        echo "https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html"
        exit 1
    fi
    
    # Check if AWS CLI is installed and configured
    if ! command_exists aws; then
        print_error "AWS CLI is not installed. Please install it first:"
        echo "https://aws.amazon.com/cli/"
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity >/dev/null 2>&1; then
        print_error "AWS credentials are not configured. Please run 'aws configure' first."
        exit 1
    fi
    
    # Check if Docker is running (for SAM build)
    if ! docker info >/dev/null 2>&1; then
        print_error "Docker is not running. Please start Docker first."
        exit 1
    fi
    
    print_success "All prerequisites are met"
}

# Function to validate parameters
validate_parameters() {
    print_info "Validating parameters..."
    
    if [ -z "$STACK_NAME" ]; then
        STACK_NAME="rag-chatbot-${ENVIRONMENT}"
        print_info "Using default stack name: $STACK_NAME"
    fi
    
    if [ -z "$OPENAI_API_KEY" ]; then
        print_error "OpenAI API key is required. Use --openai-key parameter."
        exit 1
    fi
    
    if [ -z "$QDRANT_URL" ]; then
        print_warning "Qdrant URL not provided. Will use default."
        QDRANT_URL="http://localhost:6333"
    fi
    
    if [ -z "$BUCKET_NAME" ]; then
        BUCKET_NAME="enterprise-rag-documents-${ENVIRONMENT}-$(date +%s)"
        print_info "Using auto-generated bucket name: $BUCKET_NAME"
    fi
    
    print_success "Parameters validated"
}

# Function to build the application
build_application() {
    print_info "Building SAM application..."
    
    if ! sam build --use-container; then
        print_error "Failed to build SAM application"
        exit 1
    fi
    
    print_success "Application built successfully"
}

# Function to deploy the application
deploy_application() {
    print_info "Deploying SAM application..."
    
    # Create parameter overrides
    PARAMETER_OVERRIDES=(
        "Environment=${ENVIRONMENT}"
        "OpenAIApiKey=${OPENAI_API_KEY}"
        "QdrantUrl=${QDRANT_URL}"
        "DocumentBucketName=${BUCKET_NAME}"
    )
    
    # Convert array to string
    PARAM_STRING=$(printf "ParameterKey=%s,ParameterValue=%s " "${PARAMETER_OVERRIDES[@]}")
    
    # Deploy with guided mode on first deployment
    if [ "$GUIDED" = "true" ]; then
        sam deploy \
            --guided \
            --stack-name "$STACK_NAME" \
            --region "$REGION" \
            --capabilities CAPABILITY_IAM \
            --parameter-overrides $PARAM_STRING
    else
        sam deploy \
            --stack-name "$STACK_NAME" \
            --region "$REGION" \
            --capabilities CAPABILITY_IAM \
            --parameter-overrides $PARAM_STRING \
            --no-confirm-changeset \
            --no-fail-on-empty-changeset
    fi
    
    if [ $? -eq 0 ]; then
        print_success "Application deployed successfully"
    else
        print_error "Failed to deploy application"
        exit 1
    fi
}

# Function to get stack outputs
get_stack_outputs() {
    print_info "Retrieving stack outputs..."
    
    OUTPUTS=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs' \
        --output table 2>/dev/null)
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "📊 Stack Outputs:"
        echo "$OUTPUTS"
        echo ""
        
        # Get specific outputs
        CHAT_API_URL=$(aws cloudformation describe-stacks \
            --stack-name "$STACK_NAME" \
            --region "$REGION" \
            --query 'Stacks[0].Outputs[?OutputKey==`ChatApiUrl`].OutputValue' \
            --output text 2>/dev/null)
        
        HEALTH_URL=$(aws cloudformation describe-stacks \
            --stack-name "$STACK_NAME" \
            --region "$REGION" \
            --query 'Stacks[0].Outputs[?OutputKey==`HealthCheckUrl`].OutputValue' \
            --output text 2>/dev/null)
        
        BUCKET_NAME_OUTPUT=$(aws cloudformation describe-stacks \
            --stack-name "$STACK_NAME" \
            --region "$REGION" \
            --query 'Stacks[0].Outputs[?OutputKey==`DocumentBucketName`].OutputValue' \
            --output text 2>/dev/null)
        
        if [ -n "$CHAT_API_URL" ]; then
            print_success "Chat API URL: $CHAT_API_URL"
        fi
        
        if [ -n "$HEALTH_URL" ]; then
            print_success "Health Check URL: $HEALTH_URL"
        fi
        
        if [ -n "$BUCKET_NAME_OUTPUT" ]; then
            print_success "Document Bucket: $BUCKET_NAME_OUTPUT"
        fi
    else
        print_warning "Could not retrieve stack outputs"
    fi
}

# Function to test deployment
test_deployment() {
    print_info "Testing deployment..."
    
    # Get health check URL
    HEALTH_URL=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`HealthCheckUrl`].OutputValue' \
        --output text 2>/dev/null)
    
    if [ -n "$HEALTH_URL" ]; then
        print_info "Testing health endpoint: $HEALTH_URL"
        
        RESPONSE=$(curl -s -w "%{http_code}" -o /tmp/health_response "$HEALTH_URL" || echo "000")
        
        if [ "$RESPONSE" = "200" ]; then
            HEALTH_STATUS=$(cat /tmp/health_response | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
            print_success "Health check passed - Status: $HEALTH_STATUS"
        else
            print_warning "Health check returned HTTP $RESPONSE"
        fi
        
        rm -f /tmp/health_response
    else
        print_warning "Could not get health check URL"
    fi
    
    # Test chat endpoint
    CHAT_URL=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`ChatApiUrl`].OutputValue' \
        --output text 2>/dev/null)
    
    if [ -n "$CHAT_URL" ]; then
        print_info "Testing chat endpoint with sample query..."
        
        CHAT_RESPONSE=$(curl -s -w "%{http_code}" -X POST \
            -H "Content-Type: application/json" \
            -d '{"query":"Hello, this is a test query"}' \
            -o /tmp/chat_response \
            "$CHAT_URL" || echo "000")
        
        if [ "$CHAT_RESPONSE" = "200" ]; then
            print_success "Chat endpoint test passed"
        else
            print_warning "Chat endpoint test returned HTTP $CHAT_RESPONSE"
            if [ -f /tmp/chat_response ]; then
                cat /tmp/chat_response
            fi
        fi
        
        rm -f /tmp/chat_response
    fi
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Deploy RAG Chatbot to AWS Lambda using SAM"
    echo ""
    echo "Options:"
    echo "  -e, --environment ENV    Deployment environment (dev/staging/prod) [default: dev]"
    echo "  -s, --stack-name NAME    CloudFormation stack name [default: rag-chatbot-ENV]"
    echo "  -r, --region REGION      AWS region [default: us-east-1]"
    echo "  -k, --openai-key KEY     OpenAI API key (required)"
    echo "  -q, --qdrant-url URL     Qdrant database URL [default: http://localhost:6333]"
    echo "  -b, --bucket-name NAME   S3 bucket name [auto-generated if not provided]"
    echo "  -g, --guided             Use SAM guided deployment"
    echo "  -t, --test-only          Only run tests, skip deployment"
    echo "  -h, --help              Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 --environment dev --openai-key sk-xxx --guided"
    echo "  $0 -e prod -k sk-xxx -r us-west-2 -b my-docs-bucket"
    echo ""
}

# Main deployment function
main() {
    print_info "Starting RAG Chatbot AWS Lambda deployment"
    print_info "Stack: $STACK_NAME | Environment: $ENVIRONMENT | Region: $REGION"
    echo ""
    
    if [ "$TEST_ONLY" != "true" ]; then
        check_prerequisites
        validate_parameters
        build_application
        deploy_application
    fi
    
    get_stack_outputs
    test_deployment
    
    echo ""
    print_success "Deployment completed successfully!"
    echo ""
    echo "📝 Next steps:"
    echo "  1. Test the API endpoints using the URLs above"
    echo "  2. Upload documents to the S3 bucket for processing"
    echo "  3. Monitor Lambda function logs in CloudWatch"
    echo "  4. Set up monitoring and alerting as needed"
    echo ""
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -e|--environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -s|--stack-name)
            STACK_NAME="$2"
            shift 2
            ;;
        -r|--region)
            REGION="$2"
            shift 2
            ;;
        -k|--openai-key)
            OPENAI_API_KEY="$2"
            shift 2
            ;;
        -q|--qdrant-url)
            QDRANT_URL="$2"
            shift 2
            ;;
        -b|--bucket-name)
            BUCKET_NAME="$2"
            shift 2
            ;;
        -g|--guided)
            GUIDED="true"
            shift
            ;;
        -t|--test-only)
            TEST_ONLY="true"
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(dev|staging|prod)$ ]]; then
    print_error "Invalid environment: $ENVIRONMENT. Must be dev, staging, or prod."
    exit 1
fi

# Run main function
main