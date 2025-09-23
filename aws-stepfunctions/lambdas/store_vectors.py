"""
Lambda function to store embeddings in Qdrant vector database
"""
import json
import os
import logging
import time
from typing import Dict, Any, List
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import ResponseHandlingException

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Stores embeddings in Qdrant vector database.
    
    Args:
        event: Contains chunks with embeddings and metadata
        context: Lambda context object
        
    Returns:
        Dict containing storage results and statistics
    """
    try:
        # Configuration from environment variables
        qdrant_host = os.environ.get('QDRANT_HOST', 'qdrant')
        qdrant_port = int(os.environ.get('QDRANT_PORT', '6333'))
        collection_name = os.environ.get('COLLECTION_NAME', 'enterprise-knowledge-base')
        batch_size = int(os.environ.get('VECTOR_BATCH_SIZE', '50'))
        
        chunks = event['chunks']
        document_key = event['key']
        filename = event['filename']
        
        logger.info(f"Storing {len(chunks)} vectors in Qdrant for document {filename}")
        logger.info(f"Qdrant: {qdrant_host}:{qdrant_port}, Collection: {collection_name}")
        
        # Initialize Qdrant client
        qdrant_client = QdrantClient(host=qdrant_host, port=qdrant_port)
        
        # Verify connection and collection exists
        try:
            collections = qdrant_client.get_collections().collections
            collection_names = [col.name for col in collections]
            
            if collection_name not in collection_names:
                logger.info(f"Creating collection {collection_name}")
                
                # Get embedding dimension from first chunk
                embedding_dim = len(chunks[0]['embedding']) if chunks else 1536
                
                qdrant_client.create_collection(
                    collection_name=collection_name,
                    vectors_config=models.VectorParams(
                        size=embedding_dim,
                        distance=models.Distance.COSINE
                    )
                )
                logger.info(f"Collection {collection_name} created with dimension {embedding_dim}")
            else:
                logger.info(f"Collection {collection_name} already exists")
                
        except Exception as e:
            logger.error(f"Error checking/creating collection: {str(e)}")
            raise Exception(f"Failed to setup Qdrant collection: {str(e)}")
        
        # Process chunks in batches
        total_batches = (len(chunks) + batch_size - 1) // batch_size
        stored_count = 0
        failed_count = 0
        
        for batch_idx in range(0, len(chunks), batch_size):
            batch_chunks = chunks[batch_idx:batch_idx + batch_size]
            batch_num = (batch_idx // batch_size) + 1
            
            logger.info(f"Storing batch {batch_num}/{total_batches} ({len(batch_chunks)} vectors)")
            
            try:
                # Prepare points for Qdrant
                points = []
                for chunk in batch_chunks:
                    # Prepare metadata payload (exclude embedding to save space)
                    payload = {
                        'source': chunk['metadata']['source'],
                        'filename': chunk['metadata']['filename'], 
                        'text': chunk['text'],
                        'chunk_index': chunk['chunk_index'],
                        'character_count': chunk['character_count'],
                        'total_chunks': chunk['metadata']['total_chunks'],
                        'embedding_model': chunk.get('embedding_model', 'text-embedding-3-small')
                    }
                    
                    # Add optional metadata
                    if 'estimated_page' in chunk['metadata']:
                        payload['page'] = chunk['metadata']['estimated_page']
                    if 'total_pages' in chunk['metadata']:
                        payload['total_pages'] = chunk['metadata']['total_pages']
                    
                    point = models.PointStruct(
                        id=chunk['id'],
                        vector=chunk['embedding'],
                        payload=payload
                    )
                    points.append(point)
                
                # Upsert batch to Qdrant
                result = qdrant_client.upsert(
                    collection_name=collection_name,
                    points=points
                )
                
                if hasattr(result, 'status') and result.status == 'completed':
                    stored_count += len(batch_chunks)
                    logger.info(f"Successfully stored batch {batch_num}")
                else:
                    logger.warning(f"Batch {batch_num} upsert returned unexpected status")
                    failed_count += len(batch_chunks)
                
                # Small delay between batches to avoid overwhelming the database
                if batch_num < total_batches:
                    time.sleep(0.1)
                    
            except ResponseHandlingException as e:
                logger.error(f"Qdrant error processing batch {batch_num}: {str(e)}")
                failed_count += len(batch_chunks)
                # Continue with next batch rather than failing completely
                continue
                
            except Exception as e:
                logger.error(f"Error processing batch {batch_num}: {str(e)}")
                failed_count += len(batch_chunks)
                # For critical errors, you might want to fail the entire operation
                # For now, continue with next batch
                continue
        
        # Verify storage by checking collection info
        try:
            collection_info = qdrant_client.get_collection(collection_name)
            total_vectors_in_collection = collection_info.vectors_count
            logger.info(f"Collection now contains {total_vectors_in_collection} total vectors")
        except Exception as e:
            logger.warning(f"Could not verify collection status: {str(e)}")
            total_vectors_in_collection = None
        
        success_rate = (stored_count / len(chunks)) * 100 if chunks else 0
        
        if failed_count > 0:
            logger.warning(f"Storage completed with {failed_count} failures out of {len(chunks)} chunks")
        
        # If too many failures, consider this a failure
        if success_rate < 80:  # Less than 80% success
            raise Exception(f"Storage failed: only {stored_count}/{len(chunks)} chunks stored successfully")
        
        logger.info(f"Successfully stored {stored_count}/{len(chunks)} vectors ({success_rate:.1f}% success rate)")
        
        result = {
            'key': document_key,
            'filename': filename,
            'totalChunks': len(chunks),
            'storedVectors': stored_count,
            'failedVectors': failed_count,
            'successRate': success_rate,
            'vectorStorage': {
                'collection': collection_name,
                'batchesProcessed': total_batches,
                'totalVectorsInCollection': total_vectors_in_collection
            },
            'metadata': event.get('metadata', {})
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Error in vector storage lambda: {str(e)}")
        raise Exception(f"Vector storage failed: {str(e)}")


def validate_qdrant_connection(host: str, port: int, collection_name: str) -> bool:
    """
    Validate Qdrant connection and collection existence.
    
    Args:
        host: Qdrant host
        port: Qdrant port
        collection_name: Name of the collection to check
        
    Returns:
        True if connection and collection are valid
    """
    try:
        client = QdrantClient(host=host, port=port)
        
        # Test connection
        collections = client.get_collections()
        logger.info(f"Connected to Qdrant. Found {len(collections.collections)} collections")
        
        # Check if collection exists
        collection_names = [col.name for col in collections.collections]
        if collection_name in collection_names:
            # Get collection info
            info = client.get_collection(collection_name)
            logger.info(f"Collection {collection_name} exists with {info.vectors_count} vectors")
            return True
        else:
            logger.warning(f"Collection {collection_name} does not exist")
            return False
            
    except Exception as e:
        logger.error(f"Qdrant validation failed: {str(e)}")
        return False


# For local testing
if __name__ == "__main__":
    # Set test environment variables
    os.environ['QDRANT_HOST'] = 'localhost'
    os.environ['QDRANT_PORT'] = '6333'
    os.environ['COLLECTION_NAME'] = 'enterprise-knowledge-base'
    os.environ['VECTOR_BATCH_SIZE'] = '10'
    
    # Test event with sample chunks and embeddings
    test_chunks = [
        {
            'id': 'chunk-1',
            'text': 'This is the first chunk of text.',
            'chunk_index': 0,
            'character_count': 32,
            'embedding': [0.1] * 1536,  # Mock embedding
            'embedding_model': 'text-embedding-3-small',
            'metadata': {
                'source': 'test.pdf',
                'filename': 'test.pdf',
                'chunk_index': 0,
                'total_chunks': 2,
                'estimated_page': 1
            }
        },
        {
            'id': 'chunk-2', 
            'text': 'This is the second chunk of text.',
            'chunk_index': 1,
            'character_count': 33,
            'embedding': [0.2] * 1536,  # Mock embedding
            'embedding_model': 'text-embedding-3-small',
            'metadata': {
                'source': 'test.pdf',
                'filename': 'test.pdf',
                'chunk_index': 1,
                'total_chunks': 2,
                'estimated_page': 1
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
        # Validate Qdrant connection first
        if validate_qdrant_connection('localhost', 6333, 'enterprise-knowledge-base'):
            result = lambda_handler(test_event, None)
            print(json.dumps(result, indent=2))
        else:
            print("Qdrant connection validation failed")
            
    except Exception as e:
        print(f"Error: {e}")