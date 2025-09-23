"""
Lambda function to generate OpenAI embeddings for text chunks
"""
import json
import os
import logging
import time
from typing import Dict, Any, List
import openai
from openai import OpenAI

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Generates OpenAI embeddings for text chunks.
    
    Args:
        event: Contains text chunks and metadata
        context: Lambda context object
        
    Returns:
        Dict containing chunks with their embeddings
    """
    try:
        # Initialize OpenAI client
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key or api_key == 'your_openai_api_key_here':
            raise Exception("OpenAI API key not configured")
        
        client = OpenAI(api_key=api_key)
        
        # Configuration
        embedding_model = os.environ.get('OPENAI_EMBEDDING_MODEL', 'text-embedding-3-small')
        batch_size = int(os.environ.get('EMBEDDING_BATCH_SIZE', '20'))  # Process in batches
        
        chunks = event['chunks']
        document_key = event['key']
        filename = event['filename']
        
        logger.info(f"Generating embeddings for {len(chunks)} chunks from {filename}")
        logger.info(f"Using model: {embedding_model}, batch size: {batch_size}")
        
        # Process chunks in batches to avoid rate limits and timeout issues
        chunks_with_embeddings = []
        total_batches = (len(chunks) + batch_size - 1) // batch_size
        
        for batch_idx in range(0, len(chunks), batch_size):
            batch_chunks = chunks[batch_idx:batch_idx + batch_size]
            batch_num = (batch_idx // batch_size) + 1
            
            logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch_chunks)} chunks)")
            
            try:
                # Extract text from chunks for embedding
                texts_to_embed = [chunk['text'] for chunk in batch_chunks]
                
                # Generate embeddings for the batch
                response = client.embeddings.create(
                    input=texts_to_embed,
                    model=embedding_model
                )
                
                # Add embeddings to chunks
                for i, chunk in enumerate(batch_chunks):
                    embedding = response.data[i].embedding
                    
                    # Validate embedding
                    if len(embedding) != 1536 and embedding_model == 'text-embedding-3-small':
                        logger.warning(f"Unexpected embedding dimension: {len(embedding)}")
                    
                    chunk_with_embedding = {
                        **chunk,
                        'embedding': embedding,
                        'embedding_model': embedding_model,
                        'embedding_dimension': len(embedding)
                    }
                    
                    chunks_with_embeddings.append(chunk_with_embedding)
                
                # Add small delay between batches to respect rate limits
                if batch_num < total_batches:
                    time.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"Error processing batch {batch_num}: {str(e)}")
                # For now, raise the exception to fail fast
                # In production, you might want to implement partial failure handling
                raise Exception(f"Embedding generation failed at batch {batch_num}: {str(e)}")
        
        logger.info(f"Successfully generated embeddings for all {len(chunks_with_embeddings)} chunks")
        
        # Calculate some statistics
        total_tokens = sum(len(chunk['text'].split()) for chunk in chunks)
        avg_embedding_dimension = sum(len(chunk['embedding']) for chunk in chunks_with_embeddings) / len(chunks_with_embeddings)
        
        result = {
            'key': document_key,
            'filename': filename,
            'chunks': chunks_with_embeddings,
            'totalChunks': len(chunks_with_embeddings),
            'embeddingStats': {
                'model': embedding_model,
                'averageDimension': int(avg_embedding_dimension),
                'totalTokensApprox': total_tokens,
                'batchesProcessed': total_batches
            },
            'metadata': event.get('metadata', {})
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Error in embedding generation lambda: {str(e)}")
        raise Exception(f"Embedding generation failed: {str(e)}")


def validate_openai_config() -> bool:
    """
    Validate OpenAI configuration and connectivity.
    
    Returns:
        True if configuration is valid, False otherwise
    """
    try:
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key or api_key == 'your_openai_api_key_here':
            logger.error("OpenAI API key not configured")
            return False
        
        # Test with a simple embedding request
        client = OpenAI(api_key=api_key)
        response = client.embeddings.create(
            input=["test"],
            model="text-embedding-3-small"
        )
        
        if response.data and len(response.data) > 0:
            logger.info(f"OpenAI API validation successful. Embedding dimension: {len(response.data[0].embedding)}")
            return True
        else:
            logger.error("OpenAI API returned empty response")
            return False
            
    except Exception as e:
        logger.error(f"OpenAI API validation failed: {str(e)}")
        return False


def estimate_tokens(text: str) -> int:
    """
    Rough estimation of token count for OpenAI pricing calculation.
    
    Args:
        text: Input text
        
    Returns:
        Estimated token count
    """
    # Rough approximation: 1 token ≈ 4 characters for English text
    return len(text) // 4


# For local testing
if __name__ == "__main__":
    # Set test environment variables
    os.environ['OPENAI_API_KEY'] = 'your-test-key-here'  # Replace with actual key for testing
    os.environ['OPENAI_EMBEDDING_MODEL'] = 'text-embedding-3-small'
    os.environ['EMBEDDING_BATCH_SIZE'] = '5'
    
    # Test event with sample chunks
    test_chunks = [
        {
            'id': 'chunk-1',
            'text': 'This is the first chunk of text to be embedded.',
            'chunk_index': 0,
            'character_count': 47,
            'metadata': {
                'source': 'test.pdf',
                'filename': 'test.pdf',
                'chunk_index': 0
            }
        },
        {
            'id': 'chunk-2',
            'text': 'This is the second chunk with different content for embedding.',
            'chunk_index': 1,
            'character_count': 62,
            'metadata': {
                'source': 'test.pdf',
                'filename': 'test.pdf',
                'chunk_index': 1
            }
        }
    ]
    
    test_event = {
        'key': 'source/test-document.pdf',
        'filename': 'test-document.pdf',
        'chunks': test_chunks,
        'totalChunks': len(test_chunks),
        'metadata': {
            'originalSize': 12345,
            'extractionTimestamp': 'test-run'
        }
    }
    
    try:
        # Validate config first
        if not validate_openai_config():
            print("OpenAI configuration validation failed")
        else:
            result = lambda_handler(test_event, None)
            print(json.dumps({
                **result,
                'chunks': [
                    {**chunk, 'embedding': f"[{len(chunk['embedding'])} dimensions]"}
                    for chunk in result['chunks']
                ]
            }, indent=2))
            
    except Exception as e:
        print(f"Error: {e}")