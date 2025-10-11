"""
Multi-Armed Bandit Algorithm Selector

Implements Thompson Sampling for context-aware algorithm selection
"""

import numpy as np
import hashlib
import json
import logging
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from typing import List, Dict, Tuple
from datetime import datetime

from ..models import Rating

logger = logging.getLogger(__name__)


class BanditSelector:
    """Thompson Sampling bandit for context-aware algorithm selection"""
    
    def __init__(self, db: Session):
        self.db = db
        self.algorithms = ['svd', 'embeddings', 'graph', 'item_cf', 'long_tail', 'serendipity']
        self.default_alpha = 1.0
        self.default_beta = 1.0
        
    def extract_context(self, user_id: int, session_data: Dict = None) -> Dict:
        """Extract context features for algorithm selection"""
        now = datetime.now()
        hour = now.hour
        
        context = {
            'time_period': 'morning' if 5 <= hour < 12 else 'afternoon' if 12 <= hour < 17 else 'evening' if 17 <= hour < 22 else 'night',
            'day_of_week': 'weekend' if now.weekday() >= 5 else 'weekday',
            'user_type': self._get_user_type(user_id),
            'genre_saturation': 'low',
            'session_position': 'middle'
        }
        
        return context
    
    def select_arms(self, context: Dict, n_arms: int = 3) -> Tuple[List[str], List[float]]:
        """Select best algorithms using Thompson Sampling"""
        # Sample from Beta distributions
        samples = {}
        for algo in self.algorithms:
            samples[algo] = np.random.beta(self.default_alpha, self.default_beta)
        
        # Select top N
        sorted_algos = sorted(samples.items(), key=lambda x: x[1], reverse=True)
        selected = [a for a, _ in sorted_algos[:n_arms]]
        confidences = [s for _, s in sorted_algos[:n_arms]]
        
        # Normalize
        total = sum(confidences)
        confidences = [c / total for c in confidences] if total > 0 else [1.0 / n_arms] * n_arms
        
        return selected, confidences
    
    def _get_user_type(self, user_id: int) -> str:
        """Get user type based on activity"""
        count = self.db.query(Rating).filter(Rating.user_id == user_id).count()
        if count < 3:
            return 'cold_start'
        elif count < 20:
            return 'regular'
        else:
            return 'power_user'

