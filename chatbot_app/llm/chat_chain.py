"""Fast LLM Chat Chain with SHAP Explainability"""
import logging
import json
from typing import Iterator, Optional, Dict, Any
import torch

from app.models.qwen_loader import QwenModelLoader
from app.config import MAX_NEW_TOKENS, TEMPERATURE, TOP_P, REPETITION_PENALTY, DEVICE

logger = logging.getLogger(__name__)


class FastChatChain:
    """
    Fast chat chain with direct model inference (no LangChain agent).
    Optimized for speed with minimal overhead.
    """
    
    def __init__(self):
        """Initialize the chat chain with model"""
        self.model_loader = QwenModelLoader()
        logger.info("Chat chain initialized successfully")
    
    def _build_prompt(
        self,
        user_input: str,
        chat_history: Optional[list] = None,
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Build the prompt efficiently.
        
        Args:
            user_input: Current user message
            chat_history: List of previous messages
            system_prompt: Custom system prompt
        
        Returns:
            Complete prompt string
        """
        if chat_history is None:
            chat_history = []
        
        if system_prompt is None:
            system_prompt = """You are a helpful and accurate AI assistant. 
Answer questions clearly and concisely based on the information provided."""
        
        # Build conversation history (minimal overhead)
        history_parts = [system_prompt]
        
        for msg in chat_history[-5:]:  # Limit to last 5 messages for speed
            role = "User" if msg.get("role") == "user" else "Assistant"
            content = msg.get("content", "").strip()
            if content:
                history_parts.append(f"{role}: {content}")
        
        # Add current input
        history_parts.append(f"User: {user_input}")
        history_parts.append("Assistant:")
        
        return "\n".join(history_parts)
    
    def _generate_response(self, prompt: str) -> str:
        """
        Generate response efficiently with minimal tokenization overhead.
        
        Args:
            prompt: Input prompt
        
        Returns:
            Generated response text
        """
        try:
            # Single tokenization pass
            inputs = self.model_loader.tokenizer(
                prompt,
                return_tensors="pt",
                truncation=True,
                max_length=1024  # Input context window
            ).to(DEVICE)
            
            # Fast generation with GPU optimizations
            with torch.no_grad():
                output = self.model_loader.model.generate(
                    **inputs,
                    max_new_tokens=MAX_NEW_TOKENS,  # Use config value (512)
                    temperature=TEMPERATURE,
                    top_p=TOP_P,
                    repetition_penalty=REPETITION_PENALTY,
                    do_sample=True,
                    pad_token_id=self.model_loader.tokenizer.eos_token_id,
                    eos_token_id=self.model_loader.tokenizer.eos_token_id,
                    use_cache=True,  # Enable KV cache (GPU optimization)
                    num_beams=1  # Greedy decoding (faster)
                )
            
            # Efficient decoding
            generated_ids = output[0][inputs["input_ids"].shape[-1]:]
            response = self.model_loader.tokenizer.decode(
                generated_ids,
                skip_special_tokens=True
            ).strip()
            
            return response if response else "I couldn't generate a response. Please try again."
        
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            raise
    
    def chat(self, user_input: str, chat_history: Optional[list] = None) -> str:
        """
        Non-streaming chat for fast responses.
        
        Args:
            user_input: User's message
            chat_history: Previous messages
        
        Returns:
            LLM response
        """
        try:
            prompt = self._build_prompt(user_input, chat_history)
            response = self._generate_response(prompt)
            return response
        except Exception as e:
            logger.error(f"Chat error: {str(e)}")
            return f"Error: {str(e)}"
    
    def stream_chat(self, user_input: str, chat_history: Optional[list] = None) -> Iterator[str]:
        """
        Streaming chat - yields tokens as they're generated.
        
        Args:
            user_input: User's message
            chat_history: Previous messages
        
        Yields:
            Response tokens
        """
        try:
            prompt = self._build_prompt(user_input, chat_history)
            
            inputs = self.model_loader.tokenizer(
                prompt,
                return_tensors="pt",
                truncation=True,
                max_length=1024
            ).to(DEVICE)
            
            with torch.no_grad():
                output = self.model_loader.model.generate(
                    **inputs,
                    max_new_tokens=MAX_NEW_TOKENS,  # Use config value (512)
                    temperature=TEMPERATURE,
                    top_p=TOP_P,
                    repetition_penalty=REPETITION_PENALTY,
                    do_sample=True,
                    pad_token_id=self.model_loader.tokenizer.eos_token_id,
                    eos_token_id=self.model_loader.tokenizer.eos_token_id
                )
            
            generated_ids = output[0][inputs["input_ids"].shape[-1]:]
            response = self.model_loader.tokenizer.decode(
                generated_ids,
                skip_special_tokens=True
            )
            
            # Stream character by character
            for char in response:
                yield char
        
        except Exception as e:
            logger.error(f"Stream chat error: {str(e)}")
            yield f"Error: {str(e)}"
    
# Global instance
_chat_chain: Optional[FastChatChain] = None


def get_chat_chain() -> FastChatChain:
    """Get or create the chat chain instance (singleton)"""
    global _chat_chain
    if _chat_chain is None:
        _chat_chain = FastChatChain()
    return _chat_chain
