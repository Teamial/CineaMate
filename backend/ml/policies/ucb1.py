"""
UCB1 Policy Implementation

Upper Confidence Bound algorithm:
- Select arm with highest upper confidence bound
- UCB = mean_reward + sqrt(2 * log(total_pulls) / arm_pulls)
- Handles cold-start arms with minimum pull requirement

Note: UCB1 doesn't have analytic propensity scores, so p_score=None
"""

import math
import random
import logging
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
import redis

from .base import BasePolicy, PolicyResult

logger = logging.getLogger(__name__)

class UCB1Policy(BasePolicy):
    """UCB1 bandit policy with confidence bounds"""
    
    def __init__(self, db: Session, redis_client: Optional[redis.Redis] = None,
                 min_pulls: int = 1):
        super().__init__(db, redis_client)
        self.min_pulls = min_pulls
        logger.info(f"Initialized UCB1 policy with min_pulls={min_pulls}")
    
    @property
    def name(self) -> str:
        return "ucb"
    
    def select(self, user_ctx: Dict[str, Any], arms: List[str]) -> PolicyResult:
        """
        Select arm using UCB1 strategy
        
        Args:
            user_ctx: User context (not used in basic UCB1)
            arms: List of available arm IDs
            
        Returns:
            PolicyResult with selected arm and confidence bound
        """
        if not arms:
            raise ValueError("No arms available for selection")
        
        # Get current states for all arms
        arm_states = {}
        total_pulls = 0
        
        for arm_id in arms:
            state = self._get_arm_state(arm_id, user_ctx)
            arm_states[arm_id] = state
            total_pulls += state['count']
        
        # Calculate UCB for each arm
        ucb_values = {}
        for arm_id, state in arm_states.items():
            count = state['count']
            mean_reward = state['mean_reward']
            
            if count < self.min_pulls:
                # Cold-start: force exploration
                ucb_value = float('inf')
            else:
                # UCB1 formula: mean + sqrt(2 * log(total_pulls) / arm_pulls)
                confidence_bound = math.sqrt(2 * math.log(max(total_pulls, 1)) / count)
                ucb_value = mean_reward + confidence_bound
            
            ucb_values[arm_id] = ucb_value
        
        # Select arm with highest UCB
        max_ucb = max(ucb_values.values())
        best_arms = [arm_id for arm_id, ucb in ucb_values.items() if ucb == max_ucb]
        
        # Random tie-breaking
        selected_arm = random.choice(best_arms)
        
        # UCB1 doesn't have analytic propensity scores
        # We could approximate with tie-breaker randomization, but keep it simple
        p_score = None
        
        logger.debug(f"UCB1 selected arm {selected_arm}, UCB={ucb_values[selected_arm]:.3f}")
        
        return PolicyResult(
            arm_id=selected_arm,
            p_score=p_score,
            confidence=ucb_values[selected_arm],
            metadata={
                'ucb_value': ucb_values[selected_arm],
                'mean_reward': arm_states[selected_arm]['mean_reward'],
                'arm_count': arm_states[selected_arm]['count'],
                'total_pulls': total_pulls,
                'confidence_bound': ucb_values[selected_arm] - arm_states[selected_arm]['mean_reward']
            }
        )
    
    def update(self, arm_id: str, reward: float, ctx: Dict[str, Any]) -> None:
        """
        Update policy state based on observed reward
        
        Args:
            arm_id: Arm that was selected
            reward: Observed reward (0-1)
            ctx: Context when arm was selected
        """
        logger.debug(f"UCB1 updating arm {arm_id} with reward {reward}")
        self._update_arm_state(arm_id, reward, ctx)
    
    def get_arm_statistics(self, arms: List[str], ctx: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
        """Get statistics for all arms including UCB values"""
        stats = {}
        
        # Calculate total pulls
        total_pulls = 0
        arm_states = {}
        
        for arm_id in arms:
            state = self._get_arm_state(arm_id, ctx)
            arm_states[arm_id] = state
            total_pulls += state['count']
        
        # Calculate UCB for each arm
        for arm_id in arms:
            state = arm_states[arm_id]
            count = state['count']
            mean_reward = state['mean_reward']
            
            if count < self.min_pulls:
                ucb_value = float('inf')
                confidence_bound = float('inf')
            else:
                confidence_bound = math.sqrt(2 * math.log(max(total_pulls, 1)) / count)
                ucb_value = mean_reward + confidence_bound
            
            stats[arm_id] = {
                'count': count,
                'mean_reward': mean_reward,
                'sum_reward': state['sum_reward'],
                'ucb_value': ucb_value,
                'confidence_bound': confidence_bound,
                'is_cold_start': count < self.min_pulls
            }
        
        return stats
    
    def get_min_pulls(self) -> int:
        """Get minimum pulls required before UCB calculation"""
        return self.min_pulls
    
    def set_min_pulls(self, min_pulls: int) -> None:
        """Update minimum pulls requirement"""
        if min_pulls < 1:
            raise ValueError(f"min_pulls must be >= 1, got {min_pulls}")
        
        old_min_pulls = self.min_pulls
        self.min_pulls = min_pulls
        logger.info(f"Updated UCB1 min_pulls: {old_min_pulls} → {min_pulls}")
    
    def get_exploration_schedule(self, arms: List[str], ctx: Dict[str, Any]) -> Dict[str, float]:
        """
        Get exploration schedule showing how UCB balances exploration vs exploitation
        
        Returns approximate exploration probability for each arm
        """
        arm_states = {}
        total_pulls = 0
        
        for arm_id in arms:
            state = self._get_arm_state(arm_id, ctx)
            arm_states[arm_id] = state
            total_pulls += state['count']
        
        exploration_probs = {}
        
        for arm_id, state in arm_states.items():
            count = state['count']
            
            if count < self.min_pulls:
                # Cold-start arms get equal probability
                exploration_probs[arm_id] = 1.0 / len(arms)
            else:
                # Approximate exploration probability based on confidence bound
                confidence_bound = math.sqrt(2 * math.log(max(total_pulls, 1)) / count)
                mean_reward = state['mean_reward']
                
                # Higher confidence bound = more exploration
                # Normalize to get rough probability estimate
                exploration_probs[arm_id] = min(confidence_bound / (mean_reward + 1.0), 0.5)
        
        return exploration_probs
