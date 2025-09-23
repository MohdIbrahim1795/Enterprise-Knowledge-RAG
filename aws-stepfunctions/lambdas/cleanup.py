"""
Lambda function for cleanup and completion notification
"""
import json
import os
import logging
import boto3
from typing import Dict, Any, List
from datetime import datetime

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handles cleanup tasks and sends completion notifications after document processing.
    
    Args:
        event: Contains processing results from the entire workflow
        context: Lambda context object
        
    Returns:
        Dict containing cleanup results and final statistics
    """
    try:
        logger.info("Starting cleanup and notification process")
        
        # Extract workflow results
        processed_documents = event if isinstance(event, list) else [event]
        
        # Calculate overall statistics
        stats = calculate_workflow_statistics(processed_documents)
        logger.info(f"Workflow statistics: {stats}")
        
        # Send notification if configured
        notification_result = send_completion_notification(stats, context)
        
        # Perform optional cleanup tasks
        cleanup_result = perform_cleanup_tasks()
        
        # Log final results
        logger.info(f"Processing complete: {stats['totalDocuments']} documents processed")
        logger.info(f"Success rate: {stats['overallSuccessRate']:.1f}%")
        
        result = {
            'workflowComplete': True,
            'completionTimestamp': datetime.utcnow().isoformat(),
            'statistics': stats,
            'notification': notification_result,
            'cleanup': cleanup_result,
            'requestId': context.aws_request_id if context else 'local-test'
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Error in cleanup lambda: {str(e)}")
        # Don't fail the workflow for cleanup errors
        return {
            'workflowComplete': True,
            'error': str(e),
            'completionTimestamp': datetime.utcnow().isoformat()
        }


def calculate_workflow_statistics(processed_documents: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate overall statistics for the document processing workflow.
    
    Args:
        processed_documents: List of processing results for each document
        
    Returns:
        Dict containing workflow statistics
    """
    total_documents = len(processed_documents)
    successful_documents = 0
    total_chunks = 0
    total_vectors_stored = 0
    total_failures = 0
    
    processing_times = []
    file_sizes = []
    
    for doc_result in processed_documents:
        if isinstance(doc_result, dict):
            # Check if document was processed successfully
            if doc_result.get('storedVectors', 0) > 0:
                successful_documents += 1
            
            total_chunks += doc_result.get('totalChunks', 0)
            total_vectors_stored += doc_result.get('storedVectors', 0)
            
            # Count failed vectors
            failed_vectors = doc_result.get('failedVectors', 0)
            total_failures += failed_vectors
            
            # Collect metadata if available
            metadata = doc_result.get('metadata', {})
            if 'originalSize' in metadata:
                file_sizes.append(metadata['originalSize'])
    
    # Calculate rates and averages
    success_rate = (successful_documents / total_documents * 100) if total_documents > 0 else 0
    avg_chunks_per_doc = total_chunks / total_documents if total_documents > 0 else 0
    avg_file_size = sum(file_sizes) / len(file_sizes) if file_sizes else 0
    
    return {
        'totalDocuments': total_documents,
        'successfulDocuments': successful_documents,
        'failedDocuments': total_documents - successful_documents,
        'overallSuccessRate': success_rate,
        'totalChunksCreated': total_chunks,
        'totalVectorsStored': total_vectors_stored,
        'totalVectorFailures': total_failures,
        'averageChunksPerDocument': round(avg_chunks_per_doc, 1),
        'averageFileSize': int(avg_file_size),
        'processedFileSizes': file_sizes
    }


def send_completion_notification(stats: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Send completion notification via SNS, email, or other configured method.
    
    Args:
        stats: Workflow statistics
        context: Lambda context
        
    Returns:
        Dict containing notification results
    """
    try:
        # Check if SNS topic is configured
        sns_topic_arn = os.environ.get('COMPLETION_SNS_TOPIC_ARN')
        
        if not sns_topic_arn:
            logger.info("No SNS topic configured, skipping notification")
            return {'notificationSent': False, 'reason': 'No SNS topic configured'}
        
        # Create SNS client
        sns_client = boto3.client('sns')
        
        # Prepare notification message
        subject = f"Document Processing Workflow Complete - {stats['successfulDocuments']}/{stats['totalDocuments']} successful"
        
        message = f"""
Document Processing Workflow Completed

Summary:
- Total Documents: {stats['totalDocuments']}
- Successful: {stats['successfulDocuments']}
- Failed: {stats['failedDocuments']}
- Success Rate: {stats['overallSuccessRate']:.1f}%

Processing Details:
- Total Chunks Created: {stats['totalChunksCreated']}
- Total Vectors Stored: {stats['totalVectorsStored']}
- Vector Storage Failures: {stats['totalVectorFailures']}
- Average Chunks per Document: {stats['averageChunksPerDocument']}

Request ID: {context.aws_request_id if context else 'N/A'}
Timestamp: {datetime.utcnow().isoformat()}

This is an automated notification from the Enterprise Knowledge RAG system.
"""
        
        # Send notification
        response = sns_client.publish(
            TopicArn=sns_topic_arn,
            Subject=subject,
            Message=message
        )
        
        logger.info(f"Notification sent successfully. Message ID: {response.get('MessageId')}")
        
        return {
            'notificationSent': True,
            'messageId': response.get('MessageId'),
            'topicArn': sns_topic_arn
        }
        
    except Exception as e:
        logger.error(f"Failed to send notification: {str(e)}")
        return {
            'notificationSent': False,
            'error': str(e)
        }


def perform_cleanup_tasks() -> Dict[str, Any]:
    """
    Perform optional cleanup tasks like removing temporary files, optimizing storage, etc.
    
    Returns:
        Dict containing cleanup results
    """
    cleanup_results = {
        'tasksPerformed': [],
        'errors': []
    }
    
    try:
        # Task 1: Clean up old temporary files (if any)
        temp_cleanup_result = cleanup_temp_files()
        cleanup_results['tasksPerformed'].append({
            'task': 'temp_file_cleanup',
            'result': temp_cleanup_result
        })
        
        # Task 2: Optimize vector database (optional)
        if os.environ.get('ENABLE_VECTOR_DB_OPTIMIZATION', '').lower() == 'true':
            vector_optimization_result = optimize_vector_database()
            cleanup_results['tasksPerformed'].append({
                'task': 'vector_db_optimization',
                'result': vector_optimization_result
            })
        
        # Task 3: Update processing metrics (optional)
        metrics_result = update_processing_metrics()
        cleanup_results['tasksPerformed'].append({
            'task': 'metrics_update',
            'result': metrics_result
        })
        
        logger.info(f"Cleanup completed. Performed {len(cleanup_results['tasksPerformed'])} tasks")
        
    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")
        cleanup_results['errors'].append(str(e))
    
    return cleanup_results


def cleanup_temp_files() -> Dict[str, Any]:
    """Clean up any temporary files that might have been created during processing."""
    try:
        import tempfile
        import shutil
        
        temp_dir = tempfile.gettempdir()
        cleaned_files = 0
        
        # In a real Lambda environment, temp files are automatically cleaned up
        # This is more relevant for local testing or container environments
        
        logger.info(f"Temp directory cleanup check: {temp_dir}")
        return {
            'cleanedFiles': cleaned_files,
            'tempDirectory': temp_dir
        }
        
    except Exception as e:
        logger.error(f"Temp file cleanup error: {str(e)}")
        return {'error': str(e)}


def optimize_vector_database() -> Dict[str, Any]:
    """Optionally optimize the vector database after bulk insertions."""
    try:
        # This could include operations like:
        # - Rebuilding indexes
        # - Compacting storage
        # - Updating collection statistics
        
        logger.info("Vector database optimization would be performed here")
        return {
            'optimizationPerformed': False,
            'reason': 'Not implemented in this version'
        }
        
    except Exception as e:
        logger.error(f"Vector DB optimization error: {str(e)}")
        return {'error': str(e)}


def update_processing_metrics() -> Dict[str, Any]:
    """Update processing metrics in CloudWatch or other monitoring system."""
    try:
        # This could include:
        # - Updating CloudWatch custom metrics
        # - Logging to application metrics system
        # - Updating processing history database
        
        logger.info("Processing metrics update would be performed here")
        return {
            'metricsUpdated': False,
            'reason': 'Not implemented in this version'
        }
        
    except Exception as e:
        logger.error(f"Metrics update error: {str(e)}")
        return {'error': str(e)}


# For local testing
if __name__ == "__main__":
    # Test with sample workflow results
    test_events = [
        {
            'key': 'source/doc1.pdf',
            'filename': 'doc1.pdf',
            'totalChunks': 10,
            'storedVectors': 10,
            'failedVectors': 0,
            'successRate': 100.0,
            'metadata': {
                'originalSize': 50000,
                'extractionTimestamp': 'test-run-1'
            }
        },
        {
            'key': 'source/doc2.pdf', 
            'filename': 'doc2.pdf',
            'totalChunks': 8,
            'storedVectors': 7,
            'failedVectors': 1,
            'successRate': 87.5,
            'metadata': {
                'originalSize': 35000,
                'extractionTimestamp': 'test-run-2'
            }
        }
    ]
    
    class MockContext:
        aws_request_id = 'test-request-cleanup-123'
    
    try:
        result = lambda_handler(test_events, MockContext())
        print(json.dumps(result, indent=2))
        
    except Exception as e:
        print(f"Error: {e}")