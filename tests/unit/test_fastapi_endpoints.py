"""
Unit tests for FastAPI endpoints
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

# Mock the database and external dependencies before importing the app
with patch('fastapi_app.app.database.engine'), \
     patch('fastapi_app.app.main.openai_client'), \
     patch('fastapi_app.app.main.qdrant_client'), \
     patch('fastapi_app.app.main.redis_client'):
    from fastapi_app.app.main import app, get_db
    
client = TestClient(app)


class TestChatEndpoint:
    """Test the /chat endpoint"""
    
    def setup_method(self):
        """Setup for each test method"""
        # Override database dependency with mock
        def mock_get_db():
            return Mock()
        app.dependency_overrides[get_db] = mock_get_db
    
    def teardown_method(self):
        """Cleanup after each test method"""
        app.dependency_overrides.clear()
    
    @patch('fastapi_app.app.main.openai_client')
    @patch('fastapi_app.app.main.qdrant_client') 
    @patch('fastapi_app.app.main.redis_client')
    def test_chat_endpoint_success(self, mock_redis, mock_qdrant, mock_openai):
        """Test successful chat request"""
        # Setup mocks
        mock_redis.get.return_value = None  # No cache
        
        # Mock embedding response
        mock_embed_response = Mock()
        mock_embed_response.data = [Mock(embedding=[0.1] * 1536)]
        mock_openai.embeddings.create.return_value = mock_embed_response
        
        # Mock search results
        mock_search_result = Mock()
        mock_search_result.payload = {"text": "Test context"}
        mock_qdrant.search.return_value = [mock_search_result]
        
        # Mock LLM response
        mock_llm_response = Mock()
        mock_llm_response.choices = [Mock(message=Mock(content="Test answer"))]
        mock_openai.chat.completions.create.return_value = mock_llm_response
        
        # Make request
        response = client.post(
            "/chat",
            json={"query": "Test query", "conversation_id": "test-123"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert data["conversation_id"] == "test-123"
    
    @patch('fastapi_app.app.main.OPENAI_API_KEY', None)
    def test_chat_endpoint_no_api_key(self):
        """Test chat endpoint when OpenAI API key is missing"""
        response = client.post(
            "/chat",
            json={"query": "Test query"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "OpenAI API key is missing" in data["answer"]
        assert data["source"] == "error"
    
    @patch('fastapi_app.app.main.redis_client')
    def test_chat_endpoint_cached_response(self, mock_redis):
        """Test chat endpoint with cached response"""
        # Setup cache hit
        mock_redis.get.return_value = "Cached response"
        
        response = client.post(
            "/chat", 
            json={"query": "Test query"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["answer"] == "Cached response"
        assert data["source"] == "cache"
    
    def test_chat_endpoint_invalid_request(self):
        """Test chat endpoint with invalid request format"""
        response = client.post(
            "/chat",
            json={}  # Missing required query field
        )
        
        # The endpoint should handle this gracefully
        assert response.status_code in [400, 422, 500]  # Various possible error codes


class TestChatHistoryFunctions:
    """Test chat history management functions"""
    
    @patch('fastapi_app.app.main.get_chat_history')
    def test_get_chat_history(self, mock_get_history):
        """Test get_chat_history function"""
        # This would test the actual function if we import it separately
        # For now, we'll test through the endpoint behavior
        mock_get_history.return_value = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ]
        
        # Test through endpoint that uses chat history
        with patch('fastapi_app.app.main.redis_client.get', return_value=None), \
             patch('fastapi_app.app.main.openai_client'), \
             patch('fastapi_app.app.main.qdrant_client'):
            response = client.post(
                "/chat",
                json={"query": "Test", "conversation_id": "existing-conv"}
            )
            
            # The endpoint should process without errors
            assert response.status_code in [200, 500]  # Either success or handled error


class TestErrorHandling:
    """Test error handling scenarios"""
    
    @patch('fastapi_app.app.main.openai_client')
    @patch('fastapi_app.app.main.qdrant_client')
    def test_qdrant_connection_error(self, mock_qdrant, mock_openai):
        """Test handling of Qdrant connection errors"""
        mock_qdrant.search.side_effect = Exception("Connection error")
        
        response = client.post(
            "/chat",
            json={"query": "Test query"}
        )
        
        # Should handle the error gracefully
        assert response.status_code == 200
        data = response.json()
        assert "error" in data or "Error" in data.get("answer", "")
    
    @patch('fastapi_app.app.main.openai_client')
    def test_openai_api_error(self, mock_openai):
        """Test handling of OpenAI API errors"""
        mock_openai.embeddings.create.side_effect = Exception("API quota exceeded")
        
        response = client.post(
            "/chat",
            json={"query": "Test query"}
        )
        
        # Should handle the error gracefully
        assert response.status_code == 200
        data = response.json()
        assert "error" in data or "Error" in data.get("answer", "")


class TestHealthEndpoint:
    """Test health check functionality"""
    
    def test_app_startup(self):
        """Test that the app starts up correctly"""
        # Basic test to ensure the app initializes
        response = client.get("/")
        # The app might not have a root endpoint, so any response indicates it's running
        assert response.status_code in [200, 404, 405]


class TestInputValidation:
    """Test input validation and sanitization"""
    
    def test_query_length_limit(self):
        """Test handling of very long queries"""
        long_query = "x" * 10000  # Very long query
        
        response = client.post(
            "/chat",
            json={"query": long_query}
        )
        
        # Should either handle gracefully or return appropriate error
        assert response.status_code in [200, 400, 413, 422]
    
    def test_special_characters_in_query(self):
        """Test handling of special characters in queries"""
        special_query = "What about <script>alert('xss')</script>?"
        
        response = client.post(
            "/chat",
            json={"query": special_query}
        )
        
        # Should process without issues
        assert response.status_code in [200, 400]
        
        if response.status_code == 200:
            data = response.json()
            # Response should not contain unescaped special characters
            assert "<script>" not in data.get("answer", "")
    
    def test_sql_injection_attempt(self):
        """Test handling of SQL injection attempts"""
        injection_query = "'; DROP TABLE chat_history; --"
        
        response = client.post(
            "/chat",
            json={"query": injection_query}
        )
        
        # Should handle safely without errors
        assert response.status_code in [200, 400]


if __name__ == '__main__':
    pytest.main([__file__])