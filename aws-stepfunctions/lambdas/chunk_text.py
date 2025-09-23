"""
Lambda function to chunk text into smaller segments for embedding generation
"""
import json
import os
import logging
import hashlib
import uuid
from typing import Dict, Any, List
import re

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Splits extracted text into smaller chunks suitable for embedding generation.
    
    Args:
        event: Contains extracted text and document metadata
        context: Lambda context object
        
    Returns:
        Dict containing text chunks and metadata
    """
    try:
        # Extract parameters from event
        extracted_text = event['extractedText']
        document_key = event['key']
        filename = event.get('filename', document_key.split('/')[-1])
        
        # Chunking configuration from environment or defaults
        chunk_size = int(os.environ.get('CHUNK_SIZE', '1000'))
        chunk_overlap = int(os.environ.get('CHUNK_OVERLAP', '200'))
        
        logger.info(f"Chunking document {filename} with chunk_size={chunk_size}, overlap={chunk_overlap}")
        
        # Create chunks using recursive character text splitter logic
        chunks = recursive_character_text_split(
            text=extracted_text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        
        logger.info(f"Created {len(chunks)} chunks from document {filename}")
        
        # Create chunk objects with metadata
        chunk_objects = []
        for i, chunk_text in enumerate(chunks):
            # Generate unique ID for each chunk
            content_hash = hashlib.md5(f"{filename}-{i}-{chunk_text[:50]}".encode()).hexdigest()
            chunk_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, content_hash))
            
            chunk_obj = {
                'id': chunk_id,
                'text': chunk_text,
                'chunk_index': i,
                'character_count': len(chunk_text),
                'metadata': {
                    'source': document_key,
                    'filename': filename,
                    'chunk_index': i,
                    'total_chunks': len(chunks),
                    'original_document_chars': len(extracted_text)
                }
            }
            
            # Add page information if available
            if 'pages' in event:
                chunk_obj['metadata']['total_pages'] = len(event['pages'])
                # Try to determine which page(s) this chunk might come from
                # This is approximate since we don't track exact positions
                estimated_page = min(len(event['pages']), max(1, int((i / len(chunks)) * len(event['pages'])) + 1))
                chunk_obj['metadata']['estimated_page'] = estimated_page
        
            chunk_objects.append(chunk_obj)
        
        # Calculate statistics
        total_chunk_chars = sum(len(chunk['text']) for chunk in chunk_objects)
        avg_chunk_size = total_chunk_chars / len(chunk_objects) if chunk_objects else 0
        
        result = {
            'key': document_key,
            'filename': filename,
            'chunks': chunk_objects,
            'totalChunks': len(chunk_objects),
            'originalTextLength': len(extracted_text),
            'totalChunkLength': total_chunk_chars,
            'averageChunkSize': int(avg_chunk_size),
            'chunkingConfig': {
                'chunk_size': chunk_size,
                'chunk_overlap': chunk_overlap
            },
            'metadata': event.get('metadata', {})
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Error in text chunking lambda: {str(e)}")
        raise Exception(f"Text chunking failed: {str(e)}")


def recursive_character_text_split(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> List[str]:
    """
    Recursively splits text into chunks, trying to respect natural boundaries.
    Based on LangChain's RecursiveCharacterTextSplitter logic.
    
    Args:
        text: The text to split
        chunk_size: Maximum size of each chunk
        chunk_overlap: Number of characters to overlap between chunks
        
    Returns:
        List of text chunks
    """
    if not text.strip():
        return []
    
    # Define separators in order of preference
    separators = ["\n\n", "\n", ". ", "! ", "? ", "; ", ": ", " ", ""]
    
    def split_text_with_separators(text: str, separators: List[str]) -> List[str]:
        """Split text using the first available separator."""
        chunks = []
        
        if len(text) <= chunk_size:
            return [text] if text.strip() else []
        
        # Try each separator
        for separator in separators:
            if separator and separator in text:
                splits = text.split(separator)
                
                if len(splits) > 1:
                    # Reconstruct chunks with separator
                    current_chunk = ""
                    
                    for i, split in enumerate(splits):
                        # Add separator back except for last split
                        if i < len(splits) - 1:
                            split_with_sep = split + separator
                        else:
                            split_with_sep = split
                        
                        # Check if adding this split would exceed chunk size
                        if len(current_chunk + split_with_sep) <= chunk_size:
                            current_chunk += split_with_sep
                        else:
                            # Save current chunk if it's not empty
                            if current_chunk.strip():
                                chunks.append(current_chunk.strip())
                            
                            # Start new chunk with overlap
                            if chunk_overlap > 0 and current_chunk:
                                # Take last chunk_overlap characters from previous chunk
                                overlap_text = current_chunk[-chunk_overlap:]
                                current_chunk = overlap_text + split_with_sep
                            else:
                                current_chunk = split_with_sep
                    
                    # Add the last chunk
                    if current_chunk.strip():
                        chunks.append(current_chunk.strip())
                    
                    return chunks
        
        # If no separator worked, split by character count
        chunks = []
        for i in range(0, len(text), chunk_size - chunk_overlap):
            chunk = text[i:i + chunk_size]
            if chunk.strip():
                chunks.append(chunk.strip())
        
        return chunks
    
    return split_text_with_separators(text, separators)


def clean_text(text: str) -> str:
    """
    Clean and normalize text before chunking.
    
    Args:
        text: Raw text to clean
        
    Returns:
        Cleaned text
    """
    # Remove excessive whitespace
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = re.sub(r' +', ' ', text)
    
    # Remove common PDF artifacts
    text = re.sub(r'[^\w\s\.\,\!\?\;\:\-\(\)\[\]\{\}\"\'\/]', ' ', text)
    
    return text.strip()


# For local testing
if __name__ == "__main__":
    # Test event with sample extracted text
    test_text = """
    This is a sample document with multiple paragraphs. 
    
    The first paragraph contains some information about the topic. It has several sentences that explain the concept in detail.
    
    The second paragraph continues the discussion. It provides additional context and examples to help understand the topic better.
    
    Finally, the third paragraph concludes the document. It summarizes the key points and provides a call to action.
    """
    
    test_event = {
        'key': 'source/test-document.pdf',
        'filename': 'test-document.pdf',
        'extractedText': test_text,
        'pages': [
            {'page_number': 1, 'text': test_text[:200], 'character_count': 200},
            {'page_number': 2, 'text': test_text[200:], 'character_count': len(test_text) - 200}
        ],
        'metadata': {
            'originalSize': 12345,
            'extractionTimestamp': 'test-run'
        }
    }
    
    # Set environment variables for testing
    os.environ['CHUNK_SIZE'] = '200'
    os.environ['CHUNK_OVERLAP'] = '50'
    
    try:
        result = lambda_handler(test_event, None)
        print(json.dumps(result, indent=2))
        
        print(f"\nChunk preview:")
        for i, chunk in enumerate(result['chunks'][:3]):  # Show first 3 chunks
            print(f"Chunk {i+1} ({len(chunk['text'])} chars): {chunk['text'][:100]}...")
            
    except Exception as e:
        print(f"Error: {e}")