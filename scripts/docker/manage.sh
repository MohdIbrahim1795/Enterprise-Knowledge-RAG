#!/bin/bash
set -e

# Docker Compose Management Script for RAG Chatbot
# Provides convenient commands for managing the Docker-based RAG system

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="docker-compose.yml"
ENV_FILE=".env"
PROJECT_NAME="rag-chatbot"

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

# Function to check if Docker and Docker Compose are available
check_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! command -v docker-compose >/dev/null 2>&1; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    if ! docker info >/dev/null 2>&1; then
        print_error "Docker daemon is not running. Please start Docker first."
        exit 1
    fi
}

# Function to check if .env file exists
check_env_file() {
    if [ ! -f "$ENV_FILE" ]; then
        print_warning ".env file not found. Creating from .env_example..."
        if [ -f ".env_example" ]; then
            cp .env_example .env
            print_info "Please edit .env file with your configuration before starting services."
            return 1
        else
            print_error ".env_example file not found. Cannot create .env file."
            exit 1
        fi
    fi
    return 0
}

# Function to validate environment variables
validate_env() {
    print_info "Validating environment configuration..."
    
    # Source the .env file
    set -a
    source .env
    set +a
    
    # Check critical variables
    MISSING_VARS=()
    
    if [ -z "$OPENAI_API_KEY" ] || [ "$OPENAI_API_KEY" = "your_openai_api_key_here" ]; then
        MISSING_VARS+=("OPENAI_API_KEY")
    fi
    
    if [ -z "$POSTGRES_USER" ] || [ "$POSTGRES_USER" = "your_postgres_user" ]; then
        MISSING_VARS+=("POSTGRES_USER")
    fi
    
    if [ -z "$POSTGRES_PASSWORD" ] || [ "$POSTGRES_PASSWORD" = "your_postgres_password" ]; then
        MISSING_VARS+=("POSTGRES_PASSWORD")
    fi
    
    if [ ${#MISSING_VARS[@]} -gt 0 ]; then
        print_error "Missing or invalid environment variables:"
        for var in "${MISSING_VARS[@]}"; do
            echo "  - $var"
        done
        echo ""
        print_info "Please edit .env file and set these variables."
        return 1
    fi
    
    print_success "Environment configuration is valid"
    return 0
}

# Function to start services
start_services() {
    print_info "Starting RAG Chatbot services..."
    
    if ! check_env_file; then
        return 1
    fi
    
    if ! validate_env; then
        return 1
    fi
    
    # Build and start services
    docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" up -d --build
    
    if [ $? -eq 0 ]; then
        print_success "Services started successfully"
        show_status
        show_urls
    else
        print_error "Failed to start services"
        return 1
    fi
}

# Function to stop services
stop_services() {
    print_info "Stopping RAG Chatbot services..."
    
    docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" down
    
    if [ $? -eq 0 ]; then
        print_success "Services stopped successfully"
    else
        print_error "Failed to stop services"
        return 1
    fi
}

# Function to restart services
restart_services() {
    print_info "Restarting RAG Chatbot services..."
    stop_services
    sleep 2
    start_services
}

# Function to show service status
show_status() {
    print_info "Service Status:"
    docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" ps
}

# Function to show service URLs
show_urls() {
    echo ""
    print_info "Service URLs:"
    echo "  🌐 Streamlit UI:      http://localhost:8501"
    echo "  🔧 FastAPI Backend:   http://localhost:8000"
    echo "  📊 Airflow UI:        http://localhost:8080 (admin/admin)"
    echo "  💾 MinIO Console:     http://localhost:9001"
    echo "  🔍 Qdrant Dashboard:  http://localhost:6333/dashboard"
    echo ""
}

# Function to show logs
show_logs() {
    SERVICE=${1:-""}
    
    if [ -n "$SERVICE" ]; then
        print_info "Showing logs for $SERVICE..."
        docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" logs -f "$SERVICE"
    else
        print_info "Showing logs for all services..."
        docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" logs -f
    fi
}

# Function to execute command in service container
exec_command() {
    SERVICE="$1"
    shift
    COMMAND="$@"
    
    if [ -z "$SERVICE" ]; then
        print_error "Service name is required"
        return 1
    fi
    
    if [ -z "$COMMAND" ]; then
        COMMAND="bash"
    fi
    
    print_info "Executing command in $SERVICE: $COMMAND"
    docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec "$SERVICE" $COMMAND
}

# Function to clean up volumes and data
cleanup() {
    print_warning "This will remove all data including documents, chat history, and vector embeddings."
    read -p "Are you sure you want to continue? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "Stopping services and cleaning up..."
        docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" down -v --remove-orphans
        
        # Remove any dangling images
        docker image prune -f
        
        print_success "Cleanup completed"
    else
        print_info "Cleanup cancelled"
    fi
}

# Function to backup data
backup_data() {
    BACKUP_DIR="backups/$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    
    print_info "Creating backup in $BACKUP_DIR..."
    
    # Backup PostgreSQL database
    if docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" ps | grep -q postgres; then
        print_info "Backing up PostgreSQL database..."
        docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T postgres pg_dumpall -U postgres > "$BACKUP_DIR/postgres_backup.sql"
    fi
    
    # Backup MinIO data
    if docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" ps | grep -q minio; then
        print_info "Backing up MinIO data..."
        docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T minio tar czf - /data > "$BACKUP_DIR/minio_backup.tar.gz"
    fi
    
    # Backup Qdrant data
    if docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" ps | grep -q qdrant; then
        print_info "Backing up Qdrant data..."
        docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T qdrant tar czf - /qdrant/storage > "$BACKUP_DIR/qdrant_backup.tar.gz"
    fi
    
    # Create backup info file
    cat > "$BACKUP_DIR/backup_info.txt" << EOF
RAG Chatbot Backup
==================
Created: $(date)
Services: $(docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" ps --services | tr '\n' ' ')
Containers: $(docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" ps -q | wc -l)
EOF
    
    print_success "Backup created in $BACKUP_DIR"
}

# Function to run health checks
health_check() {
    print_info "Running health checks..."
    
    # Check if services are running
    SERVICES=$(docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" ps --services)
    RUNNING_SERVICES=$(docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" ps --services --filter status=running)
    
    echo ""
    echo "📊 Service Status:"
    
    for service in $SERVICES; do
        if echo "$RUNNING_SERVICES" | grep -q "^$service$"; then
            print_success "$service is running"
        else
            print_error "$service is not running"
        fi
    done
    
    # Test API endpoints
    echo ""
    echo "🔍 API Health Checks:"
    
    # FastAPI health check
    if curl -s -f http://localhost:8000/health >/dev/null 2>&1; then
        print_success "FastAPI backend is healthy"
    else
        print_error "FastAPI backend is not responding"
    fi
    
    # Streamlit check
    if curl -s -f http://localhost:8501 >/dev/null 2>&1; then
        print_success "Streamlit frontend is accessible"
    else
        print_error "Streamlit frontend is not accessible"
    fi
    
    # Airflow check
    if curl -s -f http://localhost:8080/health >/dev/null 2>&1; then
        print_success "Airflow is accessible"
    else
        print_warning "Airflow may still be starting up"
    fi
}

# Function to update services
update_services() {
    print_info "Updating RAG Chatbot services..."
    
    # Pull latest images
    docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" pull
    
    # Rebuild and restart
    docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" up -d --build
    
    print_success "Services updated successfully"
}

# Function to show usage
show_usage() {
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  start                 Start all services"
    echo "  stop                  Stop all services"
    echo "  restart               Restart all services"
    echo "  status                Show service status"
    echo "  logs [service]        Show logs (all services or specific service)"
    echo "  exec <service> [cmd]  Execute command in service container"
    echo "  health                Run health checks"
    echo "  backup                Create data backup"
    echo "  cleanup               Stop services and remove all data"
    echo "  update                Update services to latest versions"
    echo "  urls                  Show service URLs"
    echo ""
    echo "Examples:"
    echo "  $0 start              # Start all services"
    echo "  $0 logs fastapi_app   # Show FastAPI logs"
    echo "  $0 exec postgres bash # Open bash in postgres container"
    echo "  $0 health             # Check service health"
    echo ""
}

# Main script logic
main() {
    # Check prerequisites
    check_docker
    
    # Parse command
    case "${1:-}" in
        start)
            start_services
            ;;
        stop)
            stop_services
            ;;
        restart)
            restart_services
            ;;
        status)
            show_status
            ;;
        logs)
            show_logs "$2"
            ;;
        exec)
            shift
            exec_command "$@"
            ;;
        health)
            health_check
            ;;
        backup)
            backup_data
            ;;
        cleanup)
            cleanup
            ;;
        update)
            update_services
            ;;
        urls)
            show_urls
            ;;
        help|--help|-h)
            show_usage
            ;;
        "")
            print_error "No command specified"
            show_usage
            exit 1
            ;;
        *)
            print_error "Unknown command: $1"
            show_usage
            exit 1
            ;;
    esac
}

# Run main function
main "$@"