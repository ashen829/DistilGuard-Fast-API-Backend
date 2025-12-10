"""Application Configuration"""
import os
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
MODEL_DIR = PROJECT_ROOT / "models_cache"
MODEL_NAME = "Qwen/Qwen2-7B-Instruct"  # or use 2B variant: "Qwen/Qwen2-1.5B-Instruct"

# Auto-detect GPU, prefer CUDA if available (FIX for slowness)
import torch
if os.environ.get("DEVICE") == "cpu":
    DEVICE = "cpu"
elif torch.cuda.is_available():
    DEVICE = "cuda"
else:
    DEVICE = "cpu"

# Model Config - optimized for detailed responses without clipping
MAX_NEW_TOKENS = 512  # Increased to prevent response clipping
TEMPERATURE = 0.7
TOP_P = 0.9
REPETITION_PENALTY = 1.05

# Server Config
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", 8000))
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

# Data Sources - JSON (primary) and CSV (fallback)
# Set FL_DATA_S3_PATH to download from S3: "s3://bucket-name/path/to/file.json"
# Set FL_DATA_LOCAL_PATH for local JSON file (default: /home/fyp-llm-25/fyp-llm-25/Reasoning/fl_data.json)
FL_DATA_S3_PATH = os.environ.get("FL_DATA_S3_PATH")
FL_DATA_LOCAL_PATH = os.environ.get("FL_DATA_LOCAL_PATH", "/home/fyp-llm-25/fyp-llm-25/chatbot_project/app/data/round_002_shap(5).json")
FL_DATA_CSV_PATH = os.environ.get("FL_DATA_CSV_PATH", "/home/fyp-llm-25/fyp-llm-25/Reasoning/5gnidd_10_clietns_test_constant_noise_with_predictions_and_shap.csv")

# S3 Configuration (optional)
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Ensure model cache directory exists
MODEL_DIR.mkdir(parents=True, exist_ok=True)
