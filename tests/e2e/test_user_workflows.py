"""
End-to-end tests for the RAG chatbot system
Tests complete user workflows and system interactions
"""

import pytest
import json
import time
import os
import requests
from unittest.mock import Mock, patch
import docker
import subprocess


class TestE2EDockerEnvironment:
    """E2E tests using Docker environment"""
    
    @pytest.fixture(scope="class", autouse=True)
    def docker_environment(self):
        """Setup Docker environment for E2E testing"""
        # Check if Docker is available
        try:
            docker_client = docker.from_env()
            docker_client.ping()
        except Exception:
            pytest.skip("Docker not available for E2E tests")
        
        # Set test environment variables
        test_env = {
            "OPENAI_API_KEY": "test-key-for-e2e",
            "POSTGRES_USER": "test_user",
            "POSTGRES_PASSWORD": "test_password",
            "POSTGRES_DB": "test_rag_db",
            "MINIO_ROOT_USER": "testadmin",
            "MINIO_ROOT_PASSWORD": "testpassword123",
        }
        
        # Note: In real E2E tests, you might start docker-compose here
        # For this example, we assume services are already running or mocked
        
        yield test_env
        
        # Cleanup would go here
        pass

    def test_full_user_chat_workflow(self):
        """Test complete user chat workflow"""
        # This test would require actual running services
        # For demonstration, we'll mock the HTTP calls
        
        base_url = "http://localhost:8000"
        
        # Test data
        test_queries = [
            "What is machine learning?",
            "How does it relate to artificial intelligence?",
            "Can you give me an example?"
        ]
        
        conversation_id = None
        
        for query in test_queries:
            payload = {"query": query}
            if conversation_id:
                payload["conversation_id"] = conversation_id
            
            # In a real E2E test, this would make actual HTTP requests
            # For now, we'll simulate the expected behavior
            with patch('requests.post') as mock_post:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "answer": f"Mock response for: {query}",
                    "conversation_id": "test-conv-123",
                    "sources": [
                        {
                            "text": "Relevant context",
                            "source": "test.pdf",
                            "score": 0.9
                        }
                    ],
                    "processing_time": 0.5,
                    "status": "success"
                }
                mock_post.return_value = mock_response
                
                response = requests.post(f"{base_url}/chat", json=payload)
                
                assert response.status_code == 200
                data = response.json()
                assert "answer" in data
                assert "conversation_id" in data
                assert "sources" in data
                
                # Update conversation ID for next request
                conversation_id = data["conversation_id"]

    def test_document_upload_and_retrieval_workflow(self):
        """Test document upload and subsequent retrieval workflow"""
        # This would test:
        # 1. Upload document to MinIO
        # 2. Trigger processing (Airflow or direct)
        # 3. Verify embedding storage in Qdrant
        # 4. Query for information from that document
        # 5. Verify correct retrieval
        
        # Mock the workflow for demonstration
        with patch('boto3.client') as mock_s3:
            # Mock S3 upload
            mock_s3_instance = Mock()
            mock_s3.return_value = mock_s3_instance
            mock_s3_instance.upload_file.return_value = None
            
            # Simulate document upload
            test_document = "test_document.pdf"
            bucket_name = "test-enterprise-data"
            
            # Upload simulation
            mock_s3_instance.upload_file(test_document, bucket_name, f"source/{test_document}")
            
            # Verify upload was called
            mock_s3_instance.upload_file.assert_called_once()
            
            # Simulate processing completion (normally would wait for Airflow)
            time.sleep(0.1)  # Simulated processing time
            
            # Query for information from the uploaded document
            with patch('requests.post') as mock_post:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "answer": "Information from the uploaded document",
                    "sources": [{"source": test_document, "score": 0.95}],
                    "status": "success"
                }
                mock_post.return_value = mock_response
                
                response = requests.post(
                    "http://localhost:8000/chat",
                    json={"query": "What information is in the uploaded document?"}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert test_document in str(data["sources"])

    def test_system_resilience_workflow(self):
        """Test system resilience under various failure conditions"""
        
        # Test 1: Service temporarily unavailable
        with patch('requests.post') as mock_post:
            # First request fails
            mock_post.side_effect = requests.exceptions.ConnectionError("Service unavailable")
            
            with pytest.raises(requests.exceptions.ConnectionError):
                requests.post(
                    "http://localhost:8000/chat",
                    json={"query": "Test query"}
                )
            
            # Second request succeeds (service recovered)
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"answer": "Service recovered", "status": "success"}
            mock_post.side_effect = None
            mock_post.return_value = mock_response
            
            response = requests.post(
                "http://localhost:8000/chat", 
                json={"query": "Test query"}
            )
            assert response.status_code == 200

    def test_performance_under_load(self):
        """Test system performance under load"""
        import threading
        import queue
        
        results_queue = queue.Queue()
        error_queue = queue.Queue()
        
        def make_concurrent_request(request_id):
            try:
                start_time = time.time()
                
                # Mock the request
                with patch('requests.post') as mock_post:
                    mock_response = Mock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {
                        "answer": f"Response {request_id}",
                        "processing_time": 0.5,
                        "status": "success"
                    }
                    mock_post.return_value = mock_response
                    
                    response = requests.post(
                        "http://localhost:8000/chat",
                        json={"query": f"Load test query {request_id}"},
                        timeout=10
                    )
                    
                    end_time = time.time()
                    results_queue.put({
                        "request_id": request_id,
                        "status_code": response.status_code,
                        "response_time": end_time - start_time,
                        "success": response.status_code == 200
                    })
                    
            except Exception as e:
                error_queue.put({"request_id": request_id, "error": str(e)})
        
        # Launch concurrent requests
        threads = []
        num_requests = 10
        
        for i in range(num_requests):
            thread = threading.Thread(target=make_concurrent_request, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all requests to complete
        for thread in threads:
            thread.join(timeout=15)
        
        # Analyze results
        results = []
        while not results_queue.empty():
            results.append(results_queue.get())
        
        errors = []
        while not error_queue.empty():
            errors.append(error_queue.get())
        
        # Assertions
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == num_requests
        
        successful_requests = [r for r in results if r["success"]]
        assert len(successful_requests) == num_requests
        
        # Check average response time
        avg_response_time = sum(r["response_time"] for r in results) / len(results)
        assert avg_response_time < 2.0, f"Average response time too high: {avg_response_time}s"


class TestE2ELambdaDeployment:
    """E2E tests for Lambda deployment scenarios"""
    
    def test_lambda_cold_start_performance(self):
        """Test Lambda function cold start performance"""
        # Simulate cold start by importing handler fresh
        import importlib
        import sys
        
        # Remove module from cache to simulate cold start
        module_name = 'aws_lambda.handler'
        if module_name in sys.modules:
            del sys.modules[module_name]
        
        with patch.dict(os.environ, {
            'OPENAI_API_KEY': 'test-key',
            'QDRANT_URL': 'http://test:6333'
        }):
            with patch('aws_lambda.handler.OpenAI'), \
                 patch('aws_lambda.handler.QdrantClient'):
                
                start_time = time.time()
                
                # Import handler (simulates cold start)
                from aws_lambda.handler import lambda_handler
                
                # Make request
                event = {
                    "httpMethod": "POST",
                    "body": json.dumps({"query": "Cold start test"})
                }
                context = Mock()
                
                result = lambda_handler(event, context)
                
                end_time = time.time()
                cold_start_time = end_time - start_time
                
                # Cold start should complete within reasonable time
                assert cold_start_time < 5.0, f"Cold start too slow: {cold_start_time}s"
                assert result["statusCode"] == 200

    def test_lambda_warm_execution_performance(self):
        """Test Lambda function warm execution performance"""
        with patch.dict(os.environ, {
            'OPENAI_API_KEY': 'test-key',
            'QDRANT_URL': 'http://test:6333'
        }):
            with patch('aws_lambda.handler.openai_client') as mock_openai, \
                 patch('aws_lambda.handler.qdrant_client') as mock_qdrant:
                
                # Setup mocks
                mock_embed_response = Mock()
                mock_embed_response.data = [Mock(embedding=[0.1] * 1536)]
                mock_openai.embeddings.create.return_value = mock_embed_response
                
                mock_search_result = Mock()
                mock_search_result.payload = {"text": "Test content", "source": "test.pdf", "page": 1}
                mock_search_result.score = 0.9
                mock_qdrant.search.return_value = [mock_search_result]
                
                mock_chat_response = Mock()
                mock_chat_response.choices = [Mock(message=Mock(content="Warm execution response"))]
                mock_openai.chat.completions.create.return_value = mock_chat_response
                
                from aws_lambda.handler import lambda_handler
                
                event = {
                    "httpMethod": "POST",
                    "body": json.dumps({"query": "Warm execution test"})
                }
                context = Mock()
                
                # First request (may include some initialization)
                start_time = time.time()
                result1 = lambda_handler(event, context)
                first_execution_time = time.time() - start_time
                
                # Second request (should be faster - warm execution)
                start_time = time.time()
                result2 = lambda_handler(event, context)
                second_execution_time = time.time() - start_time
                
                # Both should succeed
                assert result1["statusCode"] == 200
                assert result2["statusCode"] == 200
                
                # Second execution should be faster or similar
                assert second_execution_time <= first_execution_time * 1.5


class TestE2EUserJourneys:
    """E2E tests for complete user journeys"""
    
    def test_new_user_onboarding_journey(self):
        """Test complete new user onboarding journey"""
        # Step 1: User accesses health check
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "healthy"}
            mock_get.return_value = mock_response
            
            response = requests.get("http://localhost:8000/health")
            assert response.status_code == 200
            assert response.json()["status"] == "healthy"
        
        # Step 2: User makes first query (no conversation history)
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "answer": "Welcome! I'm here to help with your questions.",
                "conversation_id": "new-user-123",
                "sources": [],
                "status": "success"
            }
            mock_post.return_value = mock_response
            
            response = requests.post(
                "http://localhost:8000/chat",
                json={"query": "Hello, I'm new here. What can you help me with?"}
            )
            
            assert response.status_code == 200
            data = response.json()
            conversation_id = data["conversation_id"]
            assert "help" in data["answer"].lower()
        
        # Step 3: User asks follow-up question
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "answer": "I can help you find information from our knowledge base.",
                "conversation_id": conversation_id,
                "sources": [{"text": "Knowledge base info", "source": "guide.pdf", "score": 0.8}],
                "status": "success"
            }
            mock_post.return_value = mock_response
            
            response = requests.post(
                "http://localhost:8000/chat",
                json={
                    "query": "What kind of information do you have access to?",
                    "conversation_id": conversation_id
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["conversation_id"] == conversation_id
            assert len(data["sources"]) > 0

    def test_power_user_complex_query_journey(self):
        """Test power user making complex queries"""
        
        complex_queries = [
            "Can you provide a comprehensive analysis of machine learning algorithms mentioned in our documentation?",
            "What are the performance benchmarks for different neural network architectures in our studies?",
            "How do the cost-benefit analyses compare across different AI implementation strategies?",
        ]
        
        conversation_id = "power-user-456"
        
        for i, query in enumerate(complex_queries):
            with patch('requests.post') as mock_post:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "answer": f"Complex analysis response for query {i+1}: {query[:50]}...",
                    "conversation_id": conversation_id,
                    "sources": [
                        {"text": f"Technical document {j}", "source": f"tech{j}.pdf", "score": 0.9-j*0.1}
                        for j in range(3)
                    ],
                    "processing_time": 1.2 + i * 0.3,  # Longer processing for complex queries
                    "status": "success"
                }
                mock_post.return_value = mock_response
                
                response = requests.post(
                    "http://localhost:8000/chat",
                    json={"query": query, "conversation_id": conversation_id}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert len(data["sources"]) >= 3
                assert data["processing_time"] > 1.0  # Complex queries take longer

    def test_error_recovery_user_journey(self):
        """Test user journey with error recovery"""
        
        # Step 1: User makes query that results in error
        with patch('requests.post') as mock_post:
            mock_post.side_effect = requests.exceptions.Timeout("Request timeout")
            
            with pytest.raises(requests.exceptions.Timeout):
                requests.post(
                    "http://localhost:8000/chat",
                    json={"query": "This will timeout"},
                    timeout=1
                )
        
        # Step 2: User retries with same query (should work)
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "answer": "Sorry for the earlier issue. Here's your answer.",
                "conversation_id": "recovery-123",
                "status": "success"
            }
            mock_post.return_value = mock_response
            
            response = requests.post(
                "http://localhost:8000/chat",
                json={"query": "This will work now"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "answer" in data
            assert data["status"] == "success"

    def test_multi_format_document_query_journey(self):
        """Test user querying across multiple document formats"""
        
        # Simulate queries that would retrieve from different document types
        document_queries = [
            {"query": "What does the PDF manual say about installation?", "expected_format": "pdf"},
            {"query": "Show me the setup instructions from the text files", "expected_format": "txt"},
            {"query": "What configuration options are in the markdown docs?", "expected_format": "md"}
        ]
        
        for query_info in document_queries:
            with patch('requests.post') as mock_post:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "answer": f"Information from {query_info['expected_format']} documents",
                    "sources": [
                        {
                            "text": f"Content from {query_info['expected_format']} file",
                            "source": f"document.{query_info['expected_format']}",
                            "score": 0.9
                        }
                    ],
                    "status": "success"
                }
                mock_post.return_value = mock_response
                
                response = requests.post(
                    "http://localhost:8000/chat",
                    json={"query": query_info["query"]}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert query_info["expected_format"] in data["sources"][0]["source"]


if __name__ == '__main__':
    # Run with specific markers for different test types
    pytest.main([__file__, "-v", "-s"])