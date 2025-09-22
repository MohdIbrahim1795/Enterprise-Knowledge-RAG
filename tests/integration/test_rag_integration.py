"""
Integration tests for the RAG system
Tests the interaction between different components
"""

import pytest
import json
import time
import os
from unittest.mock import Mock, patch, MagicMock
import requests


class TestRAGIntegration:
    """Integration tests for RAG functionality"""
    
    @pytest.fixture(autouse=True)
    def setup_integration_environment(self):
        """Setup integration test environment"""
        self.test_api_url = os.environ.get("TEST_API_URL", "http://localhost:8000")
        self.test_timeout = 30
    
    def test_full_rag_pipeline_mock(self):
        """Test the complete RAG pipeline with mocked external services"""
        with patch('aws_lambda.handler.openai_client') as mock_openai, \
             patch('aws_lambda.handler.qdrant_client') as mock_qdrant:
            
            # Setup mocks
            mock_embed_response = Mock()
            mock_embed_response.data = [Mock(embedding=[0.1] * 1536)]
            mock_openai.embeddings.create.return_value = mock_embed_response
            
            mock_search_result = Mock()
            mock_search_result.payload = {
                "text": "Machine learning is a subset of artificial intelligence.",
                "source": "ml_intro.pdf",
                "page": 1
            }
            mock_search_result.score = 0.95
            mock_qdrant.search.return_value = [mock_search_result]
            
            mock_chat_response = Mock()
            mock_chat_response.choices = [
                Mock(message=Mock(content="Based on the context, machine learning is a subset of artificial intelligence."))
            ]
            mock_openai.chat.completions.create.return_value = mock_chat_response
            
            # Import and test the handler
            from aws_lambda.handler import lambda_handler
            
            event = {
                "httpMethod": "POST",
                "body": json.dumps({
                    "query": "What is machine learning?",
                    "max_results": 3
                })
            }
            context = Mock()
            
            result = lambda_handler(event, context)
            
            assert result["statusCode"] == 200
            response_data = json.loads(result["body"])
            assert "answer" in response_data
            assert "machine learning" in response_data["answer"].lower()
            assert "sources" in response_data
            assert len(response_data["sources"]) > 0

    def test_embedding_search_integration(self):
        """Test embedding generation and search integration"""
        with patch('aws_lambda.handler.openai_client') as mock_openai, \
             patch('aws_lambda.handler.qdrant_client') as mock_qdrant:
            
            from aws_lambda.handler import RAGService
            
            # Setup embedding mock
            mock_embed_response = Mock()
            mock_embed_response.data = [Mock(embedding=[0.1] * 1536)]
            mock_openai.embeddings.create.return_value = mock_embed_response
            
            # Setup search mock
            mock_search_results = []
            for i in range(3):
                result = Mock()
                result.payload = {
                    "text": f"Document {i} content",
                    "source": f"doc{i}.pdf",
                    "page": 1
                }
                result.score = 0.9 - (i * 0.1)
                mock_search_results.append(result)
            
            mock_qdrant.search.return_value = mock_search_results
            
            # Test the service
            service = RAGService()
            
            # Generate embedding
            embedding = service.generate_embedding("test query")
            assert len(embedding) == 1536
            
            # Search documents
            results = service.search_documents(embedding, limit=3)
            assert len(results) == 3
            assert results[0]["score"] == 0.9
            assert results[1]["score"] == 0.8
            assert results[2]["score"] == 0.7

    def test_conversation_continuity(self):
        """Test conversation continuity across multiple requests"""
        with patch('aws_lambda.handler.openai_client') as mock_openai, \
             patch('aws_lambda.handler.qdrant_client') as mock_qdrant:
            
            from aws_lambda.handler import lambda_handler
            
            # Setup mocks
            mock_embed_response = Mock()
            mock_embed_response.data = [Mock(embedding=[0.1] * 1536)]
            mock_openai.embeddings.create.return_value = mock_embed_response
            
            mock_search_result = Mock()
            mock_search_result.payload = {"text": "Context about Python", "source": "python.pdf", "page": 1}
            mock_search_result.score = 0.9
            mock_qdrant.search.return_value = [mock_search_result]
            
            mock_chat_response = Mock()
            mock_chat_response.choices = [Mock(message=Mock(content="Python is a programming language."))]
            mock_openai.chat.completions.create.return_value = mock_chat_response
            
            context = Mock()
            
            # First request
            event1 = {
                "httpMethod": "POST",
                "body": json.dumps({
                    "query": "What is Python?",
                    "conversation_id": "test-conv-123"
                })
            }
            
            result1 = lambda_handler(event1, context)
            assert result1["statusCode"] == 200
            response1 = json.loads(result1["body"])
            assert response1["conversation_id"] == "test-conv-123"
            
            # Second request with same conversation ID
            event2 = {
                "httpMethod": "POST", 
                "body": json.dumps({
                    "query": "Tell me more about it",
                    "conversation_id": "test-conv-123"
                })
            }
            
            result2 = lambda_handler(event2, context)
            assert result2["statusCode"] == 200
            response2 = json.loads(result2["body"])
            assert response2["conversation_id"] == "test-conv-123"


class TestDocumentProcessingIntegration:
    """Integration tests for document processing"""
    
    def test_document_ingestion_pipeline(self):
        """Test document ingestion pipeline"""
        from aws_lambda.handler import document_ingest_handler
        
        # Mock S3 event
        event = {
            "Records": [
                {
                    "eventVersion": "2.0",
                    "eventSource": "aws:s3",
                    "eventName": "ObjectCreated:Put",
                    "s3": {
                        "bucket": {"name": "test-bucket"},
                        "object": {
                            "key": "source/test-document.pdf",
                            "size": 1024
                        }
                    }
                }
            ]
        }
        
        context = Mock()
        result = document_ingest_handler(event, context)
        
        assert result["statusCode"] == 200
        response_data = json.loads(result["body"])
        assert "Document ingestion handler triggered" in response_data["message"]


class TestErrorHandlingIntegration:
    """Integration tests for error handling"""
    
    def test_openai_api_failure_handling(self):
        """Test handling when OpenAI API fails"""
        with patch('aws_lambda.handler.openai_client') as mock_openai:
            mock_openai.embeddings.create.side_effect = Exception("OpenAI API Error")
            
            from aws_lambda.handler import lambda_handler
            
            event = {
                "httpMethod": "POST",
                "body": json.dumps({"query": "Test query"})
            }
            context = Mock()
            
            result = lambda_handler(event, context)
            
            assert result["statusCode"] == 500
            response_data = json.loads(result["body"])
            assert response_data["status"] == "error"
    
    def test_qdrant_connection_failure_handling(self):
        """Test handling when Qdrant connection fails"""
        with patch('aws_lambda.handler.openai_client') as mock_openai, \
             patch('aws_lambda.handler.qdrant_client') as mock_qdrant:
            
            # OpenAI works fine
            mock_embed_response = Mock()
            mock_embed_response.data = [Mock(embedding=[0.1] * 1536)]
            mock_openai.embeddings.create.return_value = mock_embed_response
            
            # Qdrant fails
            mock_qdrant.search.side_effect = Exception("Qdrant connection error")
            
            from aws_lambda.handler import lambda_handler
            
            event = {
                "httpMethod": "POST",
                "body": json.dumps({"query": "Test query"})
            }
            context = Mock()
            
            result = lambda_handler(event, context)
            
            assert result["statusCode"] == 500
            response_data = json.loads(result["body"])
            assert response_data["status"] == "error"


class TestPerformanceIntegration:
    """Integration tests for performance characteristics"""
    
    def test_response_time_within_limits(self):
        """Test that responses are generated within acceptable time limits"""
        with patch('aws_lambda.handler.openai_client') as mock_openai, \
             patch('aws_lambda.handler.qdrant_client') as mock_qdrant:
            
            # Setup mocks with realistic delays
            def slow_embedding_create(*args, **kwargs):
                time.sleep(0.1)  # Simulate API delay
                mock_response = Mock()
                mock_response.data = [Mock(embedding=[0.1] * 1536)]
                return mock_response
            
            def slow_search(*args, **kwargs):
                time.sleep(0.05)  # Simulate search delay
                result = Mock()
                result.payload = {"text": "Test content", "source": "test.pdf", "page": 1}
                result.score = 0.9
                return [result]
            
            def slow_chat_create(*args, **kwargs):
                time.sleep(0.2)  # Simulate LLM delay
                mock_response = Mock()
                mock_response.choices = [Mock(message=Mock(content="Test response"))]
                return mock_response
            
            mock_openai.embeddings.create.side_effect = slow_embedding_create
            mock_qdrant.search.side_effect = slow_search
            mock_openai.chat.completions.create.side_effect = slow_chat_create
            
            from aws_lambda.handler import lambda_handler
            
            event = {
                "httpMethod": "POST",
                "body": json.dumps({"query": "Performance test query"})
            }
            context = Mock()
            
            start_time = time.time()
            result = lambda_handler(event, context)
            end_time = time.time()
            
            # Should complete within reasonable time (allowing for mocked delays)
            assert end_time - start_time < 2.0
            assert result["statusCode"] == 200
            
            response_data = json.loads(result["body"])
            assert "processing_time" in response_data
            assert response_data["processing_time"] > 0

    def test_concurrent_requests_handling(self):
        """Test handling of multiple concurrent requests"""
        import threading
        
        with patch('aws_lambda.handler.openai_client') as mock_openai, \
             patch('aws_lambda.handler.qdrant_client') as mock_qdrant:
            
            # Setup mocks
            mock_embed_response = Mock()
            mock_embed_response.data = [Mock(embedding=[0.1] * 1536)]
            mock_openai.embeddings.create.return_value = mock_embed_response
            
            mock_search_result = Mock()
            mock_search_result.payload = {"text": "Concurrent test", "source": "test.pdf", "page": 1}
            mock_search_result.score = 0.9
            mock_qdrant.search.return_value = [mock_search_result]
            
            mock_chat_response = Mock()
            mock_chat_response.choices = [Mock(message=Mock(content="Concurrent response"))]
            mock_openai.chat.completions.create.return_value = mock_chat_response
            
            from aws_lambda.handler import lambda_handler
            
            results = []
            errors = []
            
            def make_request(request_id):
                try:
                    event = {
                        "httpMethod": "POST",
                        "body": json.dumps({"query": f"Concurrent query {request_id}"})
                    }
                    context = Mock()
                    result = lambda_handler(event, context)
                    results.append(result)
                except Exception as e:
                    errors.append(e)
            
            # Create and start multiple threads
            threads = []
            for i in range(5):
                thread = threading.Thread(target=make_request, args=(i,))
                threads.append(thread)
                thread.start()
            
            # Wait for all threads to complete
            for thread in threads:
                thread.join(timeout=5)
            
            # Check results
            assert len(errors) == 0, f"Errors occurred: {errors}"
            assert len(results) == 5
            
            for result in results:
                assert result["statusCode"] == 200


class TestHealthCheckIntegration:
    """Integration tests for health check functionality"""
    
    def test_health_check_all_services_healthy(self):
        """Test health check when all services are healthy"""
        with patch('aws_lambda.handler.openai_client') as mock_openai, \
             patch('aws_lambda.handler.qdrant_client') as mock_qdrant:
            
            mock_openai.models.list.return_value = Mock()
            mock_qdrant.get_collections.return_value = Mock()
            
            from aws_lambda.handler import health_check_handler
            
            event = {}
            context = Mock()
            
            result = health_check_handler(event, context)
            
            assert result["statusCode"] == 200
            response_data = json.loads(result["body"])
            assert response_data["status"] == "healthy"
            assert response_data["services"]["openai"] == "healthy"
            assert response_data["services"]["qdrant"] == "healthy"
    
    def test_health_check_degraded_service(self):
        """Test health check when one service is degraded"""
        with patch('aws_lambda.handler.openai_client') as mock_openai, \
             patch('aws_lambda.handler.qdrant_client') as mock_qdrant:
            
            mock_openai.models.list.side_effect = Exception("Service unavailable")
            mock_qdrant.get_collections.return_value = Mock()
            
            from aws_lambda.handler import health_check_handler
            
            event = {}
            context = Mock()
            
            result = health_check_handler(event, context)
            
            assert result["statusCode"] == 200
            response_data = json.loads(result["body"])
            assert response_data["status"] == "degraded"
            assert "unhealthy" in response_data["services"]["openai"]
            assert response_data["services"]["qdrant"] == "healthy"


if __name__ == '__main__':
    pytest.main([__file__])