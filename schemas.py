from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class LambdaPayload(BaseModel):
    """Payload sent from Lambda to FastAPI"""
    event_id: str
    bucket: str
    key: str
    event_name: str
    event_time: str
    size: Optional[int] = None
    content_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    secret_key: str  # For authentication


class WebSocketMessage(BaseModel):
    """Message format for WebSocket broadcasts"""
    type: str  # e.g., "new_upload", "file_processed", "error"
    event_id: str
    bucket: str
    key: str
    timestamp: str
    data: Optional[Dict[str, Any]] = None


class FileDownloadRequest(BaseModel):
    """Request to download file from S3"""
    s3_key: str
    store_in_db: bool = False


class EventResponse(BaseModel):
    """Response for event queries"""
    id: int
    event_id: str
    bucket: str
    key: str
    event_name: str
    event_time: datetime
    file_size: Optional[int]
    content_type: Optional[str]
    processed: int
    created_at: datetime
    
    class Config:
        from_attributes = True
