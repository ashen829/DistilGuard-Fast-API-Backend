# AWS Lambda Setup for S3 Event Integration

## Step 1: Configure Your .env File

Update the `.env` file with your actual AWS credentials and configuration:

```env
AWS_REGION=us-east-1
S3_BUCKET_NAME=your-actual-bucket-name

# Database (SQLite for development)
DATABASE_URL=sqlite:///./fastapi.db
REDIS_URL=redis://localhost:6379/0

# Security - CHANGE THIS!
LAMBDA_SECRET_KEY=your-strong-random-secret-key-here
```

## Step 2: Create AWS Lambda Function

### 2.1 Create Lambda Function in AWS Console

1. Go to AWS Lambda Console
2. Click "Create function"
3. Choose "Author from scratch"
4. Function name: `S3EventProcessor`
5. Runtime: Python 3.11 or 3.12
6. Click "Create function"

### 2.2 Upload Lambda Code

Copy the code from `lambda_function.py` to the Lambda function code editor, or:

```bash
# Create deployment package
zip lambda_deployment.zip lambda_function.py

# Upload via AWS CLI
aws lambda update-function-code \
    --function-name S3EventProcessor \
    --zip-file fileb://lambda_deployment.zip
```

### 2.3 Configure Lambda Environment Variables

In Lambda Console → Configuration → Environment variables, add:

- `FASTAPI_WEBHOOK_URL`: Your FastAPI webhook URL (e.g., `https://your-domain.com/webhook/lambda`)
- `LAMBDA_SECRET_KEY`: Same value as in your `.env` file

**For local development:**
- Use ngrok or similar tool to expose your local FastAPI: `ngrok http 8000`
- Set `FASTAPI_WEBHOOK_URL` to the ngrok URL (e.g., `https://abc123.ngrok.io/webhook/lambda`)

### 2.4 Increase Lambda Timeout

1. Configuration → General configuration → Edit
2. Set Timeout to 30 seconds (default 3 seconds might be too short)

## Step 3: Configure S3 EventBridge Integration

### 3.1 Enable EventBridge for S3 Bucket

```bash
# Via AWS CLI
aws s3api put-bucket-notification-configuration \
    --bucket your-bucket-name \
    --notification-configuration '{
      "EventBridgeConfiguration": {}
    }'
```

Or in AWS Console:
1. Go to S3 → Your bucket → Properties
2. Scroll to "Event notifications" or "Amazon EventBridge"
3. Enable "Send notifications to Amazon EventBridge"

### 3.2 Create EventBridge Rule

#### Via AWS Console:

1. Go to Amazon EventBridge → Rules
2. Click "Create rule"
3. Name: `S3-Upload-to-Lambda`
4. Event source: AWS events or EventBridge partner events
5. Event pattern:

```json
{
  "source": ["aws.s3"],
  "detail-type": ["Object Created"],
  "detail": {
    "bucket": {
      "name": ["your-bucket-name"]
    }
  }
}
```

6. Select target: Lambda function
7. Function: `S3EventProcessor`
8. Create rule

#### Via AWS CLI:

```bash
# Create event pattern file
cat > event-pattern.json << EOF
{
  "source": ["aws.s3"],
  "detail-type": ["Object Created"],
  "detail": {
    "bucket": {
      "name": ["your-bucket-name"]
    }
  }
}
EOF

# Create the rule
aws events put-rule \
    --name S3-Upload-to-Lambda \
    --event-pattern file://event-pattern.json \
    --state ENABLED

# Add Lambda as target
aws events put-targets \
    --rule S3-Upload-to-Lambda \
    --targets "Id"="1","Arn"="arn:aws:lambda:REGION:ACCOUNT_ID:function:S3EventProcessor"

# Grant EventBridge permission to invoke Lambda
aws lambda add-permission \
    --function-name S3EventProcessor \
    --statement-id EventBridgeInvoke \
    --action lambda:InvokeFunction \
    --principal events.amazonaws.com \
    --source-arn arn:aws:events:REGION:ACCOUNT_ID:rule/S3-Upload-to-Lambda
```

## Step 4: IAM Permissions

### Lambda Execution Role

Your Lambda function needs these permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:GetObjectMetadata"
      ],
      "Resource": "arn:aws:s3:::your-bucket-name/*"
    }
  ]
}
```

## Step 5: Test the Integration

### 5.1 Start FastAPI Backend

```bash
# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Start server
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 5.2 If Testing Locally with ngrok

```bash
# In another terminal
ngrok http 8000

# Update Lambda environment variable with ngrok URL
```

### 5.3 Upload Test File to S3

```bash
# Via AWS CLI
echo "Test content" > test.txt
aws s3 cp test.txt s3://your-bucket-name/test.txt

# Or use S3 Console
```

### 5.4 Monitor the Flow

1. **CloudWatch Logs**: Check Lambda execution logs
   - Go to Lambda → Monitor → View logs in CloudWatch
   
2. **FastAPI Logs**: Check terminal output
   - You should see: `INFO:main:Received Lambda webhook for event: ...`

3. **Test WebSocket**: Open `test_websocket.html` in browser

## Step 6: Production Deployment

### For Production FastAPI:

1. **Deploy to EC2/ECS/Lambda**
2. **Use PostgreSQL instead of SQLite**
   ```env
   DATABASE_URL=postgresql://user:pass@host:5432/dbname
   ```
3. **Deploy Redis**
   - Use AWS ElastiCache or Redis Cloud
4. **Use HTTPS with SSL certificate**
5. **Configure proper CORS**
6. **Set up monitoring and logging**

### Security Best Practices:

1. **Rotate secrets regularly**
2. **Use AWS Secrets Manager** for credentials
3. **Restrict CORS** to your frontend domain
4. **Use VPC** for Lambda and RDS
5. **Enable CloudWatch alarms**
6. **Use rate limiting** on webhook endpoint

## Troubleshooting

### Lambda can't reach FastAPI:
- Check Lambda has internet access (NAT Gateway if in VPC)
- Verify FASTAPI_WEBHOOK_URL is correct
- Check security groups/firewall

### EventBridge not triggering Lambda:
- Verify EventBridge is enabled on S3 bucket
- Check event pattern matches your uploads
- Review CloudWatch logs for Lambda invocations

### FastAPI not receiving events:
- Check Lambda logs for HTTP errors
- Verify secret key matches
- Test webhook endpoint directly with curl

### WebSocket not connecting:
- Check CORS configuration
- Verify server is running on correct port
- Check browser console for errors
