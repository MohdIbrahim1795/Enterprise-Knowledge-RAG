"""
Unit tests for AWS Lambda handlers
"""

import pytest
import json
import os
from unittest.mock import Mock, patch, MagicMock
from unittest import TestCase

# Import the handlers (need to mock dependencies first)
with patch.dict(os.environ, {
    'OPENAI_API_KEY': 'test-key',
    'QDRANT_URL': 'http://test:6333'
}):
    with patch('aws_lambda.handler.OpenAI'), patch('aws_lambda.handler.QdrantClient'):
        from aws_lambda.handler import (
            lambda_handler, 
            document_ingest_handler, 
            health_check_handler,
            ChatRequest,
            ChatResponse,
            RAGService
        )


class TestChatRequest:
    """Test ChatRequest data class"""
    
    def test_from_dict_valid_request(self):
        """Test creating ChatRequest from valid dictionary"""
        data = {
            "query": "Test query",
            "conversation_id": "conv-123",
            "max_results": 5
        }
        
        request = ChatRequest.from_dict(data)
        assert request.query == "Test query"
        assert request.conversation_id == "conv-123"
        assert request.max_results == 5
    
    def test_from_dict_empty_query(self):
        """Test ChatRequest validation with empty query"""
        data = {"query": ""}
        
        with pytest.raises(ValueError, match="Query cannot be empty"):
            ChatRequest.from_dict(data)
    
    def test_from_dict_max_results_capped(self):
        """Test max_results is capped at 10"""
        data = {"query": "Test", "max_results": 15}
        
        request = ChatRequest.from_dict(data)
        assert request.max_results == 10
    
    def test_from_dict_defaults(self):
        """Test default values are set correctly"""
        data = {"query": "Test query"}
        
        request = ChatRequest.from_dict(data)
        assert request.conversation_id is None
        assert request.max_results == 3


class TestChatResponse:
    """Test ChatResponse data class"""
    
    def test_to_dict(self):
        """Test converting ChatResponse to dictionary"""
        response = ChatResponse(
            answer="Test answer",
            conversation_id="conv-123",
            sources=[{"text": "Test", "score": 0.9}],
            processing_time=1.5,
            cached=True
        )
        
        result = response.to_dict()
        expected = {
            'answer': 'Test answer',
            'conversation_id': 'conv-123',
            'sources': [{"text": "Test", "score": 0.9}],
            'processing_time': 1.5,
            'cached': True,
            'status': 'success'
        }
        
        assert result == expected


class TestRAGService:
    """Test RAGService class"""
    
    @patch('aws_lambda.handler.openai_client')
    @patch('aws_lambda.handler.qdrant_client')
    def test_generate_embedding(self, mock_qdrant, mock_openai):
        """Test embedding generation"""
        # Setup mock
        mock_response = Mock()
        mock_response.data = [Mock(embedding=[0.1] * 1536)]
        mock_openai.embeddings.create.return_value = mock_response
        
        service = RAGService()
        result = service.generate_embedding("test text")
        
        assert result == [0.1] * 1536
        mock_openai.embeddings.create.assert_called_once()
    
    @patch('aws_lambda.handler.openai_client')
    @patch('aws_lambda.handler.qdrant_client')
    def test_search_documents(self, mock_qdrant, mock_openai):
        """Test document search"""
        # Setup mock search results
        mock_result = Mock()
        mock_result.payload = {
            'text': 'Test document',
            'source': 'test.pdf',
            'page': 1
        }
        mock_result.score = 0.9
        mock_qdrant.search.return_value = [mock_result]
        
        service = RAGService()
        results = service.search_documents([0.1] * 1536, limit=3)
        
        assert len(results) == 1
        assert results[0]['text'] == 'Test document'
        assert results[0]['score'] == 0.9
    
    @patch('aws_lambda.handler.openai_client')
    @patch('aws_lambda.handler.qdrant_client')
    def test_generate_response(self, mock_qdrant, mock_openai):
        """Test LLM response generation"""
        # Setup mock chat completion
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Generated answer"))]
        mock_openai.chat.completions.create.return_value = mock_response
        
        service = RAGService()
        result = service.generate_response("test query", "test context")
        
        assert result == "Generated answer"
        mock_openai.chat.completions.create.assert_called_once()


class TestLambdaHandler:
    """Test Lambda handler functions"""
    
    @patch('aws_lambda.handler.rag_service')
    def test_lambda_handler_valid_request(self, mock_service):
        """Test Lambda handler with valid request"""
        # Setup mock service response
        mock_response = Mock()
        mock_response.to_dict.return_value = {
            'answer': 'Test answer',
            'conversation_id': 'conv-123',
            'sources': [],
            'processing_time': 0.5,
            'cached': False,
            'status': 'success'
        }
        mock_service.process_chat_request.return_value = mock_response
        
        event = {
            'httpMethod': 'POST',
            'body': json.dumps({
                'query': 'Test query'
            })
        }
        context = Mock()
        
        result = lambda_handler(event, context)
        
        assert result['statusCode'] == 200
        response_body = json.loads(result['body'])
        assert response_body['answer'] == 'Test answer'
    
    def test_lambda_handler_options_request(self):
        """Test Lambda handler with OPTIONS request (CORS preflight)"""
        event = {'httpMethod': 'OPTIONS'}
        context = Mock()
        
        result = lambda_handler(event, context)
        
        assert result['statusCode'] == 200
        assert 'Access-Control-Allow-Origin' in result['headers']
        assert 'Access-Control-Allow-Methods' in result['headers']
    
    @patch('aws_lambda.handler.rag_service')
    def test_lambda_handler_invalid_request(self, mock_service):
        """Test Lambda handler with invalid request"""
        event = {
            'httpMethod': 'POST',
            'body': json.dumps({
                'query': ''  # Empty query should be invalid
            })
        }
        context = Mock()
        
        result = lambda_handler(event, context)
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert response_body['status'] == 'error'
    
    @patch('aws_lambda.handler.rag_service')
    def test_lambda_handler_service_error(self, mock_service):
        """Test Lambda handler when service raises error"""
        mock_service.process_chat_request.side_effect = Exception("Service error")
        
        event = {
            'httpMethod': 'POST',
            'body': json.dumps({
                'query': 'Test query'
            })
        }
        context = Mock()
        
        result = lambda_handler(event, context)
        
        assert result['statusCode'] == 500
        response_body = json.loads(result['body'])
        assert response_body['status'] == 'error'
    
    def test_document_ingest_handler(self):
        """Test document ingest handler"""
        event = {
            'Records': [
                {
                    's3': {
                        'bucket': {'name': 'test-bucket'},
                        'object': {'key': 'source/test.pdf'}
                    }
                }
            ]
        }
        context = Mock()
        
        result = document_ingest_handler(event, context)
        
        assert result['statusCode'] == 200
        response_body = json.loads(result['body'])
        assert 'Document ingestion handler triggered' in response_body['message']
    
    @patch('aws_lambda.handler.openai_client')
    @patch('aws_lambda.handler.qdrant_client')
    def test_health_check_handler_healthy(self, mock_qdrant, mock_openai):
        """Test health check handler when services are healthy"""
        # Mock successful service calls
        mock_openai.models.list.return_value = Mock()
        mock_qdrant.get_collections.return_value = Mock()
        
        event = {}
        context = Mock()
        
        result = health_check_handler(event, context)
        
        assert result['statusCode'] == 200
        response_body = json.loads(result['body'])
        assert response_body['status'] == 'healthy'
        assert 'openai' in response_body['services']
        assert 'qdrant' in response_body['services']
    
    @patch('aws_lambda.handler.openai_client')
    @patch('aws_lambda.handler.qdrant_client')
    def test_health_check_handler_degraded(self, mock_qdrant, mock_openai):
        """Test health check handler when one service is unhealthy"""
        # Mock OpenAI failure
        mock_openai.models.list.side_effect = Exception("API Error")
        mock_qdrant.get_collections.return_value = Mock()
        
        event = {}
        context = Mock()
        
        result = health_check_handler(event, context)
        
        assert result['statusCode'] == 200
        response_body = json.loads(result['body'])
        assert response_body['status'] == 'degraded'
        assert 'unhealthy' in response_body['services']['openai']
        assert response_body['services']['qdrant'] == 'healthy'


class TestErrorHandling:
    """Test error handling scenarios"""
    
    def test_json_parsing_error(self):
        """Test handling of malformed JSON in request body"""
        event = {
            'httpMethod': 'POST',
            'body': 'invalid json'
        }
        context = Mock()
        
        result = lambda_handler(event, context)
        
        assert result['statusCode'] == 500
        response_body = json.loads(result['body'])
        assert response_body['status'] == 'error'


if __name__ == '__main__':
    pytest.main([__file__])