import os
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent


class SessionFileHandler(FileSystemEventHandler):
    """Handles file system events for FL session files"""
    
    def __init__(self, websocket_manager, callback=None):
        self.manager = websocket_manager
        self.callback = callback
        self.processed_files = set()
        self.current_session = None
    
    def on_created(self, event):
        if event.is_directory:
            return
        
        if self._is_round_file(event.src_path):
            asyncio.create_task(self._process_file(event.src_path, 'created'))
        elif event.src_path.endswith('summary.json'):
            asyncio.create_task(self._process_summary(event.src_path))
    
    def on_modified(self, event):
        if event.is_directory:
            return
        
        if self._is_round_file(event.src_path):
            asyncio.create_task(self._process_file(event.src_path, 'modified'))
    
    def _is_round_file(self, file_path: str) -> bool:
        """Check if file is a round JSON file"""
        return file_path.endswith('.json') and 'round_' in os.path.basename(file_path)
    
    async def _process_file(self, file_path: str, event_type: str):
        """Process round file and broadcast data"""
        try:
            # Wait for file to be fully written
            await asyncio.sleep(0.5)
            
            with open(file_path, 'r') as f:
                round_data = json.load(f)
            
            # Extract session info
            session_id = round_data.get('metadata', {}).get('sessionId')
            round_num = round_data.get('metadata', {}).get('round')
            
            # Prepare broadcast message
            message = {
                "type": "ROUND_COMPLETE",
                "event": event_type,
                "sessionId": session_id,
                "round": round_num,
                "timestamp": datetime.now().isoformat(),
                "data": round_data
            }
            
            # Broadcast to all connected WebSocket clients
            await self.manager.broadcast(message)
            
            print(f"✓ Broadcasted Round {round_num} from session {session_id}")
            
            # Execute callback if provided
            if self.callback:
                await self.callback(round_data)
                
        except json.JSONDecodeError as e:
            print(f"✗ JSON decode error in {file_path}: {e}")
        except Exception as e:
            print(f"✗ Error processing {file_path}: {e}")
    
    async def _process_summary(self, file_path: str):
        """Process summary.json file"""
        try:
            await asyncio.sleep(0.5)
            
            with open(file_path, 'r') as f:
                summary_data = json.load(f)
            
            message = {
                "type": "TRAINING_COMPLETE",
                "timestamp": datetime.now().isoformat(),
                "data": summary_data
            }
            
            await self.manager.broadcast(message)
            print(f"✓ Broadcasted session summary")
            
        except Exception as e:
            print(f"✗ Error processing summary {file_path}: {e}")


class FLSessionWatcher:
    """Watches FL session directories for real-time updates"""
    
    def __init__(self, websocket_manager, sessions_path: str = "../sessions"):
        self.manager = websocket_manager
        self.sessions_path = Path(sessions_path)
        self.observer = None
        self.handler = None
        self.active = False
    
    async def start(self):
        """Start watching the sessions directory"""
        if self.active:
            print("Session watcher already running")
            return
        
        # Ensure sessions directory exists
        self.sessions_path.mkdir(parents=True, exist_ok=True)
        
        # Create handler and observer
        self.handler = SessionFileHandler(self.manager)
        self.observer = Observer()
        self.observer.schedule(self.handler, str(self.sessions_path), recursive=True)
        
        # Start observer in a separate thread
        self.observer.start()
        self.active = True
        
        print(f"✓ FL Session Watcher started - Monitoring: {self.sessions_path}")
        print(f"  Watching for round files: round_*.json")
        print(f"  Watching for summary files: summary.json")
    
    def stop(self):
        """Stop the file watcher"""
        if self.observer and self.active:
            self.observer.stop()
            self.observer.join()
            self.active = False
            print("✓ FL Session Watcher stopped")
    
    def get_latest_session(self) -> Optional[str]:
        """Get the most recent session directory"""
        try:
            sessions = [d for d in self.sessions_path.iterdir() if d.is_dir()]
            if not sessions:
                return None
            return str(max(sessions, key=lambda x: x.stat().st_mtime))
        except Exception as e:
            print(f"Error getting latest session: {e}")
            return None
    
    def get_all_sessions(self) -> list:
        """Get all session directories"""
        try:
            sessions = [d.name for d in self.sessions_path.iterdir() if d.is_dir()]
            return sorted(sessions, reverse=True)
        except Exception as e:
            print(f"Error getting sessions: {e}")
            return []
    
    def get_session_rounds(self, session_id: str) -> list:
        """Get all round files for a specific session"""
        try:
            session_path = self.sessions_path / session_id / "rounds"
            if not session_path.exists():
                return []
            
            rounds = sorted([f.name for f in session_path.glob("round_*.json")])
            return rounds
        except Exception as e:
            print(f"Error getting rounds for session {session_id}: {e}")
            return []
    
    def load_round_data(self, session_id: str, round_file: str) -> Optional[Dict[str, Any]]:
        """Load data from a specific round file"""
        try:
            file_path = self.sessions_path / session_id / "rounds" / round_file
            with open(file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading round data: {e}")
            return None
    
    def load_session_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load session summary"""
        try:
            file_path = self.sessions_path / session_id / "summary.json"
            if not file_path.exists():
                return None
            with open(file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading session summary: {e}")
            return None
