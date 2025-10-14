"""
Policy Protocol and Base Classes for Multi-Armed Bandit Algorithms

This module defines the Policy interface that all bandit algorithms must implement,
along with base classes for state management and persistence.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import hashlib
import json
import logging
from datetime import datetime
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

@dataclass
class PolicyResult:
    """Result from policy arm selection"""
    arm_id: str
    p_score: Optional[float]  # Propensity score for IPS
    confidence: float  # Confidence/score for logging
    metadata: Dict[str, Any] = None

class Policy(ABC):
    """Abstract base class for bandit policies"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Policy name identifier"""
        pass
    
    @abstractmethod
    def select(self, user_ctx: Dict[str, Any], arms: List[str]) -> PolicyResult:
        """
        Select an arm given user context and available arms
        
        Args:
            user_ctx: User context (time, user_type, etc.)
            arms: List of available arm IDs
            
        Returns:
            PolicyResult with selected arm and propensity score
        """
        pass
    
    @abstractmethod
    def update(self, arm_id: str, reward: float, ctx: Dict[str, Any]) -> None:
        """
        Update policy state based on observed reward
        
        Args:
            arm_id: Arm that was selected
            reward: Observed reward (0-1)
            ctx: Context when arm was selected
        """
        pass
    
    def get_state(self, arm_id: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Get current state for an arm in given context"""
        return self.state_manager.get_state(self.name, arm_id, self._hash_context(ctx))
    
    def _hash_context(self, ctx: Dict[str, Any]) -> str:
        """Create deterministic hash of context for state key"""
        # Sort keys for consistent hashing
        sorted_items = sorted(ctx.items())
        context_str = json.dumps(sorted_items, sort_keys=True)
        return hashlib.md5(context_str.encode()).hexdigest()[:16]

class PolicyStateManager:
    """Manages policy state persistence and caching"""
    
    def __init__(self, db: Session, redis_client: Optional['redis.Redis'] = None):
        self.db = db
        self.redis = redis_client
        self.cache_ttl = 300  # 5 minutes
    
    def get_state(self, policy: str, arm_id: str, context_key: str) -> Dict[str, Any]:
        """Get policy state with caching"""
        cache_key = f"policy_state:{policy}:{arm_id}:{context_key}"
        
        # Try Redis cache first
        if self.redis:
            try:
                cached = self.redis.get(cache_key)
                if cached:
                    return json.loads(cached)
            except Exception as e:
                logger.warning(f"Redis cache read failed: {e}")
        
        # Fallback to database
        from ..models import PolicyState
        
        state = self.db.query(PolicyState).filter(
            PolicyState.policy == policy,
            PolicyState.arm_id == arm_id,
            PolicyState.context_key == context_key
        ).first()
        
        if state:
            result = {
                'count': state.count,
                'sum_reward': state.sum_reward,
                'mean_reward': state.mean_reward,
                'alpha': state.alpha,
                'beta': state.beta,
                'last_selected_at': state.last_selected_at
            }
        else:
            # Default state
            result = {
                'count': 0,
                'sum_reward': 0.0,
                'mean_reward': 0.0,
                'alpha': 1.0,
                'beta': 1.0,
                'last_selected_at': None
            }
        
        # Cache in Redis
        if self.redis:
            try:
                self.redis.setex(cache_key, self.cache_ttl, json.dumps(result, default=str))
            except Exception as e:
                logger.warning(f"Redis cache write failed: {e}")
        
        return result
    
    def update_state(self, policy: str, arm_id: str, context_key: str, 
                    count: int, sum_reward: float, mean_reward: float,
                    alpha: float = None, beta: float = None,
                    last_selected_at: datetime = None) -> None:
        """Update policy state atomically"""
        from ..models import PolicyState
        
        try:
            # Use upsert pattern
            state = self.db.query(PolicyState).filter(
                PolicyState.policy == policy,
                PolicyState.arm_id == arm_id,
                PolicyState.context_key == context_key
            ).first()
            
            if state:
                # Update existing
                state.count = count
                state.sum_reward = sum_reward
                state.mean_reward = mean_reward
                if alpha is not None:
                    state.alpha = alpha
                if beta is not None:
                    state.beta = beta
                if last_selected_at is not None:
                    state.last_selected_at = last_selected_at
                state.updated_at = datetime.utcnow()
            else:
                # Create new
                state = PolicyState(
                    policy=policy,
                    arm_id=arm_id,
                    context_key=context_key,
                    count=count,
                    sum_reward=sum_reward,
                    mean_reward=mean_reward,
                    alpha=alpha or 1.0,
                    beta=beta or 1.0,
                    last_selected_at=last_selected_at
                )
                self.db.add(state)
            
            self.db.commit()
            
            # Invalidate cache
            if self.redis:
                cache_key = f"policy_state:{policy}:{arm_id}:{context_key}"
                try:
                    self.redis.delete(cache_key)
                except Exception as e:
                    logger.warning(f"Redis cache delete failed: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to update policy state: {e}")
            self.db.rollback()
            raise

class BasePolicy(Policy):
    """Base implementation with common functionality"""
    
    def __init__(self, db: Session, redis_client: Optional['redis.Redis'] = None):
        self.state_manager = PolicyStateManager(db, redis_client)
        self.db = db
    
    def _get_arm_state(self, arm_id: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Get state for specific arm in context"""
        return self.state_manager.get_state(self.name, arm_id, self._hash_context(ctx))
    
    def _update_arm_state(self, arm_id: str, reward: float, ctx: Dict[str, Any]) -> None:
        """Update state for specific arm after observing reward"""
        context_key = self._hash_context(ctx)
        current_state = self._get_arm_state(arm_id, ctx)
        
        # Update statistics
        new_count = current_state['count'] + 1
        new_sum_reward = current_state['sum_reward'] + reward
        new_mean_reward = new_sum_reward / new_count
        
        # Update state
        self.state_manager.update_state(
            policy=self.name,
            arm_id=arm_id,
            context_key=context_key,
            count=new_count,
            sum_reward=new_sum_reward,
            mean_reward=new_mean_reward,
            last_selected_at=datetime.utcnow()
        )
        
        logger.debug(f"Updated {self.name} state for arm {arm_id}: count={new_count}, mean={new_mean_reward:.3f}")


def get_policy(name: str, db: Session, redis_client: Optional['redis.Redis'] = None) -> Policy:
    """Factory function to get policy by name"""
    from .thompson_sampling import ThompsonSamplingPolicy
    from .epsilon_greedy import EpsilonGreedyPolicy
    from .ucb1 import UCB1Policy
    
    policies = {
        'thompson': ThompsonSamplingPolicy,
        'egreedy': EpsilonGreedyPolicy,
        'epsilon_greedy': EpsilonGreedyPolicy,  # Alias
        'ucb': UCB1Policy,
        'ucb1': UCB1Policy  # Alias
    }
    
    if name not in policies:
        raise ValueError(f"Unknown policy: {name}. Available: {list(policies.keys())}")
    
    return policies[name](db, redis_client)
