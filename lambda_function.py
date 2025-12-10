import json
import boto3
import os
from datetime import datetime


def lambda_handler(event, context):
    """
    AWS Lambda function triggered by S3 EventBridge
    Sends small JSON payload to FastAPI backend
    """
    
    # FastAPI endpoint URL - configure this in Lambda environment variables
    FASTAPI_WEBHOOK_URL = os.environ.get('FASTAPI_WEBHOOK_URL')
    LAMBDA_SECRET_KEY = os.environ.get('LAMBDA_SECRET_KEY')
    
    try:
        # Parse S3 event
        for record in event.get('Records', []):
            event_name = record.get('eventName', '')
            s3_info = record.get('s3', {})
            bucket = s3_info.get('bucket', {}).get('name', '')
            s3_key = s3_info.get('object', {}).get('key', '')
            size = s3_info.get('object', {}).get('size', 0)
            event_time = record.get('eventTime', datetime.utcnow().isoformat())
            
            # Create payload
            payload = {
                'event_id': f"{bucket}_{s3_key}_{event_time}",
                'bucket': bucket,
                'key': s3_key,
                'event_name': event_name,
                'event_time': event_time,
                'size': size,
                'content_type': None,  # Can get from S3 metadata if needed
                'metadata': {
                    'region': record.get('awsRegion', ''),
                    'source_ip': record.get('requestParameters', {}).get('sourceIPAddress', '')
                },
                'secret_key': LAMBDA_SECRET_KEY
            }
            
            # Send to FastAPI
            import urllib3
            http = urllib3.PoolManager()
            
            response = http.request(
                'POST',
                FASTAPI_WEBHOOK_URL,
                body=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            
            print(f"Sent to FastAPI: {response.status}")
            print(f"Response: {response.data.decode('utf-8')}")
        
        return {
            'statusCode': 200,
            'body': json.dumps('Successfully processed S3 event')
        }
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error processing event: {str(e)}')
        }
