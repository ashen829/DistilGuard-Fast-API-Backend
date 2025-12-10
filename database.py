from sqlalchemy import create_engine, Column, Integer, String, DateTime, JSON, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from config import get_settings
import redis.asyncio as redis

settings = get_settings()

# PostgreSQL setup
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# Redis setup
class RedisClient:
    def __init__(self):
        self.redis = None
    
    async def connect(self):
        self.redis = await redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True
        )
    
    async def disconnect(self):
        if self.redis:
            await self.redis.close()
    
    async def set(self, key: str, value: str, expiration: int = None):
        if expiration:
            await self.redis.setex(key, expiration, value)
        else:
            await self.redis.set(key, value)
    
    async def get(self, key: str):
        return await self.redis.get(key)
    
    async def publish(self, channel: str, message: str):
        await self.redis.publish(channel, message)


redis_client = RedisClient()


# Database Models
class S3Event(Base):
    __tablename__ = "s3_events"
    
    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String, unique=True, index=True)
    bucket = Column(String)
    key = Column(String)
    event_name = Column(String)
    event_time = Column(DateTime, default=datetime.utcnow)
    file_size = Column(Integer, nullable=True)
    content_type = Column(String, nullable=True)
    event_metadata = Column(JSON, nullable=True)  # Renamed from 'metadata'
    processed = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class FileContent(Base):
    __tablename__ = "file_contents"
    
    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String, index=True)
    s3_key = Column(String)
    content = Column(Text, nullable=True)
    content_hash = Column(String, nullable=True)
    stored_at = Column(DateTime, default=datetime.utcnow)


class FLSession(Base):
    __tablename__ = "fl_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True)
    s3_bucket = Column(String, nullable=True)
    s3_prefix = Column(String, nullable=True)
    total_rounds = Column(Integer, default=0)
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    status = Column(String, default="active")  # active, completed, failed
    summary = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FLRound(Base):
    __tablename__ = "fl_rounds"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True)
    round_number = Column(Integer)
    s3_key = Column(String, nullable=True)
    accuracy = Column(JSON, nullable=True)  # Store as float or null
    loss = Column(JSON, nullable=True)
    total_clients = Column(Integer, nullable=True)
    malicious_clients = Column(Integer, nullable=True)
    defense_success_rate = Column(JSON, nullable=True)
    round_data = Column(JSON)  # Full round JSON data
    timestamp = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
