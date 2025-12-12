"""
JSON Data Analyzer - Loads FL system detection data from JSON (S3 or local)

Features:
1. Download JSON from S3 bucket (optional, requires boto3)
2. Parse hierarchical client detection data
3. Convert to natural language descriptions
4. Distinguish general vs FL-specific questions
"""

import logging
import json
import os
from pathlib import Path
from typing import Optional, Tuple, List
import re

try:
    import boto3
    from botocore.exceptions import ClientError
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False
    logger = logging.getLogger(__name__)
    logger.warning("boto3 not installed - S3 functionality disabled. Install with: pip install boto3")

from chatbot_app.llm.models import RoundData, ClientRecord, Features

logger = logging.getLogger(__name__)


class JSONAnalyzer:
    """
    Analyzer for FL system JSON detection data.
    
    Can load from:
    1. S3 bucket (downloaded to local cache)
    2. Local file path
    """
    
    def __init__(self, s3_path: Optional[str] = None, local_path: Optional[str] = None):
        """
        Initialize JSON analyzer.
        
        Args:
            s3_path: S3 path like "s3://bucket-name/path/to/file.json"
            local_path: Local file path as fallback
        """
        self.s3_path = s3_path
        self.local_path = local_path
        self.data: Optional[RoundData] = None
        self.cache_dir = Path("/tmp/fl_data_cache")
        self.cache_dir.mkdir(exist_ok=True)
        
        self._load_data()
    
    def _download_from_s3(self, s3_path: str) -> str:
        """
        Download JSON from S3 bucket.
        
        Args:
            s3_path: S3 path like "s3://bucket-name/path/to/file.json"
        
        Returns:
            Local file path
        """
        if not HAS_BOTO3:
            raise RuntimeError(
                "boto3 is not installed. Install with: pip install boto3\n"
                "Or provide a local file path instead of S3."
            )
        
        try:
            # Parse S3 path
            if not s3_path.startswith("s3://"):
                raise ValueError(f"Invalid S3 path: {s3_path}")
            
            path_parts = s3_path.replace("s3://", "").split("/", 1)
            bucket = path_parts[0]
            key = path_parts[1] if len(path_parts) > 1 else ""
            
            if not key:
                raise ValueError(f"No key in S3 path: {s3_path}")
            
            logger.info(f"Downloading from S3: s3://{bucket}/{key}")
            
            # Create local cache file
            cache_file = self.cache_dir / Path(key).name
            
            # Download from S3
            s3 = boto3.client('s3')
            s3.download_file(bucket, key, str(cache_file))
            
            logger.info(f"✓ Downloaded to {cache_file}")
            return str(cache_file)
            
        except Exception as e:
            logger.error(f"Error downloading from S3: {e}")
            raise
    
    def _load_data(self):
        """Load JSON data from S3 or local file"""
        try:
            file_path = None
            
            # Try S3 first if provided
            if self.s3_path:
                try:
                    file_path = self._download_from_s3(self.s3_path)
                except Exception as e:
                    logger.warning(f"S3 download failed: {e}, trying local path")
            
            # Fall back to local path
            if file_path is None and self.local_path:
                if not Path(self.local_path).exists():
                    raise FileNotFoundError(f"Local file not found: {self.local_path}")
                file_path = self.local_path
            
            if file_path is None:
                raise ValueError("No valid S3 or local path provided")
            
            # Load JSON
            logger.info(f"Loading JSON from {file_path}")
            with open(file_path, 'r') as f:
                json_data = json.load(f)
            
            # Parse into data model
            self.data = RoundData.from_dict(json_data)
            
            logger.info(f"✓ Loaded round {self.data.round_num}")
            logger.info(f"✓ {len(self.data.clients)} clients, {self.data.num_samples} samples")
            logger.info(f"✓ Timestamp: {self.data.timestamp}")
            
        except Exception as e:
            logger.error(f"Error loading JSON: {e}")
            raise
    
    def _convert_client_to_natural_language(self, client: ClientRecord) -> str:
        """
        Convert client record to comprehensive natural language description.
        
        Includes:
        - Classification with confidence
        - ALL feature values
        - ALL SHAP values for explainability
        
        Format: Natural language with feature explanations
        """
        # Classification with confidence
        classification = client.classification.capitalize()
        confidence_pct = client.malicious_probability * 100
        
        desc = f"Client {client.client_id}: {classification} ({confidence_pct:.1f}% confidence)"
        
        # Add all feature values
        features = client.features
        desc += "\n\nFeature Values:"
        
        feature_values = [
            ("Parameter Mean", features.param_mean),
            ("Parameter Std Dev", features.param_std),
            ("Parameter Min", features.param_min),
            ("Parameter Max", features.param_max),
            ("Parameter Median", features.param_median),
            ("Parameter Range", features.param_range),
            ("Parameter Abs Mean", features.param_abs_mean),
            ("Parameter Skewness", features.param_skew),
            ("Parameter Kurtosis", features.param_kurtosis),
            ("Parameter Neg Ratio", features.param_neg_ratio),
            ("Parameter Zero Ratio", features.param_zero_ratio),
            ("Last Layer Mean", features.last_layer_mean),
            ("Last Layer Std Dev", features.last_layer_std),
            ("Last Layer Min", features.last_layer_min),
            ("Last Layer Max", features.last_layer_max),
            ("Last Layer Abs Mean", features.last_layer_abs_mean),
            ("Last Layer Neg Ratio", features.last_layer_neg_ratio),
            ("First vs Last Mean Ratio", features.first_vs_last_mean_ratio),
            ("First vs Last Std Ratio", features.first_vs_last_std_ratio),
            ("Avg L1 Distance", features.avg_l1_distance),
            ("Avg L2 Distance", features.avg_l2_distance),
            ("Cosine Similarity", features.cosine_similarity),
        ]
        
        for fname, fvalue in feature_values:
            if isinstance(fvalue, float):
                if abs(fvalue) < 0.0001 or abs(fvalue) > 100000:
                    desc += f"\n  - {fname}: {fvalue:.2e}"
                else:
                    desc += f"\n  - {fname}: {fvalue:.6f}"
            else:
                desc += f"\n  - {fname}: {fvalue}"
        
        # Add SHAP values if available
        if client.shap_values and client.shap_values.feature_shap_values:
            desc += "\n\nFeature Importance (SHAP Values):"
            desc += f"\n  Base Value: {client.shap_values.base_value}"
            
            shap_dict = client.shap_values.feature_shap_values
            for feature_name, shap_value in sorted(shap_dict.items(), key=lambda x: abs(x[1]), reverse=True):
                if isinstance(shap_value, float):
                    if abs(shap_value) < 0.0001 or abs(shap_value) > 100000:
                        desc += f"\n  - {feature_name}: {shap_value:.2e} (contribution)"
                    else:
                        desc += f"\n  - {feature_name}: {shap_value:.6f} (contribution)"
                else:
                    desc += f"\n  - {feature_name}: {shap_value} (contribution)"
        
        return desc
    
    def _is_fl_system_question(self, question: str) -> bool:
        """Detect if question is about FL system or general knowledge"""
        fl_keywords = [
            'client', 'malicious', 'benign', 'detection', 'round', 'confidence',
            'classification', 'probability', 'suspicious', 'attack', 'anomal',
            'federated', 'learning', 'model', 'update', 'poisoned', 'feature',
            'parameter', 'csv', 'data', 'statistics', 'detection rate', 'accuracy'
        ]
        
        question_lower = question.lower()
        
        for keyword in fl_keywords:
            if keyword in question_lower:
                return True
        
        return False
    
    def _extract_client_id(self, question: str) -> Optional[int]:
        """Extract client_id from question"""
        match = re.search(r'client[\s_#]*(\d+)', question, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None
    
    def _extract_round_num(self, question: str) -> Optional[int]:
        """Extract round number from question"""
        match = re.search(r'round[\s_#]*(\d+)', question, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None
    
    def _select_relevant_clients(self, question: str) -> List[ClientRecord]:
        """Select up to 3 most relevant client records"""
        if self.data is None or len(self.data.clients) == 0:
            return []
        
        question_lower = question.lower()
        clients = self.data.clients
        
        # Strategy 1: Specific client ID
        client_id = self._extract_client_id(question)
        if client_id is not None:
            matching = [c for c in clients if c.client_id == client_id]
            if matching:
                logger.info(f"Selected client {client_id}")
                return matching[:3]
        
        # Strategy 2: Malicious clients
        if 'malicious' in question_lower or 'poisoned' in question_lower:
            malicious = [c for c in clients if c.classification == 'malicious']
            if malicious:
                logger.info(f"Selected {len(malicious)} malicious clients")
                return malicious[:3]
        
        # Strategy 3: Benign clients
        if 'benign' in question_lower or 'normal' in question_lower:
            benign = [c for c in clients if c.classification == 'benign']
            if benign:
                logger.info(f"Selected {len(benign)} benign clients")
                return benign[:3]
        
        # Strategy 4: High confidence
        if 'confidence' in question_lower or 'confident' in question_lower:
            if 'high' in question_lower or 'highest' in question_lower:
                sorted_clients = sorted(clients, key=lambda c: c.malicious_probability, reverse=True)
                logger.info(f"Selected top 3 high confidence clients")
                return sorted_clients[:3]
        
        # Strategy 5: Default - first 3 clients
        logger.info(f"Selected first 3 clients (default)")
        return clients[:3]
    
    def get_client_with_top_shap_features(self, client_id: int, top_n: int = 5) -> Optional[str]:
        """
        Get client information with top N SHAP features for LLM context.
        
        Args:
            client_id: Client ID to get info for
            top_n: Number of top SHAP features to return
        
        Returns:
            Natural language description with top SHAP features
        """
        if not self.data:
            return None
        
        try:
            # Find client in current round data
            matching_clients = [c for c in self.data.clients if c.client_id == client_id]
            
            if not matching_clients:
                logger.warning(f"Client {client_id} not found in round {self.data.round_num}")
                return None
            
            client = matching_clients[0]
            
            # Build description with top SHAP features
            classification = client.classification.capitalize()
            confidence_pct = client.malicious_probability * 100
            
            desc = f"**Client {client_id} Analysis**\n\n"
            desc += f"Classification: {classification} ({confidence_pct:.2f}% confidence)\n"
            desc += f"Round: {self.data.round_num}\n\n"
            
            # Get top N features by SHAP value
            if client.shap_values and client.shap_values.feature_shap_values:
                shap_dict = client.shap_values.feature_shap_values
                features_dict = {
                    k: v for k, v in vars(client.features).items() 
                    if not k.startswith('_')
                }
                
                # Sort by absolute SHAP value
                sorted_features = sorted(
                    shap_dict.items(),
                    key=lambda x: abs(float(x[1])) if x[1] is not None else 0,
                    reverse=True
                )[:top_n]
                
                desc += "**Top Contributing Features (SHAP):**\n\n"
                
                for idx, (feature_name, shap_value) in enumerate(sorted_features, 1):
                    feature_value = features_dict.get(feature_name, "N/A")
                    
                    # Format feature value
                    if isinstance(feature_value, float):
                        if abs(feature_value) < 0.0001 or abs(feature_value) > 100000:
                            feat_str = f"{feature_value:.2e}"
                        else:
                            feat_str = f"{feature_value:.6f}"
                    else:
                        feat_str = str(feature_value)
                    
                    # Format SHAP value
                    if isinstance(shap_value, float):
                        if abs(shap_value) < 0.0001 or abs(shap_value) > 100000:
                            shap_str = f"{shap_value:.2e}"
                        else:
                            shap_str = f"{shap_value:.6f}"
                    else:
                        shap_str = str(shap_value)
                    
                    desc += f"{idx}. **{feature_name}**: Value={feat_str}, SHAP={shap_str}\n"
            else:
                desc += "No SHAP analysis available for this client."
            
            logger.info(f"Generated SHAP context for client {client_id}")
            return desc
            
        except Exception as e:
            logger.error(f"Error getting client SHAP features: {e}", exc_info=True)
            return None
    
    def get_context_for_question(self, question: str) -> Tuple[str, bool]:
        """
        Get context for the question.
        Returns: (context_text, is_fl_question)
        """
        is_fl_question = self._is_fl_system_question(question)
        
        if not is_fl_question:
            logger.info("General knowledge question - no JSON context needed")
            return "", False
        
        # FL-specific question - get relevant clients
        relevant_clients = self._select_relevant_clients(question)
        
        if len(relevant_clients) == 0:
            return "No relevant detection data found in the dataset.", True
        
        # Convert to natural language
        descriptions = []
        for client in relevant_clients:
            description = self._convert_client_to_natural_language(client)
            descriptions.append(description)
        
        # Build context
        context = f"""
Round {self.data.round_num} Detection Results:
- Timestamp: {self.data.timestamp}
- Total clients analyzed: {len(self.data.clients)}
- Total samples: {self.data.num_samples}

Relevant Detection Records:
{chr(10).join(descriptions)}
""".strip()
        
        logger.info(f"Context length: {len(context)} chars")
        return context, True


# Global instance
_analyzer: Optional[JSONAnalyzer] = None


def get_json_analyzer() -> JSONAnalyzer:
    """Get or initialize the JSON analyzer"""
    global _analyzer
    if _analyzer is None:
        from chatbot_app.config import FL_DATA_S3_PATH, FL_DATA_LOCAL_PATH
        _analyzer = JSONAnalyzer(s3_path=FL_DATA_S3_PATH, local_path=FL_DATA_LOCAL_PATH)
    return _analyzer
