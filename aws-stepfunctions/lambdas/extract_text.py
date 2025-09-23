"""
Lambda function to extract text from PDF documents
"""
import json
import boto3
import os
import tempfile
import logging
from typing import Dict, Any, List
import pypdf
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Extracts text content from a PDF document stored in S3/MinIO.
    
    Args:
        event: Contains document information (key, bucketName, etc.)
        context: Lambda context object
        
    Returns:
        Dict containing extracted text and metadata
    """
    try:
        # Extract document information from event
        document_key = event['key']
        bucket_name = event.get('bucketName', os.environ.get('SOURCE_BUCKET', 'enterprise-data'))
        
        logger.info(f"Extracting text from document: {document_key}")
        
        # Initialize S3 client
        s3_config = {}
        if os.environ.get('S3_ENDPOINT_URL'):
            s3_config['endpoint_url'] = os.environ.get('S3_ENDPOINT_URL')
            
        s3_client = boto3.client('s3', **s3_config)
        
        # Download the PDF file to temporary storage
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
            try:
                s3_client.download_file(bucket_name, document_key, temp_file.name)
                temp_path = temp_file.name
                logger.info(f"Downloaded {document_key} to {temp_path}")
            except ClientError as e:
                logger.error(f"Failed to download file {document_key}: {e}")
                raise Exception(f"Failed to download file: {str(e)}")
        
        try:
            # Extract text using PyPDF
            pdf_reader = pypdf.PdfReader(temp_path)
            pages_text = []
            total_text = ""
            
            for page_num, page in enumerate(pdf_reader.pages, 1):
                try:
                    page_text = page.extract_text()
                    if page_text.strip():  # Only add non-empty pages
                        pages_text.append({
                            'page_number': page_num,
                            'text': page_text,
                            'character_count': len(page_text)
                        })
                        total_text += page_text + "\n\n"
                except Exception as e:
                    logger.warning(f"Failed to extract text from page {page_num}: {e}")
                    continue
            
            # Clean up temporary file
            os.unlink(temp_path)
            
            # Validate extraction
            if not total_text.strip():
                raise Exception("No text could be extracted from the PDF")
            
            logger.info(f"Successfully extracted {len(total_text)} characters from {len(pages_text)} pages")
            
            result = {
                'key': document_key,
                'bucketName': bucket_name,
                'filename': event.get('filename', document_key.split('/')[-1]),
                'extractedText': total_text.strip(),
                'pages': pages_text,
                'totalPages': len(pdf_reader.pages),
                'extractedPages': len(pages_text),
                'totalCharacters': len(total_text),
                'metadata': {
                    'originalSize': event.get('size', 0),
                    'lastModified': event.get('lastModified'),
                    'extractionTimestamp': context.aws_request_id if context else 'local-test'
                }
            }
            
            return result
            
        except Exception as e:
            # Clean up temporary file if it exists
            if 'temp_path' in locals():
                try:
                    os.unlink(temp_path)
                except:
                    pass
            logger.error(f"Error extracting text from {document_key}: {str(e)}")
            raise Exception(f"Text extraction failed: {str(e)}")
            
    except Exception as e:
        logger.error(f"Error in text extraction lambda: {str(e)}")
        raise Exception(f"Text extraction lambda failed: {str(e)}")


def extract_text_fallback(temp_path: str) -> str:
    """
    Fallback text extraction method using alternative libraries.
    Can be extended with OCR capabilities if needed.
    
    Args:
        temp_path: Path to the temporary PDF file
        
    Returns:
        Extracted text string
    """
    try:
        # Alternative extraction method could go here
        # For example, using pdfplumber, PyMuPDF, or OCR with pytesseract
        logger.info("Using fallback text extraction method")
        
        # For now, just try PyPDF again with different settings
        with open(temp_path, 'rb') as file:
            pdf_reader = pypdf.PdfReader(file)
            text = ""
            for page in pdf_reader.pages:
                try:
                    page_text = page.extract_text()
                    text += page_text + "\n"
                except:
                    continue
            return text
            
    except Exception as e:
        logger.error(f"Fallback extraction also failed: {e}")
        raise Exception("All text extraction methods failed")


# For local testing
if __name__ == "__main__":
    # Set test environment variables
    os.environ['SOURCE_BUCKET'] = 'enterprise-data'
    os.environ['S3_ENDPOINT_URL'] = 'http://localhost:9000'  # For MinIO
    
    # Test event
    test_event = {
        'key': 'source/test-document.pdf',
        'filename': 'test-document.pdf',
        'size': 12345,
        'lastModified': '2024-01-01T00:00:00.000Z'
    }
    test_context = None
    
    try:
        result = lambda_handler(test_event, test_context)
        print(json.dumps(result, indent=2, default=str))
        print(f"\nExtracted text preview (first 200 chars):")
        print(result['extractedText'][:200] + "...")
    except Exception as e:
        print(f"Error: {e}")