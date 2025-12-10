"""
Test script for FL Session Watcher

This script simulates creating a new round file to test the real-time monitoring system.
"""

import json
import os
import time
from pathlib import Path
from datetime import datetime

def create_test_session():
    """Create a test session with sample round data"""
    
    # Create session directory
    session_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    session_path = Path("../sessions") / session_id
    rounds_path = session_path / "rounds"
    
    # Create directories
    rounds_path.mkdir(parents=True, exist_ok=True)
    (session_path / "cumulative").mkdir(exist_ok=True)
    
    print(f"✓ Created session directory: {session_path}")
    
    # Create sample round data
    for round_num in range(1, 4):
        round_data = {
            "metadata": {
                "round": round_num,
                "timestamp": datetime.now().isoformat() + "Z",
                "sessionId": session_id
            },
            "globalMetrics": {
                "accuracy": 0.95 + (round_num * 0.01),
                "loss": 0.15 - (round_num * 0.01),
                "currentRound": round_num,
                "totalClients": 10,
                "activeMaliciousClients": 2,
                "defenseSuccessRate": 80.0 + (round_num * 5),
                "isConnected": True,
                "timestamp": datetime.now().isoformat() + "Z"
            },
            "clients": [
                {
                    "id": f"client_{i}",
                    "type": "Malicious" if i < 2 else "Benign",
                    "accuracy": 0.94 + (i * 0.01),
                    "loss": 0.14 - (i * 0.005),
                    "divergence": None,
                    "learningRate": 0.01,
                    "epochs": 5,
                    "status": "Active" if i < 7 else "Inactive",
                    "trustScore": None,
                    "attackType": "Model Poisoning" if i < 2 else None,
                    "dataPoints": None,
                    "lastSeen": datetime.now().isoformat() + "Z"
                }
                for i in range(10)
            ],
            "roundSummary": {
                "round": round_num,
                "accuracy": 0.95 + (round_num * 0.01),
                "loss": 0.15 - (round_num * 0.01),
                "defenseApplied": True,
                "maliciousClientsDetected": 2,
                "participatingClients": 7,
                "duration": 2.5,
                "timestamp": datetime.now().isoformat() + "Z"
            },
            "defenseMetrics": {
                "detectionRate": 100.0,
                "falsePositiveRate": 0.0,
                "precision": 1.0,
                "recall": 1.0,
                "f1Score": 1.0,
                "defenseOverhead": 2.5,
                "attackImpactReduction": 95.0
            },
            "confusionMatrix": {
                "truePositive": 2,
                "falsePositive": 0,
                "trueNegative": 8,
                "falseNegative": 0
            },
            "alerts": [
                {
                    "id": f"alert_r{round_num}_001",
                    "round": round_num,
                    "clientId": "client_0",
                    "type": "detection",
                    "severity": "high",
                    "message": f"Model Poisoning attack detected from client_0 in round {round_num}",
                    "timestamp": datetime.now().isoformat() + "Z",
                    "acknowledged": False
                }
            ] if round_num > 1 else [],
            "clientHistory": {}
        }
        
        # Write round file
        round_file = rounds_path / f"round_{round_num:03d}.json"
        with open(round_file, 'w') as f:
            json.dump(round_data, f, indent=2)
        
        print(f"✓ Created round {round_num}: {round_file}")
        
        # Wait before creating next round (simulate training)
        if round_num < 3:
            print(f"  Waiting 3 seconds before next round...")
            time.sleep(3)
    
    # Create summary
    summary_data = {
        "sessionId": session_id,
        "totalRounds": 3,
        "startTime": datetime.now().isoformat() + "Z",
        "endTime": datetime.now().isoformat() + "Z",
        "finalAccuracy": 0.98,
        "finalLoss": 0.12,
        "totalMaliciousDetected": 2,
        "defenseEffectiveness": 95.0
    }
    
    summary_file = session_path / "summary.json"
    with open(summary_file, 'w') as f:
        json.dump(summary_data, f, indent=2)
    
    print(f"✓ Created summary: {summary_file}")
    print(f"\n✅ Test session created successfully!")
    print(f"   Session ID: {session_id}")
    print(f"   Total rounds: 3")
    print(f"\nIf your backend is running, you should see real-time updates in your dashboard!")

if __name__ == "__main__":
    print("=" * 60)
    print("FL Session Watcher Test")
    print("=" * 60)
    print("\nThis will create a test FL session with 3 rounds")
    print("Each round will be created with a 3-second delay\n")
    
    input("Press Enter to start...")
    
    try:
        create_test_session()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
