"""
Test configuration and fixtures for the RAG chatbot test suite
"""

import os
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any, List

# Test configuration
TEST_CONFIG = {
    "openai_api_key": "test-key-123",
    "qdrant_url": "http://test-qdrant:6333",
    "collection_name": "test-collection",
    "embedding_model": "text-embedding-3-small",
    "llm_model": "gpt-3.5-turbo",
    "max_tokens": 350,
    "similarity_threshold": 0.7
}

@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client for testing"""
    client = Mock()
    
    # Mock embedding response
    embedding_response = Mock()
    embedding_response.data = [Mock(embedding=[0.1] * 1536)]
    client.embeddings.create.return_value = embedding_response
    
    # Mock chat completion response
    completion_response = Mock()
    completion_response.choices = [Mock(message=Mock(content="Test response"))]
    client.chat.completions.create.return_value = completion_response
    
    # Mock models list
    client.models.list.return_value = Mock()
    
    return client

@pytest.fixture
def mock_qdrant_client():
    """Mock Qdrant client for testing"""
    client = Mock()
    
    # Mock search results
    search_result = Mock()
    search_result.payload = {
        "text": "Test document content",
        "source": "test.pdf",
        "page": 1
    }
    search_result.score = 0.9
    
    client.search.return_value = [search_result]
    client.get_collections.return_value = Mock()
    
    return client

@pytest.fixture
def sample_chat_request():
    """Sample chat request for testing"""
    return {
        "query": "What is the main topic?",
        "conversation_id": "test-conv-123",
        "max_results": 3
    }

@pytest.fixture
def sample_lambda_event():
    """Sample Lambda event for testing"""
    return {
        "httpMethod": "POST",
        "headers": {
            "Content-Type": "application/json"
        },
        "body": json.dumps({
            "query": "What is the main topic?",
            "max_results": 3
        })
    }

@pytest.fixture
def mock_lambda_context():
    """Mock Lambda context for testing"""
    context = Mock()
    context.function_name = "test-function"
    context.memory_limit_in_mb = 512
    context.get_remaining_time_in_millis.return_value = 30000
    return context

@pytest.fixture
def sample_s3_event():
    """Sample S3 event for document ingestion testing"""
    return {
        "Records": [
            {
                "eventVersion": "2.0",
                "eventSource": "aws:s3",
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {
                        "name": "test-bucket"
                    },
                    "object": {
                        "key": "source/test-document.pdf",
                        "size": 1024
                    }
                }
            }
        ]
    }

@pytest.fixture(autouse=True)
def setup_test_environment():
    """Set up test environment variables"""
    test_env = {
        "OPENAI_API_KEY": TEST_CONFIG["openai_api_key"],
        "QDRANT_URL": TEST_CONFIG["qdrant_url"],
        "COLLECTION_NAME": TEST_CONFIG["collection_name"],
        "EMBEDDING_MODEL": TEST_CONFIG["embedding_model"],
        "LLM_MODEL": TEST_CONFIG["llm_model"],
        "MAX_TOKENS": str(TEST_CONFIG["max_tokens"]),
        "SIMILARITY_THRESHOLD": str(TEST_CONFIG["similarity_threshold"]),
        "LOG_LEVEL": "DEBUG"
    }
    
    with patch.dict(os.environ, test_env):
        yield

class MockRAGService:
    """Mock RAG service for integration testing"""
    
    def __init__(self):
        self.openai_client = Mock()
        self.qdrant_client = Mock()
    
    def generate_embedding(self, text: str) -> List[float]:
        return [0.1] * 1536
    
    def search_documents(self, query_embedding: List[float], limit: int = 3) -> List[Dict[str, Any]]:
        return [
            {
                "text": "Test document content",
                "source": "test.pdf",
                "page": 1,
                "score": 0.9
            }
        ]
    
    def generate_response(self, query: str, context: str) -> str:
        return f"Generated response for query: {query}"
    
    def process_chat_request(self, request) -> Dict[str, Any]:
        return {
            "answer": "Test answer",
            "conversation_id": "test-conv-123",
            "sources": self.search_documents([0.1] * 1536),
            "processing_time": 0.5,
            "cached": False,
            "status": "success"
        }

# Test data
SAMPLE_DOCUMENTS = [
    {
        "text": "This is a sample document about machine learning.",
        "source": "ml_intro.pdf",
        "page": 1
    },
    {
        "text": "Python is a popular programming language for AI development.",
        "source": "python_guide.pdf", 
        "page": 2
    },
    {
        "text": "Vector databases are used for similarity search in RAG systems.",
        "source": "vector_db.pdf",
        "page": 3
    }
]

SAMPLE_QUERIES = [
    "What is machine learning?",
    "How to use Python for AI?",
    "Explain vector databases",
    "What are the benefits of RAG systems?"
]