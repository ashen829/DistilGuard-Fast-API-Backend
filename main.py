from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import Optional, List
import logging
import json
import os
from datetime import datetime

from config import get_settings
from database import get_db, init_db, redis_client, S3Event, FileContent
from schemas import LambdaPayload, WebSocketMessage, FileDownloadRequest, EventResponse
from aws_client import s3_client
from websocket_manager import manager
from fl_session_watcher import FLSessionWatcher
from s3_fl_processor import S3FLFileProcessor
from chatbot_router import router as chatbot_router

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Settings
settings = get_settings()

# FastAPI app
app = FastAPI(title="S3 Event Processing API", version="1.0.0")

# FL Session Watcher
fl_watcher = None


# ============================================================================
# DATA TRANSFORMATION ADAPTERS
# ============================================================================

def normalize_value(value, default=0.0):
    """Normalize null/None values to default."""
    return default if value is None else float(value)


def transform_to_global_metrics(round_data):
    """Transform round JSON to GlobalMetrics format."""
    metadata = round_data.get("metadata", {})
    global_metrics = round_data.get("globalMetrics", {})
    round_summary = round_data.get("roundSummary", {})
    
    # Get accuracy with fallback logic
    accuracy = global_metrics.get("accuracy") or round_summary.get("accuracy")
    if accuracy is None:
        # Compute from active clients
        clients = round_data.get("clients", [])
        active = [c for c in clients if c.get("accuracy") is not None]
        accuracy = sum(c["accuracy"] for c in active) / len(active) if active else 0.0
    
    accuracy_percent = normalize_value(accuracy) * 100
    loss = global_metrics.get("loss") or round_summary.get("loss")
    
    return {
        "accuracy": round(accuracy_percent, 2),
        "loss": round(normalize_value(loss), 4),
        "currentRound": metadata.get("round", 0),
        "totalClients": global_metrics.get("totalClients", 0),
        "activeMaliciousClients": global_metrics.get("activeMaliciousClients", 0),
        "defenseSuccessRate": round(normalize_value(global_metrics.get("defenseSuccessRate")), 2),
        "isConnected": True,
        "timestamp": metadata.get("timestamp", datetime.utcnow().isoformat() + "Z")
    }

# S3 FL File Processor
s3_processor = None

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include chatbot router
app.include_router(chatbot_router, prefix="/api")


@app.on_event("startup")
async def startup_event():
    """Initialize database and Redis on startup"""
    global fl_watcher, s3_processor
    logger.info("Starting up application...")
    init_db()
    try:
        await redis_client.connect()
        logger.info("Redis connected successfully")
    except Exception as e:
        logger.warning(f"Redis not available: {e}")
    
    # Initialize FL Session Watcher
    sessions_path = os.getenv("FL_SESSIONS_PATH", "sessions")
    fl_watcher = FLSessionWatcher(manager, sessions_path)
    await fl_watcher.start()
    
    # Initialize S3 FL File Processor
    s3_processor = S3FLFileProcessor(manager, sessions_path)
    logger.info("S3 FL File Processor initialized")
    
    logger.info("Application started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global fl_watcher
    logger.info("Shutting down application...")
    try:
        await redis_client.disconnect()
    except Exception as e:
        logger.warning(f"Redis disconnect error: {e}")
    
    # Stop FL Session Watcher
    if fl_watcher:
        fl_watcher.stop()


@app.get("/")
def root():
    return {
        "message": "FastAPI S3 Event Processing Backend",
        "version": "1.0.0",
        "endpoints": {
            "webhook": "/webhook/lambda",
            "websocket": "/ws",
            "events": "/events",
            "download": "/s3/download"
        }
    }


@app.post("/webhook/lambda")
async def lambda_webhook(
    payload: LambdaPayload,
    db: Session = Depends(get_db)
):
    """
    Endpoint for Lambda to POST S3 event data
    Lambda should send small JSON payload about the S3 event
    Automatically downloads, stores, and broadcasts FL session files
    """
    # Verify secret key
    if payload.secret_key != settings.lambda_secret_key:
        logger.warning(f"Unauthorized webhook attempt with invalid secret")
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    logger.info(f"Received Lambda webhook for event: {payload.event_id}")
    
    try:
        # Check if event already exists (Lambda may send duplicates)
        existing_event = db.query(S3Event).filter(S3Event.event_id == payload.event_id).first()
        
        if existing_event:
            logger.info(f"Event {payload.event_id} already exists, skipping duplicate")
            db_event = existing_event
        else:
            # Store new event in database
            db_event = S3Event(
                event_id=payload.event_id,
                bucket=payload.bucket,
                key=payload.key,
                event_name=payload.event_name,
                event_time=datetime.fromisoformat(payload.event_time.replace('Z', '+00:00')),
                file_size=payload.size,
                content_type=payload.content_type,
                event_metadata=payload.metadata,
                processed=0
            )
            db.add(db_event)
            db.commit()
            db.refresh(db_event)
        
        # Store in Redis for quick access (optional)
        try:
            await redis_client.set(
                f"event:{payload.event_id}",
                json.dumps({
                    "bucket": payload.bucket,
                    "key": payload.key,
                    "event_name": payload.event_name,
                    "timestamp": payload.event_time
                }),
                expiration=3600  # 1 hour
            )
        except Exception as redis_error:
            logger.warning(f"Redis not available: {redis_error}")
        
        # Broadcast initial S3 event notification
        ws_message = {
            "type": "s3_upload_detected",
            "event_id": payload.event_id,
            "bucket": payload.bucket,
            "key": payload.key,
            "event_name": payload.event_name,
            "timestamp": payload.event_time,
            "size": payload.size,
            "content_type": payload.content_type,
            "data": payload.metadata
        }
        await manager.broadcast(ws_message)
        
        # Process FL session file if applicable (wait for download to complete)
        if s3_processor:
            event_data = {
                "event_id": payload.event_id,
                "bucket": payload.bucket,
                "key": payload.key,
                "event_name": payload.event_name,
                "event_time": payload.event_time
            }
            # Process synchronously - wait for download and processing to complete
            await s3_processor.process_s3_event(event_data, db)
        
        logger.info(f"Event {payload.event_id} processed and broadcasted")
        
        return {
            "status": "success",
            "event_id": payload.event_id,
            "message": "Event received and processing started"
        }
    
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/s3/download")
async def download_from_s3(
    request: FileDownloadRequest,
    db: Session = Depends(get_db)
):
    """
    Download file content from S3
    Optionally store in database if needed
    """
    try:
        logger.info(f"Downloading file from S3: {request.s3_key}")
        
        # Download file from S3
        file_content = await s3_client.get_file(request.s3_key)
        file_metadata = await s3_client.get_file_metadata(request.s3_key)
        
        # Store in database if requested
        if request.store_in_db:
            # Find related event
            event = db.query(S3Event).filter(S3Event.key == request.s3_key).first()
            
            db_file = FileContent(
                event_id=event.event_id if event else None,
                s3_key=request.s3_key,
                content=file_content.decode('utf-8', errors='ignore'),  # Adjust encoding as needed
            )
            db.add(db_file)
            db.commit()
        
        return {
            "status": "success",
            "key": request.s3_key,
            "size": file_metadata['size'],
            "content_type": file_metadata['content_type'],
            "stored_in_db": request.store_in_db,
            "content_preview": file_content[:500].decode('utf-8', errors='ignore')  # First 500 bytes
        }
    
    except Exception as e:
        logger.error(f"Error downloading from S3: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/s3/presigned-url/{s3_key:path}")
async def get_presigned_url(s3_key: str, expiration: int = 3600):
    """
    Generate a presigned URL for S3 object
    Useful for large files - frontend can download directly
    """
    try:
        url = await s3_client.generate_presigned_url(s3_key, expiration)
        return {
            "status": "success",
            "s3_key": s3_key,
            "url": url,
            "expires_in": expiration
        }
    except Exception as e:
        logger.error(f"Error generating presigned URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/events", response_model=List[EventResponse])
async def get_events(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get list of S3 events"""
    events = db.query(S3Event).order_by(S3Event.created_at.desc()).offset(skip).limit(limit).all()
    return events


@app.get("/events/{event_id}", response_model=EventResponse)
async def get_event(event_id: str, db: Session = Depends(get_db)):
    """Get specific event by ID"""
    event = db.query(S3Event).filter(S3Event.event_id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time updates
    Frontend connects here to receive S3 event notifications
    """
    await manager.connect(websocket)
    
    try:
        # Send initial connection message
        await manager.send_personal_message({
            "type": "CONNECTED",
            "message": "Connected to S3 Event Stream",
            "timestamp": datetime.utcnow().isoformat()
        }, websocket)
        
        # Keep connection alive and handle incoming messages
        while True:
            data = await websocket.receive_text()
            logger.info(f"Received WebSocket message: {data}")
            
            # Echo back or handle client messages if needed
            try:
                message = json.loads(data)
                if message.get("type") == "ping":
                    await manager.send_personal_message({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    }, websocket)
            except json.JSONDecodeError:
                pass
    
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "active_websocket_connections": len(manager.active_connections)
    }


# ==================== FL Session Endpoints ====================

@app.get("/api/sessions")
async def get_sessions():
    """Get all FL training sessions"""
    if not fl_watcher:
        raise HTTPException(status_code=503, detail="Session watcher not initialized")
    
    sessions = fl_watcher.get_all_sessions()
    return {"sessions": sessions, "count": len(sessions)}


@app.get("/api/sessions/latest")
async def get_latest_session():
    """Get the most recent session"""
    if not fl_watcher:
        raise HTTPException(status_code=503, detail="Session watcher not initialized")
    
    latest = fl_watcher.get_latest_session()
    if not latest:
        raise HTTPException(status_code=404, detail="No sessions found")
    
    session_id = os.path.basename(latest)
    rounds = fl_watcher.get_session_rounds(session_id)
    summary = fl_watcher.load_session_summary(session_id)
    
    return {
        "sessionId": session_id,
        "rounds": rounds,
        "totalRounds": len(rounds),
        "summary": summary
    }


@app.get("/api/sessions/{session_id}")
async def get_session_details(session_id: str):
    """Get details of a specific session"""
    if not fl_watcher:
        raise HTTPException(status_code=503, detail="Session watcher not initialized")
    
    rounds = fl_watcher.get_session_rounds(session_id)
    summary = fl_watcher.load_session_summary(session_id)
    
    if not rounds and not summary:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "sessionId": session_id,
        "rounds": rounds,
        "totalRounds": len(rounds),
        "summary": summary
    }


@app.get("/api/sessions/{session_id}/rounds/{round_num}")
async def get_round_data(session_id: str, round_num: int):
    """Get data for a specific round"""
    if not fl_watcher:
        raise HTTPException(status_code=503, detail="Session watcher not initialized")
    
    round_file = f"round_{round_num:03d}.json"
    data = fl_watcher.load_round_data(session_id, round_file)
    
    if not data:
        raise HTTPException(status_code=404, detail="Round data not found")
    
    return data


# ==================== Database Query Endpoints ====================

@app.get("/api/db/sessions")
async def get_db_sessions(db: Session = Depends(get_db)):
    """Get all FL sessions from database"""
    try:
        from database import FLSession
        sessions = db.query(FLSession).order_by(FLSession.created_at.desc()).all()
        
        return {
            "sessions": [
                {
                    "sessionId": s.session_id,
                    "s3Bucket": s.s3_bucket,
                    "s3Prefix": s.s3_prefix,
                    "totalRounds": s.total_rounds,
                    "startTime": s.start_time.isoformat() if s.start_time else None,
                    "endTime": s.end_time.isoformat() if s.end_time else None,
                    "status": s.status,
                    "summary": s.summary,
                    "createdAt": s.created_at.isoformat(),
                    "updatedAt": s.updated_at.isoformat()
                }
                for s in sessions
            ],
            "count": len(sessions)
        }
    except Exception as e:
        logger.error(f"Error fetching sessions from database: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/db/sessions/{session_id}")
async def get_db_session_details(session_id: str, db: Session = Depends(get_db)):
    """Get FL session details from database including all rounds"""
    try:
        from database import FLSession, FLRound
        
        session = db.query(FLSession).filter(FLSession.session_id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        rounds = db.query(FLRound).filter(
            FLRound.session_id == session_id
        ).order_by(FLRound.round_number).all()
        
        return {
            "sessionId": session.session_id,
            "s3Bucket": session.s3_bucket,
            "s3Prefix": session.s3_prefix,
            "totalRounds": session.total_rounds,
            "startTime": session.start_time.isoformat() if session.start_time else None,
            "endTime": session.end_time.isoformat() if session.end_time else None,
            "status": session.status,
            "summary": session.summary,
            "rounds": [
                {
                    "round": r.round_number,
                    "accuracy": r.accuracy,
                    "loss": r.loss,
                    "totalClients": r.total_clients,
                    "maliciousClients": r.malicious_clients,
                    "defenseSuccessRate": r.defense_success_rate,
                    "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                    "s3Key": r.s3_key
                }
                for r in rounds
            ],
            "createdAt": session.created_at.isoformat(),
            "updatedAt": session.updated_at.isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching session details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/db/sessions/{session_id}/rounds/{round_num}")
async def get_db_round_data(session_id: str, round_num: int, db: Session = Depends(get_db)):
    """Get specific round data from database"""
    try:
        from database import FLRound
        
        round_data = db.query(FLRound).filter(
            FLRound.session_id == session_id,
            FLRound.round_number == round_num
        ).first()
        
        if not round_data:
            raise HTTPException(status_code=404, detail="Round not found")
        
        return {
            "sessionId": session_id,
            "round": round_data.round_number,
            "accuracy": round_data.accuracy,
            "loss": round_data.loss,
            "totalClients": round_data.total_clients,
            "maliciousClients": round_data.malicious_clients,
            "defenseSuccessRate": round_data.defense_success_rate,
            "timestamp": round_data.timestamp.isoformat() if round_data.timestamp else None,
            "s3Key": round_data.s3_key,
            "fullData": round_data.round_data
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching round data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/db/sessions/{session_id}/metrics")
async def get_session_metrics(session_id: str, db: Session = Depends(get_db)):
    """Get aggregated metrics for a session"""
    try:
        from database import FLRound
        
        rounds = db.query(FLRound).filter(
            FLRound.session_id == session_id
        ).order_by(FLRound.round_number).all()
        
        if not rounds:
            raise HTTPException(status_code=404, detail="No rounds found for session")
        
        # Calculate metrics
        accuracies = [r.accuracy for r in rounds if r.accuracy is not None]
        losses = [r.loss for r in rounds if r.loss is not None]
        
        return {
            "sessionId": session_id,
            "totalRounds": len(rounds),
            "accuracyTrend": accuracies,
            "lossTrend": losses,
            "avgAccuracy": sum(accuracies) / len(accuracies) if accuracies else None,
            "avgLoss": sum(losses) / len(losses) if losses else None,
            "finalAccuracy": accuracies[-1] if accuracies else None,
            "finalLoss": losses[-1] if losses else None,
            "totalMaliciousDetected": sum(r.malicious_clients or 0 for r in rounds),
            "rounds": [
                {
                    "round": r.round_number,
                    "accuracy": r.accuracy,
                    "loss": r.loss,
                    "maliciousClients": r.malicious_clients,
                    "timestamp": r.timestamp.isoformat() if r.timestamp else None
                }
                for r in rounds
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating session metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/db/events")
async def get_s3_events(
    limit: int = 50,
    processed: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get S3 events from database"""
    try:
        from database import S3Event
        
        query = db.query(S3Event)
        
        if processed is not None:
            query = query.filter(S3Event.processed == processed)
        
        events = query.order_by(S3Event.created_at.desc()).limit(limit).all()
        
        return {
            "events": [
                {
                    "eventId": e.event_id,
                    "bucket": e.bucket,
                    "key": e.key,
                    "eventName": e.event_name,
                    "eventTime": e.event_time.isoformat() if e.event_time else None,
                    "fileSize": e.file_size,
                    "contentType": e.content_type,
                    "processed": e.processed,
                    "createdAt": e.created_at.isoformat()
                }
                for e in events
            ],
            "count": len(events)
        }
    except Exception as e:
        logger.error(f"Error fetching S3 events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/db/sessions")
async def get_db_sessions(db: Session = Depends(get_db)):
    """Get all FL sessions stored in database"""
    if not s3_processor:
        raise HTTPException(status_code=503, detail="S3 processor not initialized")
    
    sessions = s3_processor.get_stored_sessions(db)
    return {"sessions": sessions, "count": len(sessions)}


@app.get("/api/db/files")
async def get_db_files(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Get all files stored in database"""
    files = db.query(FileContent).order_by(
        FileContent.stored_at.desc()
    ).offset(offset).limit(limit).all()
    
    return {
        "files": [
            {
                "id": f.id,
                "event_id": f.event_id,
                "s3_key": f.s3_key,
                "content_hash": f.content_hash,
                "stored_at": f.stored_at.isoformat()
            }
            for f in files
        ],
        "count": len(files)
    }


@app.get("/api/db/file/{event_id}")
async def get_file_content(event_id: str, db: Session = Depends(get_db)):
    """Get file content from database by event ID"""
    file_record = db.query(FileContent).filter(
        FileContent.event_id == event_id
    ).first()
    
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found in database")
    
    try:
        content_json = json.loads(file_record.content)
        return {
            "event_id": file_record.event_id,
            "s3_key": file_record.s3_key,
            "stored_at": file_record.stored_at.isoformat(),
            "content": content_json
        }
    except json.JSONDecodeError:
        return {
            "event_id": file_record.event_id,
            "s3_key": file_record.s3_key,
            "stored_at": file_record.stored_at.isoformat(),
            "content": file_record.content
        }


@app.post("/api/s3/process/{event_id}")
async def manually_process_s3_file(event_id: str, db: Session = Depends(get_db)):
    """Manually trigger processing of an S3 file"""
    if not s3_processor:
        raise HTTPException(status_code=503, detail="S3 processor not initialized")
    
    # Get event from database
    event = db.query(S3Event).filter(S3Event.event_id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    event_data = {
        "event_id": event.event_id,
        "bucket": event.bucket,
        "key": event.key,
        "event_name": event.event_name,
        "event_time": event.event_time.isoformat()
    }
    
    # Process the file
    await s3_processor.process_s3_event(event_data, db)
    
    return {
        "status": "success",
        "message": f"File {event.key} processed successfully"
    }


# ============================================================================
# DASHBOARD-COMPATIBLE API ENDPOINTS
# ============================================================================

@app.get("/api/metrics/global")
async def get_global_metrics(db: Session = Depends(get_db)):
    """Get global model metrics from latest round."""
    try:
        # Get latest session
        latest_session = db.query(FileContent).filter(
            FileContent.s3_key.like("%summary.json")
        ).order_by(FileContent.stored_at.desc()).first()
        
        if not latest_session:
            return {"success": False, "error": "No active simulation"}
        
        summary = json.loads(latest_session.content)
        round_history = summary.get("roundHistory", [])
        
        if not round_history:
            return {"success": False, "error": "No rounds available"}
        
        # Get latest round
        latest_round = round_history[-1]
        metrics = transform_to_global_metrics(latest_round)
        
        return {"success": True, "data": metrics}
    except Exception as e:
        logger.error(f"Error getting global metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/training/rounds")
async def get_training_rounds(
    limit: Optional[int] = None,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Get training round history."""
    try:
        latest_session = db.query(FileContent).filter(
            FileContent.s3_key.like("%summary.json")
        ).order_by(FileContent.stored_at.desc()).first()
        
        if not latest_session:
            return {"success": True, "data": {"rounds": [], "total": 0, "timestamp": datetime.utcnow().isoformat() + "Z"}}
        
        summary = json.loads(latest_session.content)
        round_history = summary.get("roundHistory", [])
        
        rounds = []
        for round_data in round_history:
            metadata = round_data.get("metadata", {})
            round_summary = round_data.get("roundSummary", {})
            global_metrics = round_data.get("globalMetrics", {})
            
            accuracy = round_summary.get("accuracy") or global_metrics.get("accuracy")
            if accuracy is None:
                clients = round_data.get("clients", [])
                active = [c for c in clients if c.get("accuracy") is not None]
                accuracy = sum(c["accuracy"] for c in active) / len(active) if active else 0.0
            
            rounds.append({
                "round": metadata.get("round", 0),
                "accuracy": round(normalize_value(accuracy), 2),
                "loss": round(normalize_value(round_summary.get("loss") or global_metrics.get("loss")), 4),
                "defenseApplied": round_summary.get("defenseApplied", False),
                "maliciousClientsDetected": round_summary.get("maliciousClientsDetected", 0)
            })
        
        # Apply offset and limit
        total = len(rounds)
        if offset:
            rounds = rounds[offset:]
        if limit:
            rounds = rounds[:limit]
        
        return {
            "success": True,
            "data": {
                "rounds": rounds,
                "total": total,
                "limit": limit,
                "offset": offset,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        }
    except Exception as e:
        logger.error(f"Error getting training rounds: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/clients")
async def get_clients(
    type: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get all clients with optional filtering."""
    try:
        latest_session = db.query(FileContent).filter(
            FileContent.s3_key.like("%summary.json")
        ).order_by(FileContent.stored_at.desc()).first()
        
        if not latest_session:
            return {"success": True, "data": {"clients": [], "total": 0, "timestamp": datetime.utcnow().isoformat() + "Z"}}
        
        summary = json.loads(latest_session.content)
        round_history = summary.get("roundHistory", [])
        
        if not round_history:
            return {"success": True, "data": {"clients": [], "total": 0, "timestamp": datetime.utcnow().isoformat() + "Z"}}
        
        # Get latest round's clients
        latest_round = round_history[-1]
        clients = latest_round.get("clients", [])
        
        formatted_clients = []
        for client in clients:
            if type and client.get("type", "").lower() != type.lower():
                continue
            
            # Normalize trust score
            trust_score = client.get("trustScore")
            if trust_score is None:
                status_val = client.get("status", "Inactive")
                trust_score = 0.8 if status_val == "Active" else 0.5 if status_val == "Warning" else 0.3
            
            client_data = {
                "id": client.get("id", "unknown"),
                "type": client.get("type", "Unknown"),
                "status": client.get("status", "Inactive"),
                "trustScore": round(float(trust_score), 2),
                "accuracy": round(normalize_value(client.get("accuracy")) * 100, 2),
                "loss": round(normalize_value(client.get("loss")), 4),
                "divergence": round(normalize_value(client.get("divergence")), 4),
                "learningRate": client.get("learningRate", 0.01),
                "epochs": client.get("epochs", 5)
            }
            
            if client.get("attackType"):
                client_data["attackType"] = client["attackType"]
            
            if status and client_data["status"] != status:
                continue
            
            formatted_clients.append(client_data)
        
        return {
            "success": True,
            "data": {
                "clients": formatted_clients,
                "total": len(formatted_clients),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        }
    except Exception as e:
        logger.error(f"Error getting clients: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/alerts")
async def get_alerts(
    severity: Optional[str] = None,
    type: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get security alerts."""
    try:
        latest_session = db.query(FileContent).filter(
            FileContent.s3_key.like("%summary.json")
        ).order_by(FileContent.stored_at.desc()).first()
        
        if not latest_session:
            return {"success": True, "data": {"alerts": [], "total": 0, "timestamp": datetime.utcnow().isoformat() + "Z"}}
        
        summary = json.loads(latest_session.content)
        round_history = summary.get("roundHistory", [])
        
        all_alerts = []
        for round_data in round_history:
            round_alerts = round_data.get("alerts", [])
            for alert in round_alerts:
                if severity and alert.get("severity") != severity:
                    continue
                if type and alert.get("type") != type:
                    continue
                
                all_alerts.append({
                    "id": alert.get("id", ""),
                    "round": alert.get("round", 0),
                    "clientId": alert.get("clientId", ""),
                    "type": alert.get("type", "unknown"),
                    "severity": alert.get("severity", "medium"),
                    "message": alert.get("message", ""),
                    "timestamp": alert.get("timestamp", ""),
                    "acknowledged": alert.get("acknowledged", False)
                })
        
        # Sort by timestamp descending
        all_alerts.sort(key=lambda x: x["timestamp"], reverse=True)
        all_alerts = all_alerts[:limit]
        
        return {
            "success": True,
            "data": {
                "alerts": all_alerts,
                "total": len(all_alerts),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        }
    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/defense/metrics")
async def get_defense_metrics(db: Session = Depends(get_db)):
    """Get defense system metrics."""
    try:
        latest_session = db.query(FileContent).filter(
            FileContent.s3_key.like("%summary.json")
        ).order_by(FileContent.stored_at.desc()).first()
        
        if not latest_session:
            return {"success": False, "error": "No active simulation"}
        
        summary = json.loads(latest_session.content)
        round_history = summary.get("roundHistory", [])
        
        if not round_history:
            return {"success": False, "error": "No rounds available"}
        
        latest_round = round_history[-1]
        defense_metrics = latest_round.get("defenseMetrics", {})
        confusion_matrix = latest_round.get("confusionMatrix", {})
        clients = latest_round.get("clients", [])
        
        # Build trust score distribution
        trust_dist = [
            {"range": "0.0-0.2", "count": 0}, 
            {"range": "0.2-0.4", "count": 0}, 
            {"range": "0.4-0.6", "count": 0}, 
            {"range": "0.6-0.8", "count": 0}, 
            {"range": "0.8-1.0", "count": 0}
        ]
        
        for client in clients:
            trust_score = client.get("trustScore")
            if trust_score is None:
                status = client.get("status", "Inactive")
                trust_score = 0.8 if status == "Active" else 0.5 if status == "Warning" else 0.3
            
            trust_score = float(trust_score)
            idx = min(int(trust_score * 5), 4)
            trust_dist[idx]["count"] += 1
        
        return {
            "success": True,
            "data": {
                "metrics": {
                    "detectionRate": round(normalize_value(defense_metrics.get("recall")) * 100, 1),
                    "falsePositiveRate": round(normalize_value(defense_metrics.get("falsePositiveRate")), 1),
                    "precision": round(normalize_value(defense_metrics.get("precision")) * 100, 1),
                    "recall": round(normalize_value(defense_metrics.get("recall")) * 100, 1),
                    "defenseOverhead": round(normalize_value(defense_metrics.get("defenseOverhead")), 2),
                    "attackImpactReduction": round(normalize_value(defense_metrics.get("attackImpactReduction")), 1)
                },
                "trustScoreDistribution": trust_dist,
                "confusionMatrix": {
                    "truePositive": confusion_matrix.get("truePositive", 0),
                    "falsePositive": confusion_matrix.get("falsePositive", 0),
                    "trueNegative": confusion_matrix.get("trueNegative", 0),
                    "falseNegative": confusion_matrix.get("falseNegative", 0)
                },
                "timestamp": latest_round.get("metadata", {}).get("timestamp", datetime.utcnow().isoformat() + "Z")
            }
        }
    except Exception as e:
        logger.error(f"Error getting defense metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/logs")
async def get_logs(
    level: Optional[str] = None,
    limit: int = 100,
    since: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get system logs."""
    try:
        latest_session = db.query(FileContent).filter(
            FileContent.s3_key.like("%summary.json")
        ).order_by(FileContent.stored_at.desc()).first()
        
        if not latest_session:
            return {"success": True, "data": {"logs": [], "total": 0, "timestamp": datetime.utcnow().isoformat() + "Z"}}
        
        summary = json.loads(latest_session.content)
        round_history = summary.get("roundHistory", [])
        
        logs = []
        log_id = 1
        
        for round_data in round_history:
            metadata = round_data.get("metadata", {})
            round_num = metadata.get("round", 0)
            timestamp = metadata.get("timestamp", "")
            round_summary = round_data.get("roundSummary", {})
            
            # Round start
            logs.append({
                "id": f"log_{log_id}", 
                "timestamp": timestamp, 
                "level": "info", 
                "message": f"Round {round_num} started"
            })
            log_id += 1
            
            # Defense detection
            if round_summary.get("defenseApplied"):
                detected = round_summary.get("maliciousClientsDetected", 0)
                log_level = "warning" if detected > 0 else "info"
                if not level or log_level == level:
                    logs.append({
                        "id": f"log_{log_id}", 
                        "timestamp": timestamp, 
                        "level": log_level,
                        "message": f"Defense detected {detected} malicious client(s) in round {round_num}"
                    })
                log_id += 1
            
            # Alerts
            for alert in round_data.get("alerts", []):
                alert_level = "error" if alert.get("severity") == "high" else "warning"
                if not level or alert_level == level:
                    logs.append({
                        "id": f"log_{log_id}", 
                        "timestamp": alert.get("timestamp", timestamp),
                        "level": alert_level, 
                        "message": alert.get("message", "")
                    })
                log_id += 1
            
            # Round complete
            duration = round_summary.get("duration", 0)
            logs.append({
                "id": f"log_{log_id}", 
                "timestamp": timestamp, 
                "level": "info",
                "message": f"Round {round_num} completed in {duration:.2f}s"
            })
            log_id += 1
        
        logs.sort(key=lambda x: x["timestamp"], reverse=True)
        logs = logs[:limit]
        
        return {
            "success": True,
            "data": {
                "logs": logs,
                "total": len(logs),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        }
    except Exception as e:
        logger.error(f"Error getting logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

