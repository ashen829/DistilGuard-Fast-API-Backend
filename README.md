# FastAPI S3 Event Processing Backend

This FastAPI backend receives S3 upload events from AWS Lambda and broadcasts them to a Next.js frontend via WebSockets.

## ✨ Features

- 🚀 Real-time S3 upload notifications via WebSocket
- 📦 AWS S3 integration with boto3
- 💾 SQLite/PostgreSQL database for event storage
- ⚡ Redis caching (optional)
- 🔒 Secure webhook with secret key authentication
- 📊 REST API for event queries
- 🎯 Lambda function included for AWS EventBridge integration

## Architecture

```
S3 Upload → EventBridge → Lambda
                           ↓ (POST small JSON payload)
                        FastAPI
                           ↓
                    ┌──────┴──────┐
                    ↓             ↓
              SQLite/PostgreSQL  WebSocket
                  +              ↓
                Redis      Next.js Frontend
```

## 📁 Project Structure

```
fast-api-backend/
├── main.py                 # FastAPI application with all endpoints
├── config.py              # Settings and environment configuration
├── database.py            # SQLAlchemy models and Redis client
├── aws_client.py          # AWS S3 client wrapper
├── websocket_manager.py   # WebSocket connection manager
├── schemas.py             # Pydantic models for validation
├── lambda_function.py     # AWS Lambda function code
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables (DO NOT commit)
├── README.md              # This file
├── AWS_SETUP.md          # Detailed AWS configuration guide
├── TESTING.md            # Testing instructions and examples
├── NEXTJS_EXAMPLE.tsx    # Next.js React component example
└── test_websocket.html   # Browser-based WebSocket tester
```

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- AWS Account with S3 access
- (Optional) PostgreSQL and Redis for production

### 1. Clone and Setup

```powershell
# Navigate to project
cd fast-api-backend

# Create virtual environment (already done)
python -m venv venv

# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

Update `.env` file:
```env
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_key_here
AWS_REGION=us-east-1
S3_BUCKET_NAME=your-bucket-name

DATABASE_URL=sqlite:///./fastapi.db
REDIS_URL=redis://localhost:6379/0

LAMBDA_SECRET_KEY=generate-a-strong-random-key
```

### 3. Run the Server

```powershell
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Server will start at: `http://localhost:8000`

### 4. Test the Setup

1. **Test basic endpoint:**
   ```powershell
   curl http://localhost:8000/
   ```

2. **Open WebSocket dashboard:**
   - Double-click `test_websocket.html`
   - Click "Connect" button

3. **Send test event:**
   See `TESTING.md` for detailed testing examples

## 📚 Documentation

- **[AWS_SETUP.md](AWS_SETUP.md)** - Complete AWS Lambda and EventBridge setup
- **[TESTING.md](TESTING.md)** - Testing guide with PowerShell examples
- **[NEXTJS_EXAMPLE.tsx](NEXTJS_EXAMPLE.tsx)** - Next.js React component integration

## 🔌 API Endpoints

### Webhook
- **POST** `/webhook/lambda` - Receive S3 events from Lambda

### WebSocket  
- **WebSocket** `/ws` - Real-time event stream

### Events
- **GET** `/events` - List all events (paginated)
- **GET** `/events/{event_id}` - Get specific event

### S3 Operations
- **POST** `/s3/download` - Download file from S3
- **GET** `/s3/presigned-url/{s3_key}` - Generate presigned URL

### Utility
- **GET** `/` - API information
- **GET** `/health` - Health check

## 🔒 Security Notes

For production deployment:

1. ✅ Use HTTPS only
2. ✅ Configure CORS for your specific frontend domain
3. ✅ Use environment variables for all secrets
4. ✅ Rotate `LAMBDA_SECRET_KEY` regularly
5. ✅ Use AWS IAM roles instead of access keys when possible
6. ✅ Implement rate limiting
7. ✅ Use PostgreSQL instead of SQLite
8. ✅ Deploy Redis with authentication

## 📝 Next Steps

1. **Configure AWS Lambda** - Follow `AWS_SETUP.md`
2. **Set up S3 EventBridge** - Enable event notifications
3. **Deploy to Production** - Use Docker/EC2/Lambda
4. **Integrate Next.js Frontend** - Use `NEXTJS_EXAMPLE.tsx`
5. **Monitor with CloudWatch** - Set up logging and alarms

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| WebSocket won't connect | Check CORS settings in `main.py` |
| Events not received | Verify Lambda secret key matches |
| Database errors | Delete `fastapi.db` and restart |
| S3 access denied | Check AWS credentials and IAM permissions |
| Redis connection failed | Make Redis optional or install locally |

## 📊 Monitoring

Check logs in terminal for:
- ✅ Connection confirmations
- 📨 Incoming webhook events  
- 🔌 WebSocket connections/disconnections
- ❌ Errors and exceptions

## 🤝 Contributing

Feel free to enhance this project:
- Add authentication/authorization
- Implement file processing workflows
- Add more event types
- Enhance error handling
- Add unit tests

## 📄 License

This project is for educational purposes.

---

**Made with ❤️ using FastAPI and AWS**
