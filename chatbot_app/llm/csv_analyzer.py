"""
CSV Data Analyzer - Simple row selection and natural language conversion

Provides:
1. Dynamic row selection from CSV based on keywords
2. Convert rows to natural language descriptions (header: value format)
3. Distinguish general vs FL-specific questions
4. Always exclude true_label
"""

import logging
import pandas as pd
import numpy as np
import re
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class CSVAnalyzer:
    """
    Analyzes CSV data and provides natural language context for LLM Q&A.
    
    Key features:
    - Excludes true_label from all LLM context
    - Converts rows to natural language descriptions (not raw data)
    - Distinguishes general questions from FL-specific questions
    - Dynamic row selection based on keywords
    """
    
    def __init__(self, csv_path: str):
        """Initialize with CSV path"""
        self.csv_path = csv_path
        self.df: Optional[pd.DataFrame] = None
        self._load_csv()
    
    def _load_csv(self):
        """Load CSV into memory"""
        try:
            logger.info(f"Loading CSV from {self.csv_path}")
            
            if not Path(self.csv_path).exists():
                raise FileNotFoundError(f"CSV not found: {self.csv_path}")
            
            self.df = pd.read_csv(self.csv_path)
            
            # Remove true_label (ground truth, should not be in LLM context)
            if 'true_label' in self.df.columns:
                self.df = self.df.drop(columns=['true_label'])
            
            logger.info(f"✓ Loaded {len(self.df)} records, {len(self.df.columns)} columns")
            logger.info(f"✓ true_label excluded from all data")
            
        except Exception as e:
            logger.error(f"Error loading CSV: {e}")
            raise
    
    def _convert_row_to_natural_language(self, row: pd.Series) -> str:
        """
        Convert a single row into fluent natural-language text,
        only including stats/SHAP values that exist.
        """

        def fmt(val):
            if val is None or pd.isna(val):
                return None  # Return None instead of "N/A"
            if isinstance(val, (float, np.floating)):
                if abs(val) < 0.0001 or abs(val) > 100000:
                    return f"{val:.2e}"
                return f"{val:.4f}"
            return str(val)

        get = lambda col: row[col] if col in row.index else None

        client_id_val = get("client_id")
        round_num_val = get("round_num")

        client_id = str(int(client_id_val)) if client_id_val is not None and not pd.isna(client_id_val) else "N/A"
        round_num = str(int(round_num_val)) if round_num_val is not None and not pd.isna(round_num_val) else "N/A"

        raw_label = get("predicted_label")
        # predicted_prob = fmt(get("predicted_prob"))

        # Label mapping
        if raw_label in [1, 1.0, "1", "1.0"]:
            label_text = "malicious"
        elif raw_label in [0, 0.0, "0", "0.0"]:
            label_text = "benign"
        else:
            label_text = "unknown"

        parts = [f"Client {client_id} participated in round {round_num}.",
                f"The client was classified as {label_text}."]

        # if predicted_prob is not None:
        #     parts[-1] += f" with confidence {predicted_prob}."

        # Core statistics
        stats_items = []
        if fmt(get("param_mean")): stats_items.append(f"mean value of {fmt(get('param_mean'))}")
        if fmt(get("param_std")): stats_items.append(f"standard deviation of {fmt(get('param_std'))}")
        if fmt(get("param_min")): stats_items.append(f"minimum of {fmt(get('param_min'))}")
        if fmt(get("param_max")): stats_items.append(f"maximum of {fmt(get('param_max'))}")
        if fmt(get("param_median")): stats_items.append(f"median of {fmt(get('param_median'))}")
        if fmt(get("param_range")): stats_items.append(f"value range of {fmt(get('param_range'))}")
        if fmt(get("param_abs_mean")): stats_items.append(f"absolute mean of {fmt(get('param_abs_mean'))}")
        if fmt(get("param_skew")): stats_items.append(f"skewness {fmt(get('param_skew'))}")
        if fmt(get("param_kurtosis")): stats_items.append(f"kurtosis {fmt(get('param_kurtosis'))}")
        if fmt(get("param_neg_ratio")): stats_items.append(f"proportion of negative values {fmt(get('param_neg_ratio'))}")
        if fmt(get("param_zero_ratio")): stats_items.append(f"proportion of zeros {fmt(get('param_zero_ratio'))}")

        if stats_items:
            parts.append("The model update statistics show " + ", ".join(stats_items) + ".")

        # Last layer stats
        last_layer_items = []
        if fmt(get("last_layer_mean")): last_layer_items.append(f"mean {fmt(get('last_layer_mean'))}")
        if fmt(get("last_layer_std")): last_layer_items.append(f"standard deviation {fmt(get('last_layer_std'))}")
        if fmt(get("last_layer_min")): last_layer_items.append(f"minimum {fmt(get('last_layer_min'))}")
        if fmt(get("last_layer_max")): last_layer_items.append(f"maximum {fmt(get('last_layer_max'))}")
        if fmt(get("last_layer_abs_mean")): last_layer_items.append(f"absolute mean {fmt(get('last_layer_abs_mean'))}")
        if fmt(get("last_layer_neg_ratio")): last_layer_items.append(f"negative ratio {fmt(get('last_layer_neg_ratio'))}")

        if last_layer_items:
            parts.append("For the last model layer, " + ", ".join(last_layer_items) + ".")

        # Distance metrics
        distance_items = []
        if fmt(get("avg_l1_distance")): distance_items.append(f"average L1 distance {fmt(get('avg_l1_distance'))}")
        if fmt(get("avg_l2_distance")): distance_items.append(f"average L2 distance {fmt(get('avg_l2_distance'))}")
        if fmt(get("cosine_similarity")): distance_items.append(f"cosine similarity {fmt(get('cosine_similarity'))}")

        if distance_items:
            parts.append("Distance metrics: " + ", ".join(distance_items) + ".")

        # SHAP values
        shap_items = []
        for col in row.index:
            if col.startswith("SHAP") and fmt(get(col)):
                shap_items.append(f"{col} contributed {fmt(get(col))}")
        if shap_items:
            parts.append("SHAP analysis: " + ", ".join(shap_items) + ".")

        return " ".join(parts)
    
    def _is_fl_system_question(self, question: str) -> bool:
        """Detect if question is about FL system or general knowledge"""
        fl_keywords = [
            'client', 'malicious', 'benign', 'detection', 'round', 'confidence',
            'prediction', 'poisoned', 'attack', 'csv', 'data', 'statistics', 
            'federated', 'learning', 'parameter', 'model', 'update', 'suspicious',
            'accuracy', 'performance', 'anomal', 'detection rate'
        ]
        
        question_lower = question.lower()
        
        # If question contains FL keywords, it's FL-specific
        for keyword in fl_keywords:
            if keyword in question_lower:
                return True
        
        return False
    
    def _extract_client_id(self, question: str) -> Optional[int]:
        """Extract client_id from question"""
        # Pattern: "client 5", "client_id 5", "client#5"
        match = re.search(r'client[\s_#]*(\d+)', question, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None
    
    def _select_relevant_rows(self, question: str) -> pd.DataFrame:
        """Select up to 3 most relevant rows safely"""

        if self.df is None or len(self.df) == 0:
            return pd.DataFrame()
        
        question_lower = question.lower()
        selected = self.df.copy()
        
        # Strategy 1: Filter by client_id if mentioned
        client_id = self._extract_client_id(question)
        if client_id is not None and 'client_id' in self.df.columns:
            filtered = selected[selected['client_id'] == client_id]
            if not filtered.empty:
                logger.info(f"Selected rows for client {client_id}")
                return filtered.head(3)
        
        # Strategy 2: Filter by malicious
        if ("malicious" in question_lower or "poisoned" in question_lower) and \
        "predicted_label" in selected.columns:
            
            filtered = selected[selected["predicted_label"] == 1]
            if not filtered.empty:
                logger.info("Selected malicious rows")
                cols = [c for c in ["client_id", "round_num", "predicted_label"]
                        if c in filtered.columns]
                return filtered[cols]
        
        # Strategy 2b: Filter by benign
        if ("benign" in question_lower or "normal" in question_lower) and \
        "predicted_label" in selected.columns:
            
            filtered = selected[selected["predicted_label"] == 0]
            if not filtered.empty:
                logger.info("Selected benign rows")
                cols = [c for c in ["client_id", "round_num", "predicted_label"]
                        if c in filtered.columns]
                return filtered[cols]
        
        # Strategy 3: No match → return EMPTY DataFrame
        logger.info("No relevant rows found, returning empty DataFrame")
        return pd.DataFrame()
    
    def get_context_for_question(self, question: str) -> Tuple[str, bool]:
        """
        Get context for the question.
        Returns: (context_text, is_fl_question)
        
        Context text is natural language descriptions of relevant rows if FL question,
        empty string if general question.
        """
        is_fl_question = self._is_fl_system_question(question)
        
        if not is_fl_question:
            # General question - LLM answers from its own knowledge
            logger.info("General knowledge question - no CSV context needed")
            return "", False
        
        # FL-specific question - get relevant rows
        relevant_rows = self._select_relevant_rows(question)
        
        if relevant_rows.empty:
            logger.info("No relevant rows found for this question")
            return "No relevant data found in the dataset.", True
        
        # Convert rows to natural language
        descriptions = []
        for idx, row in relevant_rows.iterrows():
            description = self._convert_row_to_natural_language(row)
            descriptions.append(description)
        
        # Combine descriptions into context text
        context = "\n\n".join(descriptions)
        
        logger.info(f"Context length: {len(context)} chars")
        return context, True

# Global instance
_analyzer: Optional[CSVAnalyzer] = None


def get_csv_analyzer() -> CSVAnalyzer:
    """Get or initialize the CSV analyzer"""
    global _analyzer
    if _analyzer is None:
        from chatbot_app.config import FL_DATA_CSV_PATH
        _analyzer = CSVAnalyzer(FL_DATA_CSV_PATH)
    return _analyzer
