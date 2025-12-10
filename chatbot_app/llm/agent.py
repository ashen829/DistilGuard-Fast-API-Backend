"""
CSV/JSON Q&A Agent - Answers questions about FL system data using LLM

Architecture:
1. User asks a question
2. Agent tries JSON data first (if available), falls back to CSV
3. Relevant data is fed to LLM as natural language context
4. LLM generates human-readable answer

No technical jargon - just natural Q&A about the detection system.
"""

import logging
from typing import List, Dict
from app.llm.chat_chain import FastChatChain, get_chat_chain
from app.llm.json_analyzer import get_json_analyzer
from app.llm.csv_analyzer import get_csv_analyzer

logger = logging.getLogger(__name__)


class CSVQAAgent:
    """
    Agent that answers questions about FL detection data.
    
    Supports both:
    1. JSON data (from S3 or local file) - primary source
    2. CSV data - fallback source
    
    Works by:
    1. User asks a question
    2. Try JSON analyzer first, fall back to CSV
    3. Extract relevant information as natural language
    4. Pass to LLM for response
    """
    
    def __init__(self):
        """Initialize with JSON and CSV analyzers"""
        self.chat_chain = get_chat_chain()
        self.json_analyzer = None
        self.csv_analyzer = None
        
        # Try to load JSON analyzer
        try:
            self.json_analyzer = get_json_analyzer()
            logger.info("✓ JSON analyzer initialized")
        except Exception as e:
            logger.warning(f"JSON analyzer failed: {e}, will use CSV fallback")
        
        # Always load CSV analyzer as fallback
        try:
            self.csv_analyzer = get_csv_analyzer()
            logger.info("✓ CSV analyzer initialized as fallback")
        except Exception as e:
            logger.error(f"CSV analyzer also failed: {e}")
        
        # Use JSON if available, otherwise CSV
        self.analyzer = self.json_analyzer if self.json_analyzer else self.csv_analyzer
        
        logger.info("✓ CSV/JSON Q&A Agent initialized")
    
    def process(self, user_input: str, chat_history: List[Dict[str, str]]) -> str:
        """
        Process user question and return answer based on CSV data or general knowledge.
        
        Args:
            user_input: User's question
            chat_history: List of previous messages
        
        Returns:
            Natural language answer
        """
        logger.info(f"Processing: {user_input}")
        
        try:
            # Determine if question is about FL system or general knowledge
            csv_context, is_fl_question = self.analyzer.get_context_for_question(user_input)
            
            if is_fl_question:
                logger.info(f"FL-specific question - CSV context length: {len(csv_context)} chars")
                # System prompt for FL-specific questions
                system_prompt = """You are a helpful assistant answering questions about a federated learning client detection system.
You have access to data about client detection results.
Explain in simple, non-technical language that a non-expert can understand.
Use the provided data to answer accurately. Do not make up information.
Focus on what the data shows, not technical details."""
                
                # Include CSV context
                user_content = f"Relevant Data:\n{csv_context}\n\nQuestion: {user_input}\n\nProvide a clear, simple answer."
            else:
                logger.info(f"General knowledge question - no CSV context needed")
                # System prompt for general questions
                system_prompt = """You are a helpful, friendly assistant.
Answer questions in simple, clear language.
Be honest if you don't know something."""
                
                # No CSV context for general questions
                user_content = user_input
            
            messages = [
                {"role": "system", "content": system_prompt},
                *chat_history,
                {"role": "user", "content": user_content}
            ]
                        
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
            # Determine if question is about FL system or general knowledge
            csv_context, is_fl_question = self.analyzer.get_context_for_question(user_input)
            
            if is_fl_question:
                logger.info(f"FL-specific question - CSV context length: {len(csv_context)} chars")
                system_prompt = """You are a helpful assistant for a federated learning poisoning detection system.
                You have access to client model update statistics and feature contribution data.
                Use the data to answer questions about client behavior.
                Do not invent new questions. Be honest if you don't know something."""

                user_content = f"""Relevant Data:
                {csv_context}

                Question: {user_input}

                - If the question asks why a client is malicious or benign, 
                    - Write a short, simple explanation for someone without technical or machine learning experience.
                    - Use SHAP values to find most important features, But do not mention SHAP directly.
                    - Only mention the most important features with the raw values.
                    - Focus on what makes this class different and what would help someone spot it.
                - Otherwise, answer directly from the dataset without adding unnecessary explanations.
                """

            else:
                logger.info(f"General knowledge question - no CSV context needed")
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
                        
            logger.info("====== LLM INPUT PROMPT START ======")
            logger.info(messages)
            logger.info("====== LLM INPUT PROMPT END ======")
            
            # Stream response
            for token in self.chat_chain.stream_chat(user_input, messages):
                yield token
                
        except Exception as e:
            logger.error(f"Error in stream_process: {e}", exc_info=True)
            yield f"Error: {str(e)}"


# Global instance
_agent: CSVQAAgent = None


def get_agent() -> CSVQAAgent:
    """Get or initialize the agent"""
    global _agent
    if _agent is None:
        _agent = CSVQAAgent()
    return _agent
