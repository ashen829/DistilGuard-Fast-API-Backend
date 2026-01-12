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
from report_generator import get_report_generator


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
            
            # Parse content based on file type
            if key.endswith('.csv'):
                # CSV file - store as-is, no JSON parsing
                json_data = None
            else:
                # JSON file
                try:
                    json_data = json.loads(file_content)
                except json.JSONDecodeError as e:
                    print(f"❌ Invalid JSON in {key}: {e}")
                    return
            
            # Store in database
            await self._store_in_database(event_id, key, file_content, json_data, db)
            
            # Save to local file system
            local_path = await self._save_locally(key, file_content, json_data)
            
            # Determine file type and broadcast appropriately
            if 'shap_analysis.csv' in key:
                # SHAP CSV file - generate reports for all rounds
                print(f"✅ Successfully processed SHAP CSV: {key}")
                await self._generate_reports_from_shap_csv(key, file_content, db)
            elif key.endswith('.csv'):
                # Other CSV files - no broadcast needed, just log
                print(f"✅ Successfully processed CSV: {key}")
            elif 'shap_analysis' in key:
                await self._broadcast_shap_analysis(json_data, key)
            elif 'round_' in key:
                await self._broadcast_round_update(json_data, key)
                # Generate reports for malicious clients in this round
                await self._generate_round_reports(json_data, key, db)
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
        # Match patterns like:
        # - sessions/2025-12-09_16-43-37/rounds/round_001.json
        # - sessions/2025-12-09_16-43-37/shap_analysis.csv
        return (
            'session' in key.lower() and 
            ('round_' in key or 'summary' in key or 'shap_analysis.csv' in key)
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
    
    async def _save_locally(self, s3_key: str, content: str, json_data: Optional[Dict[str, Any]]) -> Path:
        """Save file to local sessions directory"""
        try:
            # Extract session ID from S3 key path
            # Key format: sessions/2025-12-09_16-43-37/shap_analysis.csv
            parts = s3_key.split('/')
            session_id = parts[1] if len(parts) > 1 else datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            
            # Save based on file type
            if s3_key.endswith('shap_analysis.csv'):
                # ✅ Save the CSV content as-is
                filename = os.path.basename(s3_key)
                local_path = self.local_sessions_path / session_id / filename
                local_path.parent.mkdir(parents=True, exist_ok=True)
                with open(local_path, 'w', encoding='utf-8') as f:
                    f.write(content)  # write raw CSV content

            elif 'round_' in s3_key:
                # Extract round number
                round_num = json_data.get('metadata', {}).get('round', 1) if json_data else 1
                filename = f"round_{round_num:03d}.json"
                local_path = self.local_sessions_path / session_id / "rounds" / filename
                local_path.parent.mkdir(parents=True, exist_ok=True)
                with open(local_path, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, indent=2)

            elif 'summary' in s3_key:
                filename = "summary.json"
                local_path = self.local_sessions_path / session_id / filename
                local_path.parent.mkdir(parents=True, exist_ok=True)
                with open(local_path, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, indent=2)

            else:
                # Other CSV or files
                filename = os.path.basename(s3_key)
                local_path = self.local_sessions_path / session_id / filename
                local_path.parent.mkdir(parents=True, exist_ok=True)
                with open(local_path, 'w', encoding='utf-8') as f:
                    f.write(content)  # write raw content
                                    
            print(f"💾 Saved locally: {local_path}")
            return local_path
            
        except Exception as e:
            print(f"Error saving locally: {e}")
            raise
    
    async def _broadcast_round_update(self, round_data: Dict[str, Any], s3_key: str):
        """Broadcast round update via WebSocket"""
        try:
            message = {
                "type": "ROUND_COMPLETE",
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
    
    async def _broadcast_shap_analysis(self, shap_data: Dict[str, Any], s3_key: str):
        """Broadcast SHAP analysis update via WebSocket"""
        try:
            message = {
                "type": "shap_analysis_update",
                "source": "s3",
                "timestamp": datetime.now().isoformat(),
                "s3_key": s3_key,
                "data": shap_data
            }
            
            await self.manager.broadcast(message)
            print(f"📡 Broadcasted SHAP analysis update from S3: {os.path.basename(s3_key)}")
            
        except Exception as e:
            print(f"Error broadcasting SHAP analysis: {e}")
    
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
    
    async def download_session_shap_analysis(
        self,
        session_id: str,
        s3_bucket: str = "distil-guard-datalake",
        s3_region: str = "ap-south-1"
    ) -> Optional[Dict[str, Any]]:
        """
        Download SHAP analysis CSV file for a session from S3
        
        Args:
            session_id: Session ID (format: 2025-12-11_09-29-47)
            s3_bucket: S3 bucket name
            s3_region: S3 region
        
        Returns:
            Dictionary with path to downloaded CSV file, or None if failed
        """
        try:
            import aioboto3
            
            print(f"📥 Starting SHAP analysis CSV download for session: {session_id}")
            
            session_dir = self.local_sessions_path / session_id
            session_dir.mkdir(parents=True, exist_ok=True)
            
            session = aioboto3.Session()
            async with session.client('s3', region_name=s3_region) as s3:
                # Download shap_analysis.csv from session folder
                s3_key = f"sessions/{session_id}/shap_analysis.csv"
                
                print(f"📥 Downloading SHAP analysis CSV: {s3_key}")
                
                try:
                    local_file_path = session_dir / "shap_analysis.csv"
                    
                    await s3.download_file(
                        s3_bucket,
                        s3_key,
                        str(local_file_path)
                    )
                    
                    print(f"✅ Downloaded SHAP analysis CSV to: {local_file_path}")
                    
                    return {
                        "session_id": session_id,
                        "csv_path": str(local_file_path),
                        "file": "shap_analysis.csv"
                    }
                    
                except Exception as e:
                    print(f"⚠️  SHAP analysis CSV not found for session: {session_id}")
                    print(f"   Tried S3 path: {s3_key}")
                    return None
                    
        except Exception as e:
            print(f"❌ Error downloading SHAP analysis: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_shap_data_for_client(
        self,
        session_id: str,
        client_id: int,
        top_n: int = 5
    ) -> Optional[Dict[str, Any]]:
        """
        Get top N SHAP features for a specific client from local CSV file
        
        Args:
            session_id: Session ID
            client_id: Client ID
            top_n: Number of top features to return
        
        Returns:
            Dictionary with client's top SHAP features and metrics
        """
        try:
            import pandas as pd
            
            csv_path = self.local_sessions_path / session_id / "shap_analysis.csv"
            
            if not csv_path.exists():
                print(f"⚠️  SHAP CSV not found: {csv_path}")
                return None
            
            # Load CSV
            df = pd.read_csv(csv_path)
            
            # Filter for this client
            client_data = df[df['client_id'] == client_id]
            
            if client_data.empty:
                print(f"⚠️  Client {client_id} not found in SHAP data")
                return None
            
            # Get the most recent round for this client
            latest_row = client_data.iloc[-1]
            
            # SHAP feature columns (all columns starting with 'SHAP_')
            shap_columns = [col for col in df.columns if col.startswith('SHAP_')]
            
            # Extract SHAP values for this client and get top N by absolute value
            shap_values = {}
            for col in shap_columns:
                val = latest_row[col]
                if pd.notna(val):
                    # Remove 'SHAP_' prefix for cleaner feature names
                    feature_name = col.replace('SHAP_', '')
                    shap_values[feature_name] = float(val)
            
            # Sort by absolute value and get top N
            sorted_features = sorted(
                shap_values.items(),
                key=lambda x: abs(x[1]),
                reverse=True
            )[:top_n]
            
            # Get corresponding feature values (non-SHAP columns)
            feature_values = {}
            for col in df.columns:
                if not col.startswith('SHAP_') and col not in ['client_id', 'round_num', 'main_task_accuracy', 'main_task_loss']:
                    val = latest_row[col]
                    if pd.notna(val):
                        feature_values[col] = float(val)
            
            # Build result
            result = {
                "client_id": int(client_id),
                "session_id": session_id,
                "round": int(latest_row['round_num']),
                "main_task_accuracy": float(latest_row['main_task_accuracy']) if pd.notna(latest_row['main_task_accuracy']) else None,
                "main_task_loss": float(latest_row['main_task_loss']) if pd.notna(latest_row['main_task_loss']) else None,
                "top_shap_features": [
                    {
                        "feature_name": feat_name,
                        "feature_value": feature_values.get(feat_name),
                        "shap_value": shap_val
                    }
                    for feat_name, shap_val in sorted_features
                ]
            }
            
            print(f"✅ Got SHAP features for client {client_id}: {len(sorted_features)} top features")
            return result
            
        except Exception as e:
            print(f"❌ Error getting client SHAP features: {e}")
            import traceback
            traceback.print_exc()
            return None    
    async def _generate_round_reports(self, round_data: Dict[str, Any], s3_key: str, db: Session):
        """
        Generate explanation reports for malicious clients in a round.
        
        Args:
            round_data: Round JSON data
            s3_key: S3 key path
            db: Database session
        """
        try:
            # Extract session ID and round number from S3 key
            # Format: sessions/2025-12-09_16-43-37/rounds/round_001.json
            parts = s3_key.split('/')
            if len(parts) < 2:
                print(f"⚠️  Could not extract session ID from: {s3_key}")
                return
            
            session_id = parts[1]
            metadata = round_data.get('metadata', {})
            round_number = metadata.get('round', 0)
            
            print(f"🔍 Generating reports for session {session_id}, round {round_number}")
            
            # Get report generator
            generator = get_report_generator()
            
            # Generate reports for malicious clients
            reports = await generator.generate_round_reports(
                session_id=session_id,
                round_number=round_number,
                round_data=round_data,
                db=db
            )
            
            if reports:
                print(f"✅ Generated {len(reports)} reports for round {round_number}")
                
                # Broadcast reports via WebSocket
                await self._broadcast_reports_generated(session_id, round_number, reports)
            else:
                print(f"ℹ️  No reports generated for round {round_number}")
            
        except Exception as e:
            print(f"❌ Error generating round reports: {e}")
            import traceback
            traceback.print_exc()
    
    async def _broadcast_reports_generated(self, session_id: str, round_number: int, reports: list):
        """
        Broadcast report generation event via WebSocket.
        
        Args:
            session_id: Session ID
            round_number: Round number
            reports: List of generated reports
        """
        try:
            message = {
                "type": "REPORTS_GENERATED",
                "source": "report_generator",
                "timestamp": datetime.now().isoformat(),
                "sessionId": session_id,
                "round": round_number,
                "reportCount": len(reports),
                "reports": reports
            }
            
            await self.manager.broadcast(message)
            print(f"📡 Broadcasted {len(reports)} reports for round {round_number}")
            
        except Exception as e:
            print(f"Error broadcasting reports: {e}")
    
    async def _generate_reports_from_shap_csv(
        self,
        s3_key: str,
        csv_content: str,
        db: Session
    ):
        """
        Generate explanation reports for all malicious clients from SHAP CSV analysis.
        
        This is called when shap_analysis.csv is received. The CSV contains all client
        data for all rounds. We parse it, group by round, and generate reports for
        malicious clients (predicted_label == 'malicious').
        
        DEDUPLICATION: Avoids generating duplicate reports for the same client in the same round.
        Uses unique key: (session_id, round_number, client_id)
        
        Args:
            s3_key: S3 key path (e.g., sessions/2025-01-12_00-07-59/shap_analysis.csv)
            csv_content: CSV file content as string
            db: Database session
        """
        try:
            import pandas as pd
            from io import StringIO
            
            # Extract session ID from S3 key
            parts = s3_key.split('/')
            if len(parts) < 2:
                print(f"⚠️  Could not extract session ID from: {s3_key}")
                return
            
            session_id = parts[1]
            
            print(f"🔍 Parsing SHAP CSV for session: {session_id}")
            
            # Parse CSV content
            df = pd.read_csv(StringIO(csv_content))
            
            print(f"📊 Loaded {len(df)} records from SHAP CSV")
            print(f"📊 Columns available: {list(df.columns)[:5]}... (showing first 5)")
            
            # Get report generator
            generator = get_report_generator()
            
            # DEDUPLICATION: Track processed (session_id, round_num, client_id) combinations
            processed_clients = set()
            
            # Group by round and process each round
            all_reports = []
            rounds_processed = set()
            duplicates_skipped = 0
            
            for _, row in df.iterrows():
                try:
                    round_num = int(row.get('round_num', 0))
                    client_id = int(row.get('client_id', -1))
                    predicted_label = row.get('predicted_label', 'benign')
                    ground_truth = row.get('ground_truth_label', 'benign')
                    
                    # Normalize predicted label: handle both numeric (0/1) and string ('benign'/'malicious')
                    is_malicious = False
                    if isinstance(predicted_label, (int, float)):
                        # Numeric labels: 1 = malicious, 0 = benign
                        is_malicious = predicted_label == 1
                    else:
                        # String labels: 'malicious' or 'benign'
                        is_malicious = str(predicted_label).lower() == 'malicious'
                    
                    # Normalize ground truth similarly
                    ground_truth_str = str(ground_truth).lower() if isinstance(ground_truth, str) else ('malicious' if ground_truth == 1 else 'benign')
                    
                    # DEDUPLICATION CHECK: Skip if we've already processed this client in this round
                    client_key = (session_id, round_num, client_id)
                    if client_key in processed_clients:
                        duplicates_skipped += 1
                        print(f"⏭️  Skipping duplicate: Client {client_id} in Round {round_num}")
                        continue
                    
                    # Generate report for malicious predictions
                    if is_malicious:
                        print(f"🎯 Found malicious client {client_id} in round {round_num}")
                        
                        # Create a minimal round_data structure from CSV row
                        # The report generator will use SHAP analyzer if available
                        round_data = {
                            'metadata': {'round': round_num},
                            'clients': [
                                {
                                    'client_id': client_id,
                                    'clientId': client_id,
                                    'isMalicious': is_malicious,
                                    'is_malicious': is_malicious,
                                    'predicted_label': 'malicious' if is_malicious else 'benign',
                                    'ground_truth_label': ground_truth_str,
                                    'main_task_accuracy': float(row.get('main_task_accuracy', 0)) if pd.notna(row.get('main_task_accuracy')) else 0,
                                    'main_task_loss': float(row.get('main_task_loss', 0)) if pd.notna(row.get('main_task_loss')) else 0,
                                }
                            ],
                            'globalMetrics': {
                                'detectedClients': [{'clientId': client_id, 'score': 0.95}]
                            }
                        }
                        
                        # Generate report for this client
                        reports = await generator.generate_round_reports(
                            session_id=session_id,
                            round_number=round_num,
                            round_data=round_data,
                            db=db
                        )
                        
                        if reports:
                            all_reports.extend(reports)
                            rounds_processed.add(round_num)
                            # Mark this client as processed in this round
                            processed_clients.add(client_key)
                            print(f"✅ Generated report for client {client_id} in round {round_num}")
                        
                except Exception as e:
                    print(f"⚠️  Error processing row: {e}")
                    continue
            
            # Summary
            print(f"\n✅ SHAP CSV Processing Complete")
            print(f"   - Rounds processed: {len(rounds_processed)} ({sorted(rounds_processed)})")
            print(f"   - Total reports generated: {len(all_reports)}")
            print(f"   - Duplicate clients skipped: {duplicates_skipped}")
            
            if all_reports:
                # Group reports by round for broadcasting
                reports_by_round = {}
                for report in all_reports:
                    # These reports are already stored in DB by generator
                    pass
                
                # Broadcast summary of what was generated
                message = {
                    "type": "SHAP_REPORTS_GENERATED",
                    "source": "shap_csv_processor",
                    "timestamp": datetime.now().isoformat(),
                    "sessionId": session_id,
                    "roundsProcessed": sorted(rounds_processed),
                    "totalReports": len(all_reports),
                    "duplicatesSkipped": duplicates_skipped,
                    "status": "complete"
                }
                await self.manager.broadcast(message)
                print(f"📡 Broadcasted SHAP processing completion to clients")
            else:
                print(f"ℹ️  No malicious clients found in SHAP CSV")
            
        except Exception as e:
            print(f"❌ Error processing SHAP CSV: {e}")
            import traceback
            traceback.print_exc()

