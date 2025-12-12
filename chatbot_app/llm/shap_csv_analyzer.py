"""
SHAP CSV Analyzer - Reads shap_analysis.csv from latest session

Provides:
1. Load SHAP analysis CSV with client features and SHAP values
2. Extract top 5 contributing features for a client using SHAP values
3. Convert to natural language descriptions
4. Query by client ID and round
"""

import logging
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class SHAPCSVAnalyzer:
    """
    Analyzes SHAP CSV data for FL client detection.
    
    CSV Format:
    - client_id: ID of the client
    - round_num: Training round number
    - main_task_accuracy: Model accuracy in this round
    - main_task_loss: Model loss in this round
    - param_*: Parameter statistics columns
    - SHAP_param_*: SHAP values for parameter statistics
    - SHAP_last_layer_*: SHAP values for last layer statistics
    - SHAP_*: All SHAP contribution values
    """
    
    def __init__(self, csv_path: str):
        """Initialize with CSV path"""
        self.csv_path = csv_path
        self.df: Optional[pd.DataFrame] = None
        self._load_csv()
    
    def _load_csv(self):
        """Load CSV into memory"""
        try:
            logger.info(f"Loading SHAP CSV from {self.csv_path}")
            
            if not Path(self.csv_path).exists():
                raise FileNotFoundError(f"CSV not found: {self.csv_path}")
            
            self.df = pd.read_csv(self.csv_path)
            
            logger.info(f"✓ Loaded {len(self.df)} records, {len(self.df.columns)} columns")
            logger.info(f"✓ Available columns: {list(self.df.columns)[:10]}...")
            
        except Exception as e:
            logger.error(f"Error loading CSV: {e}")
            raise
    
    def get_top_shap_features_for_client(
        self,
        client_id: int,
        top_n: int = 5
    ) -> Optional[str]:
        """
        Get top N SHAP features for a specific client.
        
        Returns natural language description with:
        - Client ID and Round
        - Main task accuracy and loss
        - Top 5 contributing features with their values and SHAP contributions
        
        Args:
            client_id: Client ID to query
            top_n: Number of top features to return (default 5)
        
        Returns:
            Natural language description or None if client not found
        """
        try:
            if self.df is None or len(self.df) == 0:
                logger.warning("No data loaded")
                return None
            
            # Filter for this client
            client_data = self.df[self.df['client_id'] == client_id]
            
            if client_data.empty:
                logger.warning(f"Client {client_id} not found in data")
                return None
            
            # Get the latest round for this client
            latest_row = client_data.iloc[-1]
            
            # Extract key metrics
            round_num = int(latest_row['round_num'])
            accuracy = latest_row.get('main_task_accuracy')
            loss = latest_row.get('main_task_loss')
            
            # Find all SHAP columns
            shap_columns = [col for col in self.df.columns if col.startswith('SHAP_')]
            
            if not shap_columns:
                logger.warning(f"No SHAP columns found in CSV")
                return None
            
            # Extract SHAP values for this row
            shap_values = {}
            for shap_col in shap_columns:
                val = latest_row[shap_col]
                if pd.notna(val):
                    # Get the corresponding feature column (without SHAP_ prefix)
                    feature_col = shap_col.replace('SHAP_', '')
                    shap_values[feature_col] = float(val)
            
            if not shap_values:
                logger.warning(f"No SHAP values found for client {client_id}")
                return None
            
            # Sort by absolute value and get top N
            sorted_features = sorted(
                shap_values.items(),
                key=lambda x: abs(x[1]),
                reverse=True
            )[:top_n]
            
            # Build natural language description
            desc = f"**Client {client_id} - Round {round_num} Analysis**\n\n"
            
            # Add metrics
            if pd.notna(accuracy):
                desc += f"Main task accuracy: {float(accuracy):.4f}\n"
            if pd.notna(loss):
                desc += f"Main task loss: {float(loss):.4f}\n"
                
            if "predicted_label" in self.df.columns:
                desc += f"Predicted label: {latest_row['predicted_label']}\n"

            desc += "\n**Top {n} Contributing Features (by SHAP value):**\n\n".format(n=min(top_n, len(sorted_features)))
            
            # Add top features
            for idx, (feature_name, shap_val) in enumerate(sorted_features, 1):
                # Get the actual feature value from the row
                feature_value = latest_row.get(feature_name)
                
                # Format values
                if pd.notna(feature_value):
                    feat_val_str = self._format_value(feature_value)
                else:
                    feat_val_str = "N/A"
                
                shap_val_str = self._format_value(shap_val)
                
                desc += f"{idx}. **{feature_name}**\n"
                desc += f"   - Feature value: {feat_val_str}\n"
                desc += f"   - SHAP contribution: {shap_val_str}\n"
            
            logger.info(f"✓ Generated SHAP analysis for client {client_id}")
            return desc
            
        except Exception as e:
            logger.error(f"Error getting SHAP features for client: {e}", exc_info=True)
            return None
    
    def _format_value(self, val: Any) -> str:
        """Format a numeric value for display"""
        if val is None or pd.isna(val):
            return "N/A"
        
        if isinstance(val, (int, np.integer)):
            return str(int(val))
        
        if isinstance(val, (float, np.floating)):
            # Use scientific notation for very small or large values
            if abs(val) < 0.0001 or abs(val) > 100000:
                return f"{val:.2e}"
            return f"{val:.6f}"
        
        return str(val)
    
    def get_context_for_question(self, question: str) -> tuple[str, bool]:
        """
        Get context for a question about FL detection.
        
        Returns: (context_text, is_fl_question)
        
        Args:
            question: User's question
        
        Returns:
            Tuple of (context_text, is_fl_question)
        """
        is_fl_question = self._is_fl_system_question(question)
        
        if not is_fl_question:
            return "", False
        
        # Try to extract client ID from question
        client_id = self._extract_client_id(question)
        
        if client_id is not None:
            context = self.get_top_shap_features_for_client(client_id, top_n=5)
            if context:
                logger.info(f"Got SHAP context for client {client_id}")
                return context, True
            else:
                return "Client data not found in SHAP analysis.", True
        
        # General FL question without specific client
        return self._get_general_fl_context(), True
    
    def _is_fl_system_question(self, question: str) -> bool:
        """Detect if question is about FL system"""
        fl_keywords = [
            'client', 'malicious', 'benign', 'detection', 'round', 'accuracy',
            'loss', 'federated', 'learning', 'parameter', 'model', 'attack',
            'poison', 'feature', 'shap', 'analysis', 'update', 'suspicious'
        ]
        
        question_lower = question.lower()
        for keyword in fl_keywords:
            if keyword in question_lower:
                return True
        
        return False
    
    def _extract_client_id(self, question: str) -> Optional[int]:
        """Extract client_id from question"""
        import re
        # Pattern: "client 5", "client_id 5", "client#5"
        match = re.search(r'client[\s_#]*(\d+)', question, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None
    
    def _get_general_fl_context(self) -> str:
        """Get general context about the FL system"""
        if self.df is None or len(self.df) == 0:
            return ""
        
        # Get basic statistics
        num_clients = self.df['client_id'].nunique()
        num_rounds = self.df['round_num'].max()
        
        context = f"**Federated Learning System Overview:**\n\n"
        context += f"- Number of clients: {num_clients}\n"
        context += f"- Number of rounds: {num_rounds}\n"
        context += f"- Total records: {len(self.df)}\n\n"
        
        # Get average metrics
        avg_accuracy = self.df['main_task_accuracy'].mean()
        avg_loss = self.df['main_task_loss'].mean()
        
        if pd.notna(avg_accuracy):
            context += f"- Average accuracy: {avg_accuracy:.4f}\n"
        if pd.notna(avg_loss):
            context += f"- Average loss: {avg_loss:.4f}\n"
        
        return context


# Global instance
_analyzer: Optional[SHAPCSVAnalyzer] = None


def get_shap_csv_analyzer(csv_path: Optional[str] = None) -> SHAPCSVAnalyzer:
    """Get or initialize the SHAP CSV analyzer"""
    global _analyzer
    
    if _analyzer is None:
        if csv_path is None:
            # Try to find latest session's shap_analysis.csv
            sessions_path = Path("../sessions")
            if not sessions_path.exists():
                sessions_path = Path("./sessions")
            
            if sessions_path.exists():
                # Find most recent session
                session_dirs = sorted(
                    [d for d in sessions_path.iterdir() if d.is_dir()],
                    reverse=True
                )
                
                if session_dirs:
                    csv_path = session_dirs[0] / "shap_analysis.csv"
                    if not csv_path.exists():
                        raise FileNotFoundError(f"No shap_analysis.csv found in {session_dirs[0]}")
                else:
                    raise FileNotFoundError("No session directories found")
            else:
                raise FileNotFoundError("No sessions directory found")
        
        _analyzer = SHAPCSVAnalyzer(str(csv_path))
    
    return _analyzer


def reset_analyzer():
    """Reset the global analyzer instance"""
    global _analyzer
    _analyzer = None
