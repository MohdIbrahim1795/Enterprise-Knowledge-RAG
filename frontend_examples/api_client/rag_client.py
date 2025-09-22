"""
Python API Client Library for RAG Chatbot
Provides a reusable client library for integrating with the RAG system
"""

import json
import logging
import time
from typing import Dict, Any, List, Optional, Union
import requests
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import hashlib


# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class ChatMessage:
    """Represents a chat message"""
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class ChatSource:
    """Represents a source document for a chat response"""
    text: str
    source: str
    page: Optional[int] = None
    score: float = 0.0


@dataclass
class ChatResponse:
    """Represents a complete chat response"""
    answer: str
    conversation_id: str
    sources: List[ChatSource]
    processing_time: float
    cached: bool = False
    status: str = "success"
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChatResponse':
        """Create ChatResponse from API response dictionary"""
        sources = [
            ChatSource(**source) for source in data.get('sources', [])
        ]
        
        return cls(
            answer=data.get('answer', ''),
            conversation_id=data.get('conversation_id', ''),
            sources=sources,
            processing_time=data.get('processing_time', 0.0),
            cached=data.get('cached', False),
            status=data.get('status', 'success')
        )


class RAGAPIError(Exception):
    """Custom exception for RAG API errors"""
    
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class RAGAPIClient:
    """
    Python client library for RAG Chatbot API
    
    Provides high-level interface for interacting with RAG services,
    including chat functionality, health checks, and conversation management.
    """
    
    def __init__(
        self,
        api_url: str,
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        api_key: Optional[str] = None
    ):
        """
        Initialize RAG API client
        
        Args:
            api_url: Base URL of the RAG API service
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds
            api_key: Optional API key for authentication
        """
        self.api_url = api_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # Setup HTTP session
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'RAG-Python-Client/1.0'
        })
        
        if api_key:
            self.session.headers['Authorization'] = f'Bearer {api_key}'
        
        # Conversation management
        self._conversation_id: Optional[str] = None
        self._conversation_history: List[ChatMessage] = []
        
        logger.info(f"Initialized RAG API client for {self.api_url}")
    
    @property
    def conversation_id(self) -> Optional[str]:
        """Get current conversation ID"""
        return self._conversation_id
    
    @property
    def conversation_history(self) -> List[ChatMessage]:
        """Get conversation history"""
        return self._conversation_history.copy()
    
    def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> requests.Response:
        """
        Make HTTP request with retry logic
        
        Args:
            method: HTTP method
            endpoint: API endpoint (relative to base URL)
            data: Request payload (for POST/PUT)
            params: URL parameters (for GET)
            
        Returns:
            Response object
            
        Raises:
            RAGAPIError: If request fails after all retries
        """
        url = f"{self.api_url}/{endpoint.lstrip('/')}"
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                if method.upper() == 'GET':
                    response = self.session.get(url, params=params, timeout=self.timeout)
                elif method.upper() == 'POST':
                    response = self.session.post(url, json=data, timeout=self.timeout)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                # Check for HTTP errors
                if response.status_code >= 400:
                    error_data = None
                    try:
                        error_data = response.json()
                    except:
                        pass
                    
                    raise RAGAPIError(
                        f"HTTP {response.status_code}: {response.text}",
                        status_code=response.status_code,
                        response_data=error_data
                    )
                
                return response
                
            except requests.exceptions.RequestException as e:
                last_exception = e
                if attempt < self.max_retries:
                    logger.warning(f"Request failed (attempt {attempt + 1}/{self.max_retries + 1}): {e}")
                    time.sleep(self.retry_delay * (2 ** attempt))  # Exponential backoff
                else:
                    logger.error(f"Request failed after {self.max_retries + 1} attempts")
                    break
        
        raise RAGAPIError(f"Request failed: {last_exception}")
    
    def health_check(self) -> Dict[str, Any]:
        """
        Check service health
        
        Returns:
            Health status dictionary
            
        Raises:
            RAGAPIError: If health check fails
        """
        logger.debug("Performing health check")
        response = self._make_request('GET', '/health')
        return response.json()
    
    def is_healthy(self) -> bool:
        """
        Quick health check
        
        Returns:
            True if service is healthy, False otherwise
        """
        try:
            health_data = self.health_check()
            return health_data.get('status') in ['healthy', 'degraded']
        except:
            return False
    
    def chat(
        self,
        query: str,
        conversation_id: Optional[str] = None,
        max_results: int = 3,
        update_history: bool = True
    ) -> ChatResponse:
        """
        Send chat query to RAG system
        
        Args:
            query: User query text
            conversation_id: Optional conversation ID (uses current if None)
            max_results: Maximum number of source results
            update_history: Whether to update conversation history
            
        Returns:
            ChatResponse object
            
        Raises:
            RAGAPIError: If chat request fails
        """
        if not query.strip():
            raise ValueError("Query cannot be empty")
        
        # Use provided conversation_id or current one
        conv_id = conversation_id or self._conversation_id
        
        payload = {
            "query": query.strip(),
            "max_results": min(max_results, 10)  # Cap at 10
        }
        
        if conv_id:
            payload["conversation_id"] = conv_id
        
        logger.debug(f"Sending chat query: {query[:100]}...")
        
        response = self._make_request('POST', '/chat', data=payload)
        response_data = response.json()
        
        # Create response object
        chat_response = ChatResponse.from_dict(response_data)
        
        # Update conversation tracking
        if update_history:
            self._conversation_id = chat_response.conversation_id
            
            # Add user message
            self._conversation_history.append(
                ChatMessage(role='user', content=query)
            )
            
            # Add assistant response
            self._conversation_history.append(
                ChatMessage(role='assistant', content=chat_response.answer)
            )
        
        logger.debug(f"Received response (time: {chat_response.processing_time:.2f}s)")
        
        return chat_response
    
    def start_new_conversation(self) -> None:
        """Start a new conversation (clears conversation ID and history)"""
        logger.info("Starting new conversation")
        self._conversation_id = None
        self._conversation_history.clear()
    
    def get_conversation_summary(self) -> Dict[str, Any]:
        """
        Get summary of current conversation
        
        Returns:
            Dictionary with conversation metadata
        """
        return {
            'conversation_id': self._conversation_id,
            'message_count': len(self._conversation_history),
            'started_at': self._conversation_history[0].timestamp if self._conversation_history else None,
            'last_message_at': self._conversation_history[-1].timestamp if self._conversation_history else None
        }
    
    def export_conversation(self, format: str = 'json') -> Union[str, Dict]:
        """
        Export conversation history
        
        Args:
            format: Export format ('json', 'text', or 'dict')
            
        Returns:
            Conversation data in requested format
        """
        if format == 'dict':
            return {
                'conversation_id': self._conversation_id,
                'messages': [asdict(msg) for msg in self._conversation_history],
                'exported_at': datetime.now().isoformat()
            }
        elif format == 'json':
            return json.dumps(self.export_conversation('dict'), indent=2, default=str)
        elif format == 'text':
            lines = [f"Conversation ID: {self._conversation_id}", ""]
            for msg in self._conversation_history:
                timestamp = msg.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                lines.append(f"[{timestamp}] {msg.role.title()}: {msg.content}")
                lines.append("")
            return "\n".join(lines)
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def batch_chat(
        self, 
        queries: List[str],
        start_new_conversation: bool = True,
        delay_between_queries: float = 0.0
    ) -> List[ChatResponse]:
        """
        Send multiple queries in sequence
        
        Args:
            queries: List of query strings
            start_new_conversation: Whether to start fresh conversation
            delay_between_queries: Delay between queries in seconds
            
        Returns:
            List of ChatResponse objects
        """
        if start_new_conversation:
            self.start_new_conversation()
        
        responses = []
        
        for i, query in enumerate(queries):
            if i > 0 and delay_between_queries > 0:
                time.sleep(delay_between_queries)
            
            try:
                response = self.chat(query)
                responses.append(response)
                logger.debug(f"Completed query {i + 1}/{len(queries)}")
            except Exception as e:
                logger.error(f"Failed query {i + 1}/{len(queries)}: {e}")
                # Create error response
                error_response = ChatResponse(
                    answer=f"Error: {str(e)}",
                    conversation_id=self._conversation_id or '',
                    sources=[],
                    processing_time=0.0,
                    status='error'
                )
                responses.append(error_response)
        
        return responses
    
    def search_similar(
        self,
        query: str,
        max_results: int = 5,
        min_score: float = 0.0
    ) -> List[ChatSource]:
        """
        Search for similar documents (if supported by API)
        
        Args:
            query: Search query
            max_results: Maximum results to return
            min_score: Minimum similarity score
            
        Returns:
            List of ChatSource objects
        """
        # This would require a dedicated search endpoint
        # For now, extract sources from a chat response
        response = self.chat(query, update_history=False)
        return [
            source for source in response.sources 
            if source.score >= min_score
        ][:max_results]
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup resources"""
        self.session.close()
        logger.debug("Closed RAG API client session")


# Convenience functions
def create_client(api_url: str, **kwargs) -> RAGAPIClient:
    """
    Create and return a RAG API client
    
    Args:
        api_url: RAG service URL
        **kwargs: Additional client parameters
        
    Returns:
        RAGAPIClient instance
    """
    return RAGAPIClient(api_url, **kwargs)


def quick_query(api_url: str, query: str, **kwargs) -> str:
    """
    Quick single query without maintaining conversation state
    
    Args:
        api_url: RAG service URL  
        query: Query text
        **kwargs: Additional parameters for client or chat
        
    Returns:
        Answer text
    """
    with create_client(api_url, **kwargs) as client:
        response = client.chat(query, update_history=False)
        return response.answer


# Example usage
if __name__ == "__main__":
    import sys
    
    # Basic usage example
    API_URL = "http://localhost:8000"
    
    # Create client
    client = RAGAPIClient(API_URL)
    
    try:
        # Health check
        if not client.is_healthy():
            print("❌ Service is not healthy")
            sys.exit(1)
        
        print("✅ Service is healthy")
        
        # Interactive chat
        print("\n🤖 RAG API Client - Interactive Mode")
        print("Type 'quit' to exit, 'new' for new conversation\n")
        
        while True:
            try:
                query = input("Query: ").strip()
                
                if query.lower() == 'quit':
                    break
                elif query.lower() == 'new':
                    client.start_new_conversation()
                    print("🔄 Started new conversation")
                    continue
                elif not query:
                    continue
                
                response = client.chat(query)
                
                print(f"\n🤖 Answer: {response.answer}")
                
                if response.sources:
                    print(f"\n📚 Sources ({len(response.sources)}):")
                    for i, source in enumerate(response.sources, 1):
                        print(f"  {i}. {source.source} (score: {source.score:.2f})")
                
                print(f"\n⏱️ Processing time: {response.processing_time:.2f}s")
                if response.cached:
                    print("💾 (cached)")
                
                print("-" * 50)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"❌ Error: {e}")
        
        # Show conversation summary
        summary = client.get_conversation_summary()
        if summary['message_count'] > 0:
            print(f"\n📊 Conversation Summary:")
            print(f"  Messages: {summary['message_count']}")
            print(f"  Started: {summary['started_at']}")
            print(f"  Last message: {summary['last_message_at']}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)