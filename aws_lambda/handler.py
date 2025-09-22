"""
AWS Lambda Handler for RAG Chatbot
Provides serverless chat functionality with document retrieval and LLM response generation.
"""

import json
import os
import logging
import boto3
import hashlib
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

# Third-party imports
try:
    from openai import OpenAI
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qdrant_models
except ImportError as e:
    logging.error(f"Required dependencies not available: {e}")
    raise

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "enterprise-knowledge-base")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-3.5-turbo")
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "350"))
SIMILARITY_THRESHOLD = float(os.environ.get("SIMILARITY_THRESHOLD", "0.7"))

# Initialize clients (done at module level for Lambda container reuse)
openai_client = None
qdrant_client = None

if OPENAI_API_KEY:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)

if QDRANT_URL:
    qdrant_client = QdrantClient(url=QDRANT_URL)


@dataclass
class ChatRequest:
    """Data class for chat request validation"""
    query: str
    conversation_id: Optional[str] = None
    max_results: int = 3
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChatRequest':
        """Create ChatRequest from dictionary with validation"""
        query = data.get('query', '').strip()
        if not query:
            raise ValueError("Query cannot be empty")
        
        return cls(
            query=query,
            conversation_id=data.get('conversation_id'),
            max_results=min(int(data.get('max_results', 3)), 10)  # Cap at 10
        )


@dataclass
class ChatResponse:
    """Data class for standardized chat response"""
    answer: str
    conversation_id: str
    sources: List[Dict[str, Any]]
    processing_time: float
    cached: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'answer': self.answer,
            'conversation_id': self.conversation_id,
            'sources': self.sources,
            'processing_time': self.processing_time,
            'cached': self.cached,
            'status': 'success'
        }


class RAGService:
    """Service class for RAG operations"""
    
    def __init__(self):
        if not openai_client:
            raise ValueError("OpenAI client not initialized. Check OPENAI_API_KEY.")
        if not qdrant_client:
            raise ValueError("Qdrant client not initialized. Check QDRANT_URL.")
        
        self.openai_client = openai_client
        self.qdrant_client = qdrant_client
    
    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for given text"""
        try:
            response = self.openai_client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise
    
    def search_documents(self, query_embedding: List[float], limit: int = 3) -> List[Dict[str, Any]]:
        """Search for relevant documents using vector similarity"""
        try:
            search_results = self.qdrant_client.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_embedding,
                limit=limit,
                score_threshold=SIMILARITY_THRESHOLD
            )
            
            sources = []
            for result in search_results:
                source = {
                    'text': result.payload.get('text', ''),
                    'source': result.payload.get('source', 'unknown'),
                    'page': result.payload.get('page'),
                    'score': float(result.score)
                }
                sources.append(source)
            
            return sources
            
        except Exception as e:
            logger.error(f"Error searching documents: {e}")
            raise
    
    def generate_response(self, query: str, context: str) -> str:
        """Generate LLM response based on query and context"""
        prompt = f"""You are an expert Q&A assistant. Answer the user's question based only on the provided context. 
If the answer is not in the context, say you don't have enough information to answer the question.
Be concise but comprehensive in your response.

<context>
{context}
</context>

Question: {query}"""
        
        try:
            response = self.openai_client.chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=MAX_TOKENS,
                temperature=0.1
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error generating LLM response: {e}")
            raise
    
    def process_chat_request(self, request: ChatRequest) -> ChatResponse:
        """Process complete chat request"""
        import time
        start_time = time.time()
        
        try:
            # Generate embedding for query
            query_embedding = self.generate_embedding(request.query)
            
            # Search for relevant documents
            sources = self.search_documents(query_embedding, request.max_results)
            
            if not sources:
                answer = "I don't have enough information in my knowledge base to answer your question."
            else:
                # Combine context from sources
                context = "\n\n".join([source['text'] for source in sources])
                answer = self.generate_response(request.query, context)
            
            processing_time = time.time() - start_time
            
            # Generate conversation ID if not provided
            conversation_id = request.conversation_id or hashlib.md5(
                f"{request.query}{start_time}".encode()
            ).hexdigest()[:12]
            
            return ChatResponse(
                answer=answer,
                conversation_id=conversation_id,
                sources=sources,
                processing_time=processing_time
            )
            
        except Exception as e:
            logger.error(f"Error processing chat request: {e}")
            raise


# Global service instance (reused across Lambda invocations)
rag_service = None


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler for RAG chat functionality
    
    Expected event format:
    {
        "body": json_string_containing_chat_request,
        "httpMethod": "POST",
        "headers": {...}
    }
    """
    global rag_service
    
    try:
        # Initialize service if not already done
        if not rag_service:
            rag_service = RAGService()
        
        # Handle CORS preflight
        if event.get('httpMethod') == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'POST, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
                },
                'body': json.dumps({'message': 'CORS preflight successful'})
            }
        
        # Parse request body
        if isinstance(event.get('body'), str):
            body = json.loads(event['body'])
        else:
            body = event.get('body', {})
        
        # Validate request
        try:
            chat_request = ChatRequest.from_dict(body)
        except ValueError as e:
            return {
                'statusCode': 400,
                'headers': {'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({
                    'error': str(e),
                    'status': 'error'
                })
            }
        
        # Process chat request
        response = rag_service.process_chat_request(chat_request)
        
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps(response.to_dict())
        }
        
    except Exception as e:
        logger.error(f"Lambda handler error: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'error': 'Internal server error',
                'status': 'error',
                'message': str(e) if os.environ.get('DEBUG') else 'An error occurred processing your request'
            })
        }


def document_ingest_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler for document ingestion
    Triggered by S3 events when new documents are uploaded
    """
    try:
        # This would handle S3 events and trigger document processing
        # For now, return a placeholder response
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Document ingestion handler triggered',
                'event': event
            })
        }
    except Exception as e:
        logger.error(f"Document ingest handler error: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Document ingestion failed',
                'message': str(e)
            })
        }


def health_check_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Health check handler for monitoring"""
    try:
        # Basic health checks
        health_status = {
            'status': 'healthy',
            'timestamp': int(time.time()),
            'services': {}
        }
        
        # Check OpenAI API
        if openai_client:
            try:
                # Simple API call to test connectivity
                openai_client.models.list()
                health_status['services']['openai'] = 'healthy'
            except Exception as e:
                health_status['services']['openai'] = f'unhealthy: {str(e)}'
                health_status['status'] = 'degraded'
        
        # Check Qdrant
        if qdrant_client:
            try:
                qdrant_client.get_collections()
                health_status['services']['qdrant'] = 'healthy'
            except Exception as e:
                health_status['services']['qdrant'] = f'unhealthy: {str(e)}'
                health_status['status'] = 'degraded'
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps(health_status)
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'status': 'unhealthy',
                'error': str(e)
            })
        }


if __name__ == "__main__":
    # For local testing
    import time
    
    test_event = {
        'httpMethod': 'POST',
        'body': json.dumps({
            'query': 'What is the main topic of the documents?',
            'max_results': 3
        })
    }
    
    class MockContext:
        def __init__(self):
            self.function_name = "test-function"
            self.memory_limit_in_mb = 512
    
    context = MockContext()
    result = lambda_handler(test_event, context)
    print("Test result:", json.dumps(result, indent=2))