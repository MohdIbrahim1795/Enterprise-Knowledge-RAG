#!/usr/bin/env python3
"""
Example script to trigger the AWS Step Functions document processing workflow
"""

import json
import boto3
import argparse
import time
from datetime import datetime
from typing import Dict, Any, Optional

def trigger_workflow(
    state_machine_arn: str, 
    input_data: Optional[Dict[str, Any]] = None,
    execution_name: Optional[str] = None,
    region: str = 'us-east-1'
) -> Dict[str, Any]:
    """
    Trigger the document processing Step Functions workflow.
    
    Args:
        state_machine_arn: ARN of the Step Functions state machine
        input_data: Optional input data for the workflow
        execution_name: Optional name for the execution
        region: AWS region
        
    Returns:
        Dict containing execution details
    """
    
    # Initialize Step Functions client
    client = boto3.client('stepfunctions', region_name=region)
    
    # Default input data
    if input_data is None:
        input_data = {
            "bucketName": "enterprise-data",
            "sourcePrefix": "source/",
            "processedPrefix": "processed/",
            "chunkSize": 1000,
            "chunkOverlap": 200
        }
    
    # Generate execution name if not provided
    if execution_name is None:
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        execution_name = f"document-processing-{timestamp}"
    
    print(f"Starting execution: {execution_name}")
    print(f"Input data: {json.dumps(input_data, indent=2)}")
    
    try:
        # Start execution
        response = client.start_execution(
            stateMachineArn=state_machine_arn,
            name=execution_name,
            input=json.dumps(input_data)
        )
        
        execution_arn = response['executionArn']
        start_date = response['startDate']
        
        print(f"✅ Execution started successfully!")
        print(f"   Execution ARN: {execution_arn}")
        print(f"   Start Date: {start_date}")
        
        return {
            'executionArn': execution_arn,
            'startDate': start_date,
            'executionName': execution_name
        }
        
    except Exception as e:
        print(f"❌ Failed to start execution: {str(e)}")
        raise


def monitor_execution(execution_arn: str, region: str = 'us-east-1', poll_interval: int = 30):
    """
    Monitor the execution of a Step Functions workflow.
    
    Args:
        execution_arn: ARN of the execution to monitor
        region: AWS region
        poll_interval: Seconds between status checks
    """
    
    client = boto3.client('stepfunctions', region_name=region)
    
    print(f"🔍 Monitoring execution: {execution_arn}")
    print(f"   Polling every {poll_interval} seconds...")
    print()
    
    start_time = time.time()
    
    while True:
        try:
            # Get execution status
            response = client.describe_execution(executionArn=execution_arn)
            
            status = response['status']
            start_date = response['startDate']
            
            elapsed = time.time() - start_time
            elapsed_str = f"{int(elapsed//60)}m {int(elapsed%60)}s"
            
            print(f"⏱️  [{elapsed_str}] Status: {status}")
            
            if status in ['SUCCEEDED', 'FAILED', 'TIMED_OUT', 'ABORTED']:
                break
            
            # Wait before next check
            time.sleep(poll_interval)
            
        except KeyboardInterrupt:
            print("\n🛑 Monitoring interrupted by user")
            break
        except Exception as e:
            print(f"❌ Error monitoring execution: {str(e)}")
            break
    
    # Get final status
    try:
        final_response = client.describe_execution(executionArn=execution_arn)
        final_status = final_response['status']
        
        print(f"\n📊 Final Status: {final_status}")
        
        if 'stopDate' in final_response:
            duration = final_response['stopDate'] - final_response['startDate']
            print(f"   Duration: {duration}")
        
        if final_status == 'SUCCEEDED':
            print("✅ Workflow completed successfully!")
            if 'output' in final_response:
                output = json.loads(final_response['output'])
                print(f"   Output preview: {json.dumps(output, indent=2)[:500]}...")
        
        elif final_status == 'FAILED':
            print("❌ Workflow failed!")
            if 'error' in final_response:
                print(f"   Error: {final_response['error']}")
            if 'cause' in final_response:
                print(f"   Cause: {final_response['cause']}")
        
    except Exception as e:
        print(f"❌ Error getting final status: {str(e)}")


def list_recent_executions(state_machine_arn: str, region: str = 'us-east-1', max_items: int = 10):
    """
    List recent executions of the Step Functions workflow.
    
    Args:
        state_machine_arn: ARN of the Step Functions state machine
        region: AWS region  
        max_items: Maximum number of executions to list
    """
    
    client = boto3.client('stepfunctions', region_name=region)
    
    try:
        response = client.list_executions(
            stateMachineArn=state_machine_arn,
            maxResults=max_items
        )
        
        executions = response.get('executions', [])
        
        print(f"📋 Recent executions for: {state_machine_arn.split(':')[-1]}")
        print()
        
        if not executions:
            print("   No executions found")
            return
        
        for i, execution in enumerate(executions, 1):
            name = execution['name']
            status = execution['status']
            start_date = execution['startDate'].strftime('%Y-%m-%d %H:%M:%S')
            
            status_emoji = {
                'SUCCEEDED': '✅',
                'FAILED': '❌', 
                'RUNNING': '🔄',
                'TIMED_OUT': '⏰',
                'ABORTED': '🛑'
            }.get(status, '❓')
            
            print(f"   {i:2}. {status_emoji} {name}")
            print(f"       Status: {status}")
            print(f"       Started: {start_date}")
            
            if 'stopDate' in execution:
                stop_date = execution['stopDate'].strftime('%Y-%m-%d %H:%M:%S')
                duration = execution['stopDate'] - execution['startDate']
                print(f"       Stopped: {stop_date} (Duration: {duration})")
            
            print()
            
    except Exception as e:
        print(f"❌ Error listing executions: {str(e)}")


def main():
    parser = argparse.ArgumentParser(description='Trigger AWS Step Functions document processing workflow')
    parser.add_argument('--state-machine-arn', required=True, help='Step Functions state machine ARN')
    parser.add_argument('--bucket', help='S3 bucket name override')
    parser.add_argument('--source-prefix', default='source/', help='Source prefix override')
    parser.add_argument('--processed-prefix', default='processed/', help='Processed prefix override')
    parser.add_argument('--execution-name', help='Custom execution name')
    parser.add_argument('--region', default='us-east-1', help='AWS region')
    parser.add_argument('--monitor', action='store_true', help='Monitor execution after starting')
    parser.add_argument('--list-executions', action='store_true', help='List recent executions')
    parser.add_argument('--monitor-existing', help='Monitor existing execution by ARN')
    
    args = parser.parse_args()
    
    if args.list_executions:
        list_recent_executions(args.state_machine_arn, args.region)
        return
    
    if args.monitor_existing:
        monitor_execution(args.monitor_existing, args.region)
        return
    
    # Prepare input data
    input_data = {
        "sourcePrefix": args.source_prefix,
        "processedPrefix": args.processed_prefix
    }
    
    if args.bucket:
        input_data["bucketName"] = args.bucket
    
    # Start execution
    try:
        result = trigger_workflow(
            state_machine_arn=args.state_machine_arn,
            input_data=input_data,
            execution_name=args.execution_name,
            region=args.region
        )
        
        # Monitor if requested
        if args.monitor:
            print()
            monitor_execution(result['executionArn'], args.region)
        else:
            print(f"\n🔗 Monitor execution at:")
            print(f"   https://{args.region}.console.aws.amazon.com/states/home?region={args.region}#/executions/details/{result['executionArn']}")
        
    except Exception as e:
        print(f"❌ Failed to trigger workflow: {str(e)}")
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())