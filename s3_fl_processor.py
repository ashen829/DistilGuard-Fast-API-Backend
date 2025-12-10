"""
S3 FL Session File Processor
Monitors S3 bucket for FL session files, downloads them, stores in SQLite, and broadcasts to dashboard
"""

import json
import os
import gzip
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import asyncio
from sqlalchemy.orm import Session

from aws_client import s3_client
from database import S3Event, FileContent, FLSession, FLRound, SessionLocal
from websocket_manager import ConnectionManager


class S3FLFileProcessor:
    """Processes FL session files from S3"""
    
    def __init__(self, websocket_manager: ConnectionManager, local_sessions_path: str = "../sessions"):
        self.manager = websocket_manager
        self.local_sessions_path = Path(local_sessions_path)
        self.local_sessions_path.mkdir(parents=True, exist_ok=True)
    
    async def process_s3_event(self, event_data: Dict[str, Any], db: Session):
        """
        Process S3 event: download file, store in DB, save locally, and broadcast
        """
        try:
            bucket = event_data.get('bucket')
            key = event_data.get('key')
            event_id = event_data.get('event_id')
            
            print(f"📥 Processing S3 file: s3://{bucket}/{key}")
            
            # Check if this is an FL session file
            if not self._is_fl_session_file(key):
                print(f"⏭️  Skipping non-FL file: {key}")
                return
            
            # Download file from S3
            file_content = await self._download_from_s3(bucket, key)
            if not file_content:
                print(f"❌ Failed to download: {key}")
                return
            
            # Parse JSON content
            try:
                json_data = json.loads(file_content)
            except json.JSONDecodeError as e:
                print(f"❌ Invalid JSON in {key}: {e}")
                return
            
            # Store in database
            await self._store_in_database(event_id, key, file_content, json_data, db)
            
            # Save to local file system
            local_path = await self._save_locally(key, json_data)
            
            # Determine file type and broadcast appropriately
            if 'round_' in key:
                await self._broadcast_round_update(json_data, key)
            elif 'summary.json' in key:
                await self._broadcast_session_summary(json_data)
            
            # Mark as processed
            event = db.query(S3Event).filter(S3Event.event_id == event_id).first()
            if event:
                event.processed = 1
                db.commit()
            
            print(f"✅ Successfully processed: {key}")
            print(f"   Stored in DB and saved to: {local_path}")
            
        except Exception as e:
            print(f"❌ Error processing S3 event: {e}")
            import traceback
            traceback.print_exc()
    
    def _is_fl_session_file(self, key: str) -> bool:
        """Check if S3 key is an FL session file"""
        # Match patterns like: sessions/2025-12-09_16-43-37/rounds/round_001.json
        return (
            'session' in key.lower() and 
            key.endswith('.json') and 
            ('round_' in key or 'summary' in key)
        )
    
    async def _download_from_s3(self, bucket: str, key: str) -> Optional[str]:
        """Download file content from S3 (handles gzip compression)"""
        try:
            response = s3_client.s3_client.get_object(Bucket=bucket, Key=key)
            content_bytes = response['Body'].read()
            
            # Check if content is gzip-compressed (starts with 0x1f8b)
            if content_bytes[:2] == b'\x1f\x8b':
                print(f"🗜️  Decompressing gzip file: {key}")
                content = gzip.decompress(content_bytes).decode('utf-8')
            else:
                content = content_bytes.decode('utf-8')
            
            return content
        except Exception as e:
            print(f"Error downloading from S3: {e}")
            return None
    
    async def _store_in_database(self, event_id: str, s3_key: str, content: str, json_data: Dict[str, Any], db: Session):
        """Store file content in SQLite database"""
        try:
            # Calculate content hash
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            
            # Store raw file content
            existing = db.query(FileContent).filter(
                FileContent.event_id == event_id
            ).first()
            
            if existing:
                print(f"📝 Updating existing DB record for: {s3_key}")
                existing.content = content
                existing.content_hash = content_hash
                existing.stored_at = datetime.utcnow()
            else:
                print(f"📝 Creating new DB record for: {s3_key}")
                file_record = FileContent(
                    event_id=event_id,
                    s3_key=s3_key,
                    content=content,
                    content_hash=content_hash,
                    stored_at=datetime.utcnow()
                )
                db.add(file_record)
            
            # Store FL-specific data
            metadata = json_data.get('metadata', {})
            session_id = metadata.get('sessionId')
            
            if session_id:
                # Store/update FL session
                session = db.query(FLSession).filter(
                    FLSession.session_id == session_id
                ).first()
                
                if not session:
                    session = FLSession(
                        session_id=session_id,
                        s3_bucket=s3_key.split('/')[0] if '/' in s3_key else None,
                        s3_prefix='/'.join(s3_key.split('/')[:-1]) if '/' in s3_key else None,
                        status="active",
                        created_at=datetime.utcnow()
                    )
                    db.add(session)
                    print(f"📊 Created FL session: {session_id}")
                
                session.updated_at = datetime.utcnow()
                
                # If it's a round file, store round data
                if 'round_' in s3_key:
                    round_num = metadata.get('round')
                    if round_num:
                        existing_round = db.query(FLRound).filter(
                            FLRound.session_id == session_id,
                            FLRound.round_number == round_num
                        ).first()
                        
                        global_metrics = json_data.get('globalMetrics', {})
                        
                        if existing_round:
                            print(f"📝 Updating round {round_num} for session {session_id}")
                            existing_round.round_data = json_data
                            existing_round.accuracy = global_metrics.get('accuracy')
                            existing_round.loss = global_metrics.get('loss')
                            existing_round.total_clients = global_metrics.get('totalClients')
                            existing_round.malicious_clients = global_metrics.get('activeMaliciousClients')
                            existing_round.defense_success_rate = global_metrics.get('defenseSuccessRate')
                        else:
                            print(f"📊 Creating round {round_num} for session {session_id}")
                            fl_round = FLRound(
                                session_id=session_id,
                                round_number=round_num,
                                s3_key=s3_key,
                                accuracy=global_metrics.get('accuracy'),
                                loss=global_metrics.get('loss'),
                                total_clients=global_metrics.get('totalClients'),
                                malicious_clients=global_metrics.get('activeMaliciousClients'),
                                defense_success_rate=global_metrics.get('defenseSuccessRate'),
                                round_data=json_data,
                                timestamp=datetime.fromisoformat(metadata.get('timestamp', '').replace('Z', '+00:00')) if metadata.get('timestamp') else datetime.utcnow()
                            )
                            db.add(fl_round)
                        
                        # Update session total rounds
                        if round_num > (session.total_rounds or 0):
                            session.total_rounds = round_num
                
                # If it's a summary file, update session
                elif 'summary' in s3_key:
                    session.summary = json_data
                    session.status = "completed"
                    session.total_rounds = json_data.get('totalRounds', session.total_rounds)
                    if json_data.get('endTime'):
                        session.end_time = datetime.fromisoformat(json_data['endTime'].replace('Z', '+00:00'))
            
            db.commit()
            print(f"✅ Stored in database: {s3_key} (hash: {content_hash[:12]}...)")
            
        except Exception as e:
            print(f"Error storing in database: {e}")
            import traceback
            traceback.print_exc()
            db.rollback()
    
    async def _save_locally(self, s3_key: str, json_data: Dict[str, Any]) -> Path:
        """Save file to local sessions directory"""
        try:
            # Extract session ID from metadata or key
            session_id = json_data.get('metadata', {}).get('sessionId')
            if not session_id:
                # Try to extract from S3 key path
                parts = s3_key.split('/')
                for part in parts:
                    if '_' in part and '-' in part:  # Looks like session ID
                        session_id = part
                        break
            
            if not session_id:
                session_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            
            # Determine if it's a round file or summary
            if 'round_' in s3_key:
                # Extract round number
                round_num = json_data.get('metadata', {}).get('round', 1)
                filename = f"round_{round_num:03d}.json"
                local_path = self.local_sessions_path / session_id / "rounds" / filename
            elif 'summary' in s3_key:
                filename = "summary.json"
                local_path = self.local_sessions_path / session_id / filename
            else:
                filename = os.path.basename(s3_key)
                local_path = self.local_sessions_path / session_id / filename
            
            # Create directory structure
            local_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write file
            with open(local_path, 'w') as f:
                json.dump(json_data, f, indent=2)
            
            print(f"💾 Saved locally: {local_path}")
            return local_path
            
        except Exception as e:
            print(f"Error saving locally: {e}")
            raise
    
    async def _broadcast_round_update(self, round_data: Dict[str, Any], s3_key: str):
        """Broadcast round update via WebSocket"""
        try:
            message = {
                "type": "round_update",
                "source": "s3",
                "event": "s3_download",
                "sessionId": round_data.get('metadata', {}).get('sessionId'),
                "round": round_data.get('metadata', {}).get('round'),
                "timestamp": datetime.now().isoformat(),
                "s3_key": s3_key,
                "data": round_data
            }
            
            await self.manager.broadcast(message)
            print(f"📡 Broadcasted round update from S3: Round {message['round']}")
            
        except Exception as e:
            print(f"Error broadcasting round update: {e}")
    
    async def _broadcast_session_summary(self, summary_data: Dict[str, Any]):
        """Broadcast session summary via WebSocket"""
        try:
            message = {
                "type": "session_summary",
                "source": "s3",
                "timestamp": datetime.now().isoformat(),
                "data": summary_data
            }
            
            await self.manager.broadcast(message)
            print(f"📡 Broadcasted session summary from S3")
            
        except Exception as e:
            print(f"Error broadcasting session summary: {e}")
    
    def get_stored_sessions(self, db: Session) -> list:
        """Get all sessions stored in database"""
        try:
            files = db.query(FileContent).order_by(FileContent.stored_at.desc()).all()
            
            sessions = {}
            for file in files:
                # Extract session ID from s3_key
                parts = file.s3_key.split('/')
                for part in parts:
                    if '_' in part and '-' in part:
                        session_id = part
                        if session_id not in sessions:
                            sessions[session_id] = {
                                'sessionId': session_id,
                                'rounds': [],
                                'lastUpdate': file.stored_at
                            }
                        if 'round_' in file.s3_key:
                            sessions[session_id]['rounds'].append(file.s3_key)
            
            return list(sessions.values())
            
        except Exception as e:
            print(f"Error getting stored sessions: {e}")
            return []
    
    def get_round_from_db(self, event_id: str, db: Session) -> Optional[Dict[str, Any]]:
        """Retrieve round data from database"""
        try:
            file_record = db.query(FileContent).filter(
                FileContent.event_id == event_id
            ).first()
            
            if file_record and file_record.content:
                return json.loads(file_record.content)
            return None
            
        except Exception as e:
            print(f"Error retrieving from database: {e}")
            return None
