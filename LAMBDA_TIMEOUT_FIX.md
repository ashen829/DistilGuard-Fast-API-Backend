# Lambda Timeout Fix - Testing Options

## Problem
Lambda in AWS cannot reach your local computer at localhost or 192.168.x.x

## Quick Fix Options

### Option 1: Use ngrok (Recommended for Testing)

1. **Download ngrok**: https://ngrok.com/download
2. **Install**: Extract the zip file
3. **Run in PowerShell**:
   ```powershell
   cd path\to\ngrok
   .\ngrok http 8000
   ```
4. **You'll see output like**:
   ```
   Forwarding  https://abc123.ngrok.io -> http://localhost:8000
   ```
5. **Copy the https URL** (e.g., `https://abc123.ngrok.io`)
6. **Update Lambda Environment Variable**:
   - Go to Lambda → Configuration → Environment variables
   - Edit `FASTAPI_WEBHOOK_URL`
   - New value: `https://abc123.ngrok.io/webhook/lambda`
   - Click Save
7. **Test Lambda again** - should work now!

⏰ ngrok free tier: URLs change each time you restart

---

### Option 2: Deploy FastAPI to AWS EC2 (Production Solution)

1. Launch EC2 instance (t2.micro is free tier)
2. Install Python and dependencies
3. Run FastAPI with: `uvicorn main:app --host 0.0.0.0 --port 8000`
4. Get EC2 public IP (e.g., 54.123.45.67)
5. Update Lambda: `http://54.123.45.67:8000/webhook/lambda`

Security: Add inbound rule in Security Group for port 8000

---

### Option 3: Use AWS Lambda Function URL (Easiest Production)

Deploy FastAPI as a Lambda function itself:
- Use Mangum adapter for FastAPI
- Get automatic HTTPS URL
- No server management needed

---

### Option 4: Test Lambda Locally Without Network

**For now, to verify Lambda code works:**

Update your Lambda function to just print the event:

```python
def lambda_handler(event, context):
    print(f"Received event: {json.dumps(event)}")
    
    # Skip FastAPI call for testing
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Event received (FastAPI call skipped for testing)'
        })
    }
```

This lets you verify EventBridge → Lambda works.
Add FastAPI call back later when you have a public URL.

---

## Recommended Flow

**For Development/Testing:**
```
S3 → EventBridge → Lambda (stores in S3 or DynamoDB)
                     ↓
              FastAPI reads from S3/DynamoDB
```

**For Production:**
```
S3 → EventBridge → Lambda → FastAPI (on EC2/ECS/Lambda)
                              ↓
                         WebSocket → Frontend
```

---

## Current Status Check

Your FastAPI is running on: `localhost:8000`
Lambda is trying to reach: `FASTAPI_WEBHOOK_URL` environment variable

**Lambda needs a PUBLIC URL** - it can't access localhost!
