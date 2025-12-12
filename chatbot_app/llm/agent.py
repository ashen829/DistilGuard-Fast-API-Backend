"""
SHAP Q&A Agent - Answers questions about FL system using SHAP CSV data

Architecture:
1. User asks a question about a client
2. Agent extracts client ID from question
3. Gets top 5 SHAP contributing features for that client from CSV
4. Sends features + metrics as natural language context to LLM
5. LLM generates human-readable answer

Features:
- Reads shap_analysis.csv from latest session
- Extracts top 5 features by SHAP value
- Includes feature values, SHAP contributions, accuracy, and loss
- Converts to natural language for LLM context
"""

import logging
import re
from pathlib import Path
from typing import List, Dict, Optional
from chatbot_app.llm.chat_chain import FastChatChain, get_chat_chain
from chatbot_app.llm.shap_csv_analyzer import get_shap_csv_analyzer

logger = logging.getLogger(__name__)


class SHAPQAAgent:
    """
    Agent that answers questions about FL detection using SHAP CSV data.
    
    Enhanced features:
    - Reads shap_analysis.csv from latest session in sessions/ folder
    - Extracts top 5 SHAP features for mentioned clients
    - Provides natural language context to LLM
    """
    
    def __init__(self):
        """Initialize with chat chain and SHAP analyzer"""
        self.chat_chain = get_chat_chain()
        self.analyzer = None
        
        # Try to load SHAP CSV analyzer
        try:
            self.analyzer = get_shap_csv_analyzer()
            logger.info("✓ SHAP CSV analyzer initialized")
        except Exception as e:
            logger.error(f"Failed to initialize SHAP analyzer: {e}")
            logger.warning("Agent will not provide SHAP context without CSV data")
        
        logger.info("✓ SHAP Q&A Agent initialized")
    
    def _extract_client_ids(self, question: str) -> List[int]:
        """
        Extract client IDs from question.
        
        Matches patterns like:
        - "client 0", "client_0", "client0"
        - "client 1", "client_1", "client1"
        
        Args:
            question: User's question
        
        Returns:
            List of client IDs, or empty list
        """
        pattern = r'client\s*[_\s]?(\d+)'
        matches = re.findall(pattern, question, re.IGNORECASE)
        
        client_ids = [int(m) for m in matches]
        if client_ids:
            logger.info(f"Extracted client IDs from question: {client_ids}")
        return client_ids
    
    def _get_shap_context_for_clients(self, client_ids: List[int]) -> Optional[str]:
        """
        Get SHAP feature context for mentioned clients.
        
        Args:
            client_ids: List of client IDs
        
        Returns:
            Natural language context with top 5 SHAP features
        """
        if not client_ids or not self.analyzer:
            return None
        
        try:
            contexts = []
            
            for client_id in client_ids:
                # Get top 5 SHAP features for this client from CSV
                shap_context = self.analyzer.get_top_shap_features_for_client(
                    client_id=client_id,
                    top_n=5
                )
                
                if shap_context:
                    contexts.append(shap_context)
                    logger.info(f"✓ Got SHAP context for client {client_id}")
                else:
                    logger.warning(f"⚠️  Could not get SHAP context for client {client_id}")
            
            if contexts:
                return "\n\n".join(contexts)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting SHAP context: {e}", exc_info=True)
            return None
    
    def process(self, user_input: str, chat_history: List[Dict[str, str]]) -> str:
        """
        Process user question and return answer based on SHAP CSV data or general knowledge.
        
        Args:
            user_input: User's question
            chat_history: List of previous messages
        
        Returns:
            Natural language answer
        """
        logger.info(f"Processing: {user_input}")
        
        try:
            # Check if question mentions specific clients
            client_ids = self._extract_client_ids(user_input)
            shap_context = None
            
            if client_ids and self.analyzer:
                logger.info(f"Client IDs detected: {client_ids}, fetching SHAP context...")
                shap_context = self._get_shap_context_for_clients(client_ids)
            
            # Determine if this is FL-specific question
            is_fl_question = self.analyzer and self.analyzer._is_fl_system_question(user_input)
            
            if is_fl_question and self.analyzer:
                logger.info(f"FL-specific question detected")
                
                # System prompt for FL-specific questions
                system_prompt = """You are a helpful assistant answering questions about a federated learning poisoning detection system.
You have access to client model update statistics and SHAP feature analysis showing which features are most important for detecting client behavior.

When discussing SHAP features:
- Explain what each top feature represents and why it's important for detection
- Use simple terms that non-technical people can understand
- Describe what the feature values mean (high/low, positive/negative, etc.)
- Explain how each feature contributes to the detection decision
- Compare clients when asked about multiple ones

Be clear, accurate, and help users understand client behavior through the provided SHAP analysis."""
                
                # Use SHAP context if available, otherwise general context
                if shap_context:
                    user_content = f"""SHAP Feature Analysis:
{shap_context}

Question: {user_input}

Based on the SHAP analysis above, explain the client's behavior and what the top features reveal about them."""
                else:
                    user_content = user_input
            else:
                logger.info(f"General knowledge question or no analyzer")
                
                # System prompt for general questions
                system_prompt = """You are a helpful, friendly assistant.
Answer questions accurately and honestly.
Be clear and concise."""
                
                user_content = user_input
            
            messages = [
                {"role": "system", "content": system_prompt},
                *chat_history,
                {"role": "user", "content": user_content}
            ]
            
            logger.info("====== LLM INPUT START ======")
            logger.info(f"System: {system_prompt[:100]}...")
            if shap_context:
                logger.info(f"SHAP Context length: {len(shap_context)} chars")
            logger.info(f"User: {user_input}")
            logger.info("====== LLM INPUT END ======")
            
            # Generate response
            response = self.chat_chain.chat(user_input, messages)
            
            logger.info(f"Response generated: {len(response)} chars")
            return response
            
        except Exception as e:
            logger.error(f"Error in process: {e}", exc_info=True)
            return f"I encountered an error: {str(e)}"
    
    def stream_process(self, user_input: str, chat_history: List[Dict[str, str]]):
        """
        Stream version of process - yields tokens as they're generated.
        
        Args:
            user_input: User's question
            chat_history: List of previous messages
        
        Yields:
            Response tokens
        """
        logger.info(f"Stream processing: {user_input}")
        
        try:
            # Check if question mentions specific clients
            client_ids = self._extract_client_ids(user_input)
            shap_context = None
            
            if client_ids and self.analyzer:
                logger.info(f"Client IDs detected: {client_ids}, fetching SHAP context...")
                shap_context = self._get_shap_context_for_clients(client_ids)
            
            # Determine if this is FL-specific question
            is_fl_question = self.analyzer and self.analyzer._is_fl_system_question(user_input)
            
            if is_fl_question and self.analyzer:
                logger.info(f"FL-specific question detected")
                
                system_prompt = """You are a helpful assistant for a federated learning poisoning detection system.
                You have access to client model update statistics and feature contribution data.
                Use the data to answer questions about client behavior.
                Do not invent new questions. Be honest if you don't know something."""
                
                if shap_context:
                    user_content = f"""SHAP Feature Analysis:
{shap_context}

Question: {user_input}

                - If the question asks why a client is malicious or benign, 
                    - Write a short, simple explanation for someone without technical or machine learning experience.
                    - Use SHAP values to find most important features, But do not mention SHAP directly.
                    - Only mention the most important features with the raw values.
                    - Focus on what makes this class different and what would help someone spot it.
                - Otherwise, answer directly from the dataset without adding unnecessary explanations.
                """

            else:
                logger.info(f"General knowledge question or no analyzer")
                
                system_prompt = """You are a helpful, friendly assistant.
                Only answer questions related to the federated learning poisoning detection system.
                Do not answer questions outside this domain. If a question is outside this domain, respond with a polite pre-set message such as: 
                "I'm sorry, I can only answer questions about the federated learning poisoning detection system." 
                Be honest if you don't know something."""

                user_content = user_input
            
            messages = [
                {"role": "system", "content": system_prompt},
                *chat_history,
                {"role": "user", "content": user_content}
            ]
            
            logger.info("====== LLM STREAM INPUT START ======")
            logger.info(f"System: {system_prompt[:100]}...")
            if shap_context:
                logger.info(f"SHAP Context length: {len(shap_context)} chars")
            logger.info(f"User: {user_input}")
            logger.info("====== LLM STREAM INPUT END ======")
            
            # Stream response
            for token in self.chat_chain.stream_chat(user_input, messages):
                yield token
                
        except Exception as e:
            logger.error(f"Error in stream_process: {e}", exc_info=True)
            yield f"Error: {str(e)}"


# Global instance
_agent: Optional[SHAPQAAgent] = None


def get_agent() -> SHAPQAAgent:
    """Get or initialize the SHAP Q&A agent"""
    global _agent
    if _agent is None:
        _agent = SHAPQAAgent()
    return _agent
