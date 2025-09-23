"""
Lambda function to list new documents in the source bucket/MinIO
"""
import json
import boto3
import os
import logging
from typing import List, Dict, Any
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lists new documents in the source S3 bucket/MinIO that need processing.
    
    Args:
        event: Lambda event data (can contain bucket and prefix overrides)
        context: Lambda context object
        
    Returns:
        Dict containing list of documents to process and document count
    """
    try:
        # Configuration from environment variables
        bucket_name = event.get('bucketName', os.environ.get('SOURCE_BUCKET', 'enterprise-data'))
        source_prefix = event.get('sourcePrefix', os.environ.get('SOURCE_PREFIX', 'source/'))
        processed_prefix = event.get('processedPrefix', os.environ.get('PROCESSED_PREFIX', 'processed/'))
        
        # Initialize S3 client (works with MinIO if endpoint_url is configured)
        s3_config = {}
        if os.environ.get('S3_ENDPOINT_URL'):
            s3_config['endpoint_url'] = os.environ.get('S3_ENDPOINT_URL')
            
        s3_client = boto3.client('s3', **s3_config)
        
        logger.info(f"Scanning bucket '{bucket_name}' with prefix '{source_prefix}' for new documents")
        
        # List all objects in source directory
        source_objects = []
        paginator = s3_client.get_paginator('list_objects_v2')
        
        for page in paginator.paginate(Bucket=bucket_name, Prefix=source_prefix):
            for obj in page.get('Contents', []):
                # Skip directories and non-PDF files for now
                key = obj['Key']
                if not key.endswith('/') and key.lower().endswith('.pdf'):
                    source_objects.append({
                        'key': key,
                        'size': obj['Size'],
                        'lastModified': obj['LastModified'].isoformat(),
                        'filename': key.split('/')[-1]
                    })
        
        # Get list of already processed files
        processed_filenames = set()
        try:
            for page in paginator.paginate(Bucket=bucket_name, Prefix=processed_prefix):
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    if not key.endswith('/'):
                        filename = key.split('/')[-1]
                        processed_filenames.add(filename)
        except ClientError as e:
            # Processed directory might not exist yet
            logger.warning(f"Could not list processed directory: {e}")
        
        # Filter out already processed documents
        new_documents = []
        for doc in source_objects:
            if doc['filename'] not in processed_filenames:
                new_documents.append(doc)
        
        logger.info(f"Found {len(source_objects)} total documents, {len(new_documents)} new documents to process")
        
        result = {
            'bucketName': bucket_name,
            'sourcePrefix': source_prefix,
            'processedPrefix': processed_prefix,
            'documents': new_documents,
            'documentCount': len(new_documents),
            'totalDocuments': len(source_objects),
            'processedDocuments': len(processed_filenames)
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Error listing documents: {str(e)}")
        raise Exception(f"Failed to list documents: {str(e)}")


# For local testing
if __name__ == "__main__":
    import os
    
    # Set test environment variables
    os.environ['SOURCE_BUCKET'] = 'enterprise-data'
    os.environ['SOURCE_PREFIX'] = 'source/'
    os.environ['PROCESSED_PREFIX'] = 'processed/'
    os.environ['S3_ENDPOINT_URL'] = 'http://localhost:9000'  # For MinIO
    
    # Test event
    test_event = {}
    test_context = None
    
    try:
        result = lambda_handler(test_event, test_context)
        print(json.dumps(result, indent=2, default=str))
    except Exception as e:
        print(f"Error: {e}")