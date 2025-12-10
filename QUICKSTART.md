# 🚀 Quick Start Guide

## ✅ Your Server is Running!

FastAPI is live at: **http://localhost:8000**

## 🎯 Test It Right Now (3 Steps)

### Step 1: Test the API (30 seconds)

Open PowerShell and run:

```powershell
# Test if server is working
curl http://localhost:8000/

# Check health
curl http://localhost:8000/health
```

### Step 2: Open WebSocket Dashboard (1 minute)

1. Double-click `test_websocket.html` in File Explorer
2. Click the **"Connect"** button
3. You should see status change to "Connected" 🟢

### Step 3: Send a Test Event (2 minutes)

In PowerShell, copy and paste this:

```powershell
$payload = @{
    event_id = "test-$(Get-Date -Format 'yyyyMMddHHmmss')"
    bucket = "my-test-bucket"
    key = "uploads/demo-file.txt"
    event_name = "ObjectCreated:Put"
    event_time = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    size = 2048
    content_type = "text/plain"
    metadata = @{ test = "true" }
    secret_key = "change-this-to-a-random-secret-key"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/webhook/lambda" -Method Post -Body $payload -ContentType "application/json"
```

**Watch the magic!** ✨ The event should appear in your WebSocket dashboard instantly!

---

## 📝 What to Do Next

### Option A: Deploy to AWS (Recommended for Production)

Follow **AWS_SETUP.md** to:
1. Create AWS Lambda function
2. Configure S3 EventBridge
3. Connect real S3 uploads to your backend

### Option B: Integrate with Next.js Frontend

Copy **NEXTJS_EXAMPLE.tsx** to your Next.js project and use the component.

### Option C: Configure for Production

1. Update `.env` with:
   - Your actual S3 bucket name
   - A strong random secret key
   - PostgreSQL connection (instead of SQLite)
   - Redis connection

2. Deploy FastAPI:
   - AWS EC2
   - Heroku
   - Railway
   - Render

---

## 🔧 Common Commands

```powershell
# Start server (if not running)
.\venv\Scripts\Activate.ps1
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Stop server
# Press Ctrl+C in the terminal

# View logs
# Watch the terminal where uvicorn is running

# Check database
sqlite3 fastapi.db
.tables
SELECT * FROM s3_events;
.exit

# Install additional packages
.\venv\Scripts\python.exe -m pip install package-name
```

---

## 📚 Documentation Files

| File | What's Inside |
|------|---------------|
| **SUMMARY.md** | Complete overview of what was created |
| **README.md** | Main project documentation |
| **AWS_SETUP.md** | Step-by-step AWS configuration |
| **TESTING.md** | Full testing guide with examples |
| **NEXTJS_EXAMPLE.tsx** | React component for your frontend |

---

## ✅ Checklist for Going Live

- [ ] Update S3_BUCKET_NAME in `.env`
- [ ] Generate strong LAMBDA_SECRET_KEY
- [ ] Deploy Lambda function (AWS_SETUP.md)
- [ ] Enable S3 EventBridge notifications
- [ ] Create EventBridge rule
- [ ] Test with real S3 upload
- [ ] Deploy FastAPI to production server
- [ ] Switch to PostgreSQL database
- [ ] Deploy Redis server
- [ ] Enable HTTPS
- [ ] Configure CORS for your domain
- [ ] Set up monitoring/logging

---

## 💡 Pro Tips

1. **Keep the terminal window open** to see real-time logs
2. **Use test_websocket.html** for instant visual feedback during development
3. **Check TESTING.md** for more advanced test scenarios
4. **The server auto-reloads** when you edit Python files (--reload flag)

---

## 🆘 Need Help?

**Server not starting?**
- Check if port 8000 is already in use
- Verify virtual environment is activated
- Review terminal error messages

**WebSocket won't connect?**
- Make sure server is running on http://0.0.0.0:8000
- Check browser console for errors (F12)
- Try clicking "Connect" button again

**Events not appearing?**
- Verify secret key matches in payload and .env
- Check FastAPI terminal logs
- Ensure WebSocket is connected (green status)

---

**You're all set! Happy coding! 🎉**
