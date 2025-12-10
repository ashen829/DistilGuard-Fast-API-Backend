"""Qwen Model Loader"""
import logging
from typing import Optional
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from app.config import MODEL_NAME, MODEL_DIR, DEVICE

logger = logging.getLogger(__name__)


class QwenModelLoader:
    """Singleton loader for Qwen model and tokenizer"""
    
    _instance: Optional["QwenModelLoader"] = None
    _model = None
    _tokenizer = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._model is None:
            self._load_model()
    
    def _load_model(self):
        """Load model and tokenizer from HuggingFace Hub"""
        try:
            logger.info(f"Loading tokenizer from {MODEL_NAME}...")
            self._tokenizer = AutoTokenizer.from_pretrained(
                MODEL_NAME,
                cache_dir=str(MODEL_DIR),
                trust_remote_code=True
            )
            
            logger.info(f"Loading model from {MODEL_NAME} on {DEVICE}...")
            
            # Optimize for GPU if available
            if DEVICE == "cuda":
                dtype = torch.float16  # Faster on GPU
                device_map = "auto" if torch.cuda.device_count() > 1 else "cuda:0"
            else:
                dtype = torch.float32
                device_map = "cpu"
            
            self._model = AutoModelForCausalLM.from_pretrained(
                MODEL_NAME,
                cache_dir=str(MODEL_DIR),
                trust_remote_code=True,
                torch_dtype=dtype,
                device_map=device_map,
                low_cpu_mem_usage=True
            )
            
            # Log setup details
            gpu_count = torch.cuda.device_count() if DEVICE == "cuda" else 0
            logger.info(f"✓ Model loaded on {DEVICE}")
            if gpu_count > 0:
                logger.info(f"  GPUs available: {gpu_count}")
                for i in range(gpu_count):
                    logger.info(f"    GPU {i}: {torch.cuda.get_device_name(i)}")
        except Exception as e:
            logger.error(f"Failed to load model: {str(e)}")
            raise
    
    @property
    def model(self):
        """Get the loaded model"""
        return self._model
    
    @property
    def tokenizer(self):
        """Get the loaded tokenizer"""
        return self._tokenizer
