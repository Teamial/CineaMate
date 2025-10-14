"""
ε-Greedy Policy Implementation

Simple exploration-exploitation strategy:
- With probability ε: explore (uniform random selection)
- With probability (1-ε): exploit (select arm with highest mean reward)

Propensity scoring:
- For best arm: p = (1-ε) + ε/|A|
- For other arms: p = ε/|A|
"""

import random
import logging
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
import redis

from .base import BasePolicy, PolicyResult

logger = logging.getLogger(__name__)

class EpsilonGreedyPolicy(BasePolicy):
    """ε-greedy bandit policy with configurable exploration rate"""
    
    def __init__(self, db: Session, redis_client: Optional[redis.Redis] = None, 
                 epsilon: float = 0.1):
        super().__init__(db, redis_client)
        self.epsilon = epsilon
        logger.info(f"Initialized ε-greedy policy with ε={epsilon}")
    
    @property
    def name(self) -> str:
        return "egreedy"
    
    def select(self, user_ctx: Dict[str, Any], arms: List[str]) -> PolicyResult:
        """
        Select arm using ε-greedy strategy
        
        Args:
            user_ctx: User context (not used in basic ε-greedy)
            arms: List of available arm IDs
            
        Returns:
            PolicyResult with selected arm and propensity score
        """
        if not arms:
            raise ValueError("No arms available for selection")
        
        # Get current states for all arms
        arm_states = {}
        for arm_id in arms:
            arm_states[arm_id] = self._get_arm_state(arm_id, user_ctx)
        
        # Decide: explore or exploit
        if random.random() < self.epsilon:
            # Explore: uniform random selection
            selected_arm = random.choice(arms)
            p_score = 1.0 / len(arms)  # Uniform probability
            confidence = 0.5  # Low confidence for exploration
            action = "explore"
        else:
            # Exploit: select arm with highest mean reward
            # Handle ties with uniform random selection
            best_arms = []
            best_mean = -1
            
            for arm_id, state in arm_states.items():
                mean_reward = state['mean_reward']
                if mean_reward > best_mean:
                    best_arms = [arm_id]
                    best_mean = mean_reward
                elif mean_reward == best_mean:
                    best_arms.append(arm_id)
            
            # Random tie-breaking
            selected_arm = random.choice(best_arms)
            
            # Propensity score for best arm
            p_score = (1 - self.epsilon) + (self.epsilon / len(arms))
            confidence = best_mean
            action = "exploit"
        
        logger.debug(f"ε-greedy selected arm {selected_arm} ({action}), p_score={p_score:.3f}")
        
        return PolicyResult(
            arm_id=selected_arm,
            p_score=p_score,
            confidence=confidence,
            metadata={
                'action': action,
                'epsilon': self.epsilon,
                'arm_count': len(arms),
                'selected_mean': arm_states[selected_arm]['mean_reward']
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
        logger.debug(f"ε-greedy updating arm {arm_id} with reward {reward}")
        self._update_arm_state(arm_id, reward, ctx)
    
    def get_exploration_rate(self) -> float:
        """Get current exploration rate"""
        return self.epsilon
    
    def set_exploration_rate(self, epsilon: float) -> None:
        """Update exploration rate (for dynamic tuning)"""
        if not 0 <= epsilon <= 1:
            raise ValueError(f"Epsilon must be between 0 and 1, got {epsilon}")
        
        old_epsilon = self.epsilon
        self.epsilon = epsilon
        logger.info(f"Updated ε-greedy exploration rate: {old_epsilon} → {epsilon}")
    
    def get_arm_statistics(self, arms: List[str], ctx: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
        """Get statistics for all arms"""
        stats = {}
        
        for arm_id in arms:
            state = self._get_arm_state(arm_id, ctx)
            stats[arm_id] = {
                'count': state['count'],
                'mean_reward': state['mean_reward'],
                'sum_reward': state['sum_reward'],
                'selection_probability': self._get_selection_probability(arm_id, arms, ctx)
            }
        
        return stats
    
    def _get_selection_probability(self, arm_id: str, arms: List[str], ctx: Dict[str, Any]) -> float:
        """Calculate selection probability for an arm"""
        arm_states = {}
        for aid in arms:
            arm_states[aid] = self._get_arm_state(aid, ctx)
        
        # Find best arm(s)
        best_mean = max(state['mean_reward'] for state in arm_states.values())
        best_arms = [aid for aid, state in arm_states.items() if state['mean_reward'] == best_mean]
        
        if arm_id in best_arms:
            # Best arm: exploitation probability + exploration probability
            return (1 - self.epsilon) + (self.epsilon / len(arms))
        else:
            # Non-best arm: only exploration probability
            return self.epsilon / len(arms)
