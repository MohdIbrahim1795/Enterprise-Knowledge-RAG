"""
Lambda function to move successfully processed documents to processed folder
"""
import json
import boto3
import os
import logging
from typing import Dict, Any
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Moves a successfully processed document from source to processed folder.
    
    Args:
        event: Contains document information and processing results
        context: Lambda context object
        
    Returns:
        Dict containing move operation results
    """
    try:
        # Extract document information from event
        document_key = event['key']
        filename = event['filename']
        bucket_name = event.get('bucketName', os.environ.get('SOURCE_BUCKET', 'enterprise-data'))
        source_prefix = os.environ.get('SOURCE_PREFIX', 'source/')
        processed_prefix = os.environ.get('PROCESSED_PREFIX', 'processed/')
        
        logger.info(f"Moving document {filename} from {source_prefix} to {processed_prefix}")
        
        # Initialize S3 client
        s3_config = {}
        if os.environ.get('S3_ENDPOINT_URL'):
            s3_config['endpoint_url'] = os.environ.get('S3_ENDPOINT_URL')
            
        s3_client = boto3.client('s3', **s3_config)
        
        # Define source and destination keys
        source_key = document_key
        processed_key = document_key.replace(source_prefix, processed_prefix, 1)
        
        # Add timestamp to processed filename to avoid conflicts
        if context and hasattr(context, 'aws_request_id'):
            timestamp = context.aws_request_id[:8]
        else:
            import time
            timestamp = str(int(time.time()))[-8:]
            
        # Insert timestamp before file extension
        name_parts = processed_key.rsplit('.', 1)
        if len(name_parts) == 2:
            processed_key = f"{name_parts[0]}_{timestamp}.{name_parts[1]}"
        else:
            processed_key = f"{processed_key}_{timestamp}"
        
        try:
            # Check if source file exists
            s3_client.head_object(Bucket=bucket_name, Key=source_key)
            logger.info(f"Source file confirmed: {source_key}")
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                logger.error(f"Source file not found: {source_key}")
                raise Exception(f"Source file not found: {source_key}")
            else:
                raise e
        
        try:
            # Copy file to processed location
            copy_source = {
                'Bucket': bucket_name,
                'Key': source_key
            }
            
            s3_client.copy_object(
                CopySource=copy_source,
                Bucket=bucket_name,
                Key=processed_key
            )
            logger.info(f"File copied to: {processed_key}")
            
            # Add metadata to the processed file
            processing_metadata = {
                'processing-timestamp': str(int(time.time())),
                'processing-request-id': context.aws_request_id if context else 'local-test',
                'original-source-key': source_key,
                'chunks-processed': str(event.get('totalChunks', 0)),
                'vectors-stored': str(event.get('storedVectors', 0))
            }
            
            # Update metadata on processed file
            s3_client.copy_object(
                CopySource=copy_source,
                Bucket=bucket_name,
                Key=processed_key,
                Metadata=processing_metadata,
                MetadataDirective='REPLACE'
            )
            logger.info("Processing metadata added to processed file")
            
        except Exception as e:
            logger.error(f"Error copying file: {str(e)}")
            raise Exception(f"Failed to copy file to processed location: {str(e)}")
        
        try:
            # Delete original file from source location
            s3_client.delete_object(Bucket=bucket_name, Key=source_key)
            logger.info(f"Original file deleted from: {source_key}")
            
        except Exception as e:
            logger.error(f"Error deleting source file: {str(e)}")
            # Don't fail the entire operation if deletion fails
            # The file will remain in source but also exist in processed
            logger.warning("Source file deletion failed, but copy succeeded")
        
        # Verify the processed file exists
        try:
            processed_obj = s3_client.head_object(Bucket=bucket_name, Key=processed_key)
            file_size = processed_obj['ContentLength']
            logger.info(f"Processed file verified: {processed_key} ({file_size} bytes)")
        except Exception as e:
            logger.error(f"Error verifying processed file: {str(e)}")
            raise Exception(f"Failed to verify processed file: {str(e)}")
        
        result = {
            'originalKey': source_key,
            'processedKey': processed_key,
            'bucketName': bucket_name,
            'filename': filename,
            'moveOperation': {
                'sourceDeleted': True,  # Assume success unless we caught an error above
                'processedCreated': True,
                'fileSize': file_size,
                'timestamp': processing_metadata['processing-timestamp']
            },
            'processingStats': {
                'totalChunks': event.get('totalChunks', 0),
                'storedVectors': event.get('storedVectors', 0),
                'successRate': event.get('successRate', 0)
            },
            'metadata': event.get('metadata', {})
        }
        
        logger.info(f"Successfully moved document {filename} to processed folder")
        return result
        
    except Exception as e:
        logger.error(f"Error in move processed lambda: {str(e)}")
        raise Exception(f"Failed to move document to processed folder: {str(e)}")


def cleanup_old_processed_files(bucket_name: str, processed_prefix: str, days_to_keep: int = 30):
    """
    Optional cleanup function to remove old processed files.
    This could be called periodically to manage storage costs.
    
    Args:
        bucket_name: S3 bucket name
        processed_prefix: Prefix for processed files
        days_to_keep: Number of days to keep processed files
    """
    try:
        s3_config = {}
        if os.environ.get('S3_ENDPOINT_URL'):
            s3_config['endpoint_url'] = os.environ.get('S3_ENDPOINT_URL')
            
        s3_client = boto3.client('s3', **s3_config)
        
        from datetime import datetime, timedelta
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        
        logger.info(f"Cleaning up processed files older than {days_to_keep} days (before {cutoff_date})")
        
        paginator = s3_client.get_paginator('list_objects_v2')
        deleted_count = 0
        
        for page in paginator.paginate(Bucket=bucket_name, Prefix=processed_prefix):
            for obj in page.get('Contents', []):
                if obj['LastModified'].replace(tzinfo=None) < cutoff_date:
                    try:
                        s3_client.delete_object(Bucket=bucket_name, Key=obj['Key'])
                        deleted_count += 1
                        logger.info(f"Deleted old processed file: {obj['Key']}")
                    except Exception as e:
                        logger.warning(f"Failed to delete {obj['Key']}: {e}")
        
        logger.info(f"Cleanup completed. Deleted {deleted_count} old processed files")
        return deleted_count
        
    except Exception as e:
        logger.error(f"Cleanup failed: {str(e)}")
        return 0


# For local testing
if __name__ == "__main__":
    # Set test environment variables
    os.environ['SOURCE_BUCKET'] = 'enterprise-data'
    os.environ['SOURCE_PREFIX'] = 'source/'
    os.environ['PROCESSED_PREFIX'] = 'processed/'
    os.environ['S3_ENDPOINT_URL'] = 'http://localhost:9000'  # For MinIO
    
    # Test event
    test_event = {
        'key': 'source/test-document.pdf',
        'filename': 'test-document.pdf',
        'bucketName': 'enterprise-data',
        'totalChunks': 15,
        'storedVectors': 15,
        'successRate': 100.0,
        'metadata': {
            'originalSize': 12345,
            'extractionTimestamp': 'test-run'
        }
    }
    
    class MockContext:
        aws_request_id = 'test-request-123'
    
    try:
        result = lambda_handler(test_event, MockContext())
        print(json.dumps(result, indent=2))
        
    except Exception as e:
        print(f"Error: {e}")