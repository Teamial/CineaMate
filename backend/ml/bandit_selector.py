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
from typing import List, Dict, Tuple, Optional
from datetime import datetime

from ..models import Rating, BanditState

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
    
    def _context_to_key(self, context: Dict) -> str:
        """Convert context dict to a stable string key"""
        # Create a sorted, deterministic string from context
        context_str = json.dumps(context, sort_keys=True)
        # Use first 40 chars of hash for readability
        context_hash = hashlib.sha256(context_str.encode()).hexdigest()[:40]
        return context_hash
    
    def _get_or_create_bandit_state(self, context_key: str, algorithm: str) -> BanditState:
        """Get existing bandit state or create new one with defaults"""
        state = self.db.query(BanditState).filter(
            BanditState.context_key == context_key,
            BanditState.algorithm == algorithm
        ).first()
        
        if not state:
            state = BanditState(
                context_key=context_key,
                algorithm=algorithm,
                alpha=self.default_alpha,
                beta=self.default_beta,
                total_pulls=0,
                total_successes=0,
                total_failures=0
            )
            self.db.add(state)
            self.db.commit()
            self.db.refresh(state)
        
        return state
    
    def select_arms(self, context: Dict, n_arms: int = 3) -> Tuple[List[str], List[float]]:
        """Select best algorithms using Thompson Sampling"""
        context_key = self._context_to_key(context)
        
        # Sample from Beta distributions based on stored states
        samples = {}
        for algo in self.algorithms:
            state = self._get_or_create_bandit_state(context_key, algo)
            # Sample from Beta(alpha, beta)
            samples[algo] = np.random.beta(state.alpha, state.beta)
        
        # Select top N
        sorted_algos = sorted(samples.items(), key=lambda x: x[1], reverse=True)
        selected = [a for a, _ in sorted_algos[:n_arms]]
        confidences = [s for _, s in sorted_algos[:n_arms]]
        
        # Normalize confidences to sum to 1
        total = sum(confidences)
        confidences = [c / total for c in confidences] if total > 0 else [1.0 / n_arms] * n_arms
        
        logger.info(f"Bandit selected arms for context {context_key[:10]}...: {list(zip(selected, [f'{c:.2%}' for c in confidences]))}")
        
        return selected, confidences
    
    def update_bandit(self, context: Dict, algorithm: str, outcome: str):
        """
        Update bandit state based on user feedback
        
        Args:
            context: Context dict when recommendation was made
            algorithm: Algorithm that generated the recommendation
            outcome: 'success', 'failure', or 'neutral'
        """
        context_key = self._context_to_key(context)
        state = self._get_or_create_bandit_state(context_key, algorithm)
        
        # Update based on outcome
        if outcome == 'success':
            state.alpha += 1
            state.total_successes += 1
            logger.info(f"Bandit success for {algorithm} in context {context_key[:10]}... (α={state.alpha:.1f})")
        elif outcome == 'failure':
            state.beta += 1
            state.total_failures += 1
            logger.info(f"Bandit failure for {algorithm} in context {context_key[:10]}... (β={state.beta:.1f})")
        # 'neutral' outcome doesn't update alpha/beta
        
        state.total_pulls += 1
        self.db.commit()
    
    def get_bandit_stats(self, context: Optional[Dict] = None) -> Dict:
        """Get statistics about bandit performance"""
        query = self.db.query(BanditState)
        
        if context:
            context_key = self._context_to_key(context)
            query = query.filter(BanditState.context_key == context_key)
        
        states = query.all()
        
        stats = {}
        for state in states:
            key = f"{state.context_key[:10]}..._{state.algorithm}"
            success_rate = state.alpha / (state.alpha + state.beta) if (state.alpha + state.beta) > 0 else 0
            stats[key] = {
                'algorithm': state.algorithm,
                'context_key': state.context_key,
                'alpha': state.alpha,
                'beta': state.beta,
                'success_rate': success_rate,
                'total_pulls': state.total_pulls,
                'total_successes': state.total_successes,
                'total_failures': state.total_failures
            }
        
        return stats
    
    def _get_user_type(self, user_id: int) -> str:
        """Get user type based on activity"""
        count = self.db.query(Rating).filter(Rating.user_id == user_id).count()
        if count < 3:
            return 'cold_start'
        elif count < 20:
            return 'regular'
        else:
            return 'power_user'

