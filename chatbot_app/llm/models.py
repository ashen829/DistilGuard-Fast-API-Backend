"""
Data models for FL system JSON data
"""

from typing import Dict, Optional, Any
from dataclasses import dataclass, asdict
import json


@dataclass
class Features:
    """Client feature values"""
    param_mean: float
    param_std: float
    param_min: float
    param_max: float
    param_median: float
    param_range: float
    param_abs_mean: float
    param_skew: float
    param_kurtosis: float
    param_neg_ratio: float
    param_zero_ratio: float
    last_layer_mean: float
    last_layer_std: float
    last_layer_min: float
    last_layer_max: float
    last_layer_abs_mean: float
    last_layer_neg_ratio: float
    first_vs_last_mean_ratio: float
    first_vs_last_std_ratio: float
    avg_l1_distance: float
    avg_l2_distance: float
    cosine_similarity: float

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Features':
        """Create from dictionary"""
        return cls(**data)


@dataclass
class ShapValues:
    """SHAP interpretation values"""
    base_value: float
    feature_shap_values: Dict[str, float]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ShapValues':
        """Create from dictionary"""
        return cls(
            base_value=data.get('base_value', 0.0),
            feature_shap_values=data.get('feature_shap_values', {})
        )


@dataclass
class ClientRecord:
    """Single client detection record"""
    client_id: int
    round_num: int
    classification: str  # 'malicious' or 'benign'
    malicious_probability: float
    features: Features
    shap_values: Optional[ShapValues] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ClientRecord':
        """Create from dictionary"""
        features = Features.from_dict(data.get('features', {}))
        shap = None
        if 'shap_values' in data:
            shap = ShapValues.from_dict(data['shap_values'])
        
        return cls(
            client_id=data['client_id'],
            round_num=data['round_num'],
            classification=data['classification'],
            malicious_probability=data['malicious_probability'],
            features=features,
            shap_values=shap
        )


@dataclass
class RoundData:
    """Single round detection data"""
    round_num: int
    timestamp: str
    num_samples: int
    clients: list  # List of ClientRecord

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RoundData':
        """Create from dictionary"""
        clients = [ClientRecord.from_dict(c) for c in data.get('clients', [])]
        return cls(
            round_num=data['round_num'],
            timestamp=data['timestamp'],
            num_samples=data['num_samples'],
            clients=clients
        )
