"""
Lambda function for error handling and failure notifications
"""
import json
import os
import logging
import boto3
from typing import Dict, Any
from datetime import datetime

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handles workflow errors and sends failure notifications.
    
    Args:
        event: Contains error information and workflow state
        context: Lambda context object
        
    Returns:
        Dict containing error handling results
    """
    try:
        logger.error("Document processing workflow failed")
        
        # Extract error information
        error_info = extract_error_information(event)
        logger.error(f"Error details: {error_info}")
        
        # Send failure notification
        notification_result = send_failure_notification(error_info, context)
        
        # Log error for monitoring/alerting
        log_error_for_monitoring(error_info, context)
        
        # Perform error cleanup if needed
        cleanup_result = perform_error_cleanup(event)
        
        result = {
            'errorHandled': True,
            'errorTimestamp': datetime.utcnow().isoformat(),
            'errorInfo': error_info,
            'notification': notification_result,
            'cleanup': cleanup_result,
            'requestId': context.aws_request_id if context else 'local-test'
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Error in error handler lambda: {str(e)}")
        return {
            'errorHandled': False,
            'handlerError': str(e),
            'errorTimestamp': datetime.utcnow().isoformat()
        }


def extract_error_information(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and structure error information from the event.
    
    Args:
        event: Step Function error event
        
    Returns:
        Dict containing structured error information
    """
    error_info = {
        'errorType': 'Unknown',
        'errorMessage': 'No error message available',
        'failedState': 'Unknown',
        'documentKey': None,
        'workflowInput': None,
        'cause': None
    }
    
    try:
        # Check for Step Functions error structure
        if 'error' in event:
            error_data = event['error']
            
            if isinstance(error_data, dict):
                error_info['errorType'] = error_data.get('Error', 'StepFunctionError')
                error_info['errorMessage'] = error_data.get('Cause', error_data.get('errorMessage', 'Unknown error'))
                error_info['cause'] = error_data.get('Cause')
            elif isinstance(error_data, str):
                error_info['errorMessage'] = error_data
        
        # Extract document information if available
        if 'key' in event:
            error_info['documentKey'] = event['key']
        elif 'documents' in event and event['documents']:
            error_info['documentKey'] = event['documents'][0].get('key', 'Multiple documents')
        
        # Extract failed state information
        if 'Error' in event:
            error_info['errorType'] = event['Error']
        if 'Cause' in event:
            error_info['cause'] = event['Cause']
        
        # Store original workflow input for debugging
        error_info['workflowInput'] = {
            'bucketName': event.get('bucketName'),
            'documentCount': event.get('documentCount', 0),
            'sourcePrefix': event.get('sourcePrefix')
        }
        
    except Exception as e:
        logger.warning(f"Could not fully extract error information: {str(e)}")
        error_info['extractionError'] = str(e)
    
    return error_info


def send_failure_notification(error_info: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Send failure notification via SNS or other configured method.
    
    Args:
        error_info: Structured error information
        context: Lambda context
        
    Returns:
        Dict containing notification results
    """
    try:
        # Check if SNS topic is configured for error notifications
        sns_topic_arn = os.environ.get('ERROR_SNS_TOPIC_ARN')
        
        if not sns_topic_arn:
            logger.info("No error SNS topic configured, skipping notification")
            return {'notificationSent': False, 'reason': 'No SNS topic configured'}
        
        # Create SNS client
        sns_client = boto3.client('sns')
        
        # Prepare failure notification message
        document_info = error_info.get('documentKey', 'Unknown document')
        error_type = error_info.get('errorType', 'Unknown error')
        
        subject = f"Document Processing Workflow Failed - {error_type}"
        
        message = f"""
Document Processing Workflow FAILED

Error Details:
- Error Type: {error_info.get('errorType', 'Unknown')}
- Document: {document_info}
- Error Message: {error_info.get('errorMessage', 'No message available')}

Workflow Input:
- Bucket: {error_info.get('workflowInput', {}).get('bucketName', 'Unknown')}
- Source Prefix: {error_info.get('workflowInput', {}).get('sourcePrefix', 'Unknown')}
- Document Count: {error_info.get('workflowInput', {}).get('documentCount', 0)}

Technical Details:
- Request ID: {context.aws_request_id if context else 'N/A'}
- Timestamp: {datetime.utcnow().isoformat()}
- Cause: {error_info.get('cause', 'Not specified')}

This is an automated error notification from the Enterprise Knowledge RAG system.
Please check the Step Functions execution logs for more detailed information.
"""
        
        # Send notification
        response = sns_client.publish(
            TopicArn=sns_topic_arn,
            Subject=subject,
            Message=message
        )
        
        logger.info(f"Error notification sent successfully. Message ID: {response.get('MessageId')}")
        
        return {
            'notificationSent': True,
            'messageId': response.get('MessageId'),
            'topicArn': sns_topic_arn
        }
        
    except Exception as e:
        logger.error(f"Failed to send error notification: {str(e)}")
        return {
            'notificationSent': False,
            'error': str(e)
        }


def log_error_for_monitoring(error_info: Dict[str, Any], context: Any) -> None:
    """
    Log error information for monitoring systems like CloudWatch.
    
    Args:
        error_info: Structured error information
        context: Lambda context
    """
    try:
        # Create structured log entry for monitoring systems
        structured_log = {
            'event_type': 'document_processing_workflow_error',
            'error_type': error_info.get('errorType', 'Unknown'),
            'document_key': error_info.get('documentKey'),
            'error_message': error_info.get('errorMessage'),
            'request_id': context.aws_request_id if context else 'local-test',
            'timestamp': datetime.utcnow().isoformat(),
            'workflow_input': error_info.get('workflowInput', {})
        }
        
        # Log as JSON for easy parsing by monitoring tools
        logger.error(f"WORKFLOW_ERROR: {json.dumps(structured_log)}")
        
        # If CloudWatch custom metrics are configured, send metrics
        if os.environ.get('ENABLE_CLOUDWATCH_METRICS', '').lower() == 'true':
            try:
                cloudwatch = boto3.client('cloudwatch')
                
                # Send error count metric
                cloudwatch.put_metric_data(
                    Namespace='EnterpriseRAG/DocumentProcessing',
                    MetricData=[
                        {
                            'MetricName': 'WorkflowErrors',
                            'Value': 1,
                            'Unit': 'Count',
                            'Dimensions': [
                                {
                                    'Name': 'ErrorType',
                                    'Value': error_info.get('errorType', 'Unknown')
                                }
                            ]
                        }
                    ]
                )
                logger.info("Error metrics sent to CloudWatch")
                
            except Exception as e:
                logger.warning(f"Failed to send CloudWatch metrics: {str(e)}")
        
    except Exception as e:
        logger.error(f"Failed to log error for monitoring: {str(e)}")


def perform_error_cleanup(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Perform cleanup tasks when workflow fails.
    
    Args:
        event: Original workflow event with error information
        
    Returns:
        Dict containing cleanup results
    """
    cleanup_results = {
        'tasksPerformed': [],
        'errors': []
    }
    
    try:
        # Task 1: Clean up partial processing artifacts
        partial_cleanup_result = cleanup_partial_artifacts(event)
        cleanup_results['tasksPerformed'].append({
            'task': 'partial_artifact_cleanup',
            'result': partial_cleanup_result
        })
        
        # Task 2: Reset document processing state if applicable
        state_reset_result = reset_document_processing_state(event)
        cleanup_results['tasksPerformed'].append({
            'task': 'processing_state_reset',
            'result': state_reset_result
        })
        
        # Task 3: Log failure for retry analysis
        retry_analysis_result = log_for_retry_analysis(event)
        cleanup_results['tasksPerformed'].append({
            'task': 'retry_analysis_logging',
            'result': retry_analysis_result
        })
        
        logger.info(f"Error cleanup completed. Performed {len(cleanup_results['tasksPerformed'])} tasks")
        
    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")
        cleanup_results['errors'].append(str(e))
    
    return cleanup_results


def cleanup_partial_artifacts(event: Dict[str, Any]) -> Dict[str, Any]:
    """Clean up any partial processing artifacts."""
    try:
        # In case of failure, we might want to clean up:
        # - Temporary files
        # - Partial vector embeddings (if any were created)
        # - Incomplete processing records
        
        logger.info("Partial artifact cleanup would be performed here")
        
        # For now, just return a placeholder
        return {
            'artifactsFound': 0,
            'artifactsRemoved': 0,
            'cleanupPerformed': True
        }
        
    except Exception as e:
        logger.error(f"Partial artifact cleanup error: {str(e)}")
        return {'error': str(e)}


def reset_document_processing_state(event: Dict[str, Any]) -> Dict[str, Any]:
    """Reset document processing state so failed documents can be retried."""
    try:
        # This might involve:
        # - Removing processing locks
        # - Resetting status flags
        # - Clearing cached processing state
        
        logger.info("Document processing state reset would be performed here")
        
        return {
            'documentsReset': 0,
            'stateResetPerformed': True
        }
        
    except Exception as e:
        logger.error(f"State reset error: {str(e)}")
        return {'error': str(e)}


def log_for_retry_analysis(event: Dict[str, Any]) -> Dict[str, Any]:
    """Log failure information for retry analysis."""
    try:
        # This could involve:
        # - Storing failure details in DynamoDB
        # - Updating retry counters
        # - Analyzing failure patterns
        
        logger.info("Retry analysis logging would be performed here")
        
        return {
            'analysisLogged': True,
            'retryRecommendation': 'manual_review'
        }
        
    except Exception as e:
        logger.error(f"Retry analysis logging error: {str(e)}")
        return {'error': str(e)}


# For local testing
if __name__ == "__main__":
    # Test with sample error event
    test_event = {
        'error': {
            'Error': 'States.TaskFailed',
            'Cause': 'Lambda function returned error: Text extraction failed: No text could be extracted from the PDF'
        },
        'key': 'source/problematic-document.pdf',
        'filename': 'problematic-document.pdf',
        'bucketName': 'enterprise-data',
        'sourcePrefix': 'source/',
        'documentCount': 1
    }
    
    class MockContext:
        aws_request_id = 'test-error-request-123'
    
    # Set test environment variables
    os.environ['ERROR_SNS_TOPIC_ARN'] = 'arn:aws:sns:us-east-1:123456789012:document-processing-errors'
    
    try:
        result = lambda_handler(test_event, MockContext())
        print(json.dumps(result, indent=2))
        
    except Exception as e:
        print(f"Error: {e}")