# Test the FastAPI Backend

## 1. Test Basic Endpoint

```powershell
# Test root endpoint
curl http://localhost:8000/

# Expected output:
# {
#   "message": "FastAPI S3 Event Processing Backend",
#   "version": "1.0.0",
#   "endpoints": {...}
# }
```

## 2. Test Health Check

```powershell
curl http://localhost:8000/health
```

## 3. Test Webhook Endpoint (Simulating Lambda)

```powershell
# Create test payload
$payload = @{
    event_id = "test-event-$(Get-Date -Format 'yyyyMMddHHmmss')"
    bucket = "my-test-bucket"
    key = "uploads/test-file.txt"
    event_name = "ObjectCreated:Put"
    event_time = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    size = 1024
    content_type = "text/plain"
    metadata = @{
        uploader = "test-user"
        region = "us-east-1"
    }
    secret_key = "change-this-to-a-random-secret-key"
} | ConvertTo-Json

# Send to webhook
Invoke-RestMethod -Uri "http://localhost:8000/webhook/lambda" `
    -Method Post `
    -Body $payload `
    -ContentType "application/json"
```

## 4. Test Events Endpoint

```powershell
# Get all events
curl http://localhost:8000/events

# Get specific event
curl "http://localhost:8000/events/test-event-20251209120000"
```

## 5. Test WebSocket

Open `test_websocket.html` in your browser:
1. Double-click the file to open in browser
2. Click "Connect" button
3. You should see connection status change to "Connected"
4. Send a test webhook (step 3 above)
5. Watch the event appear in real-time!

## 6. Test S3 Operations (Requires AWS Credentials)

First, update `.env` with your S3 bucket name, then:

```powershell
# Test file download
$downloadPayload = @{
    s3_key = "path/to/your/file.txt"
    store_in_db = $false
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/s3/download" `
    -Method Post `
    -Body $downloadPayload `
    -ContentType "application/json"
```

```powershell
# Test presigned URL generation
curl "http://localhost:8000/s3/presigned-url/path/to/your/file.txt?expiration=3600"
```

## 7. Load Testing with Multiple Events

```powershell
# Send 10 test events
1..10 | ForEach-Object {
    $payload = @{
        event_id = "load-test-$_-$(Get-Date -Format 'yyyyMMddHHmmss')"
        bucket = "my-test-bucket"
        key = "uploads/load-test-$_.txt"
        event_name = "ObjectCreated:Put"
        event_time = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        size = Get-Random -Minimum 1024 -Maximum 10240
        content_type = "text/plain"
        metadata = @{ test_number = $_ }
        secret_key = "change-this-to-a-random-secret-key"
    } | ConvertTo-Json

    Invoke-RestMethod -Uri "http://localhost:8000/webhook/lambda" `
        -Method Post `
        -Body $payload `
        -ContentType "application/json"
    
    Write-Host "Sent event $_"
    Start-Sleep -Milliseconds 500
}
```

## 8. Database Inspection

The SQLite database file is created at `./fastapi.db`. You can inspect it:

```powershell
# Install SQLite (if needed)
# Download from https://www.sqlite.org/download.html

# Open database
sqlite3 fastapi.db

# In SQLite shell:
.tables                    # Show all tables
SELECT * FROM s3_events;   # View all events
.exit                      # Exit SQLite
```

## Expected Flow

1. **FastAPI starts** → Database tables are created
2. **WebSocket connects** → Browser receives connection confirmation
3. **Lambda sends event** → FastAPI receives webhook POST
4. **Event stored** → Database and Redis updated
5. **WebSocket broadcast** → All connected clients receive event
6. **Dashboard updates** → Real-time display in browser

## Troubleshooting

### Connection Refused
- Check if FastAPI is running: `curl http://localhost:8000/health`
- Verify port 8000 is not blocked by firewall

### WebSocket Not Connecting
- Check browser console for errors (F12)
- Verify CORS configuration in `main.py`
- Try connecting with WebSocket test tool

### Events Not Appearing
- Check secret key matches in payload and `.env`
- Review FastAPI logs in terminal
- Verify event is stored: `curl http://localhost:8000/events`

### Database Errors
- Delete `fastapi.db` and restart server
- Check file permissions
- Review terminal logs for SQL errors
