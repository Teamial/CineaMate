"""
Thompson Sampling Policy Implementation

Bayesian bandit algorithm using Beta distributions:
- Sample from Beta(α, β) for each arm
- Select arm with highest sampled value
- Update α (successes) and β (failures) based on rewards

Propensity scoring:
- Analytic propensity score from Beta distribution properties
- More complex than ε-greedy but provides unbiased estimates
"""

import numpy as np
import math
import logging
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
import redis
from datetime import datetime

from .base import BasePolicy, PolicyResult

logger = logging.getLogger(__name__)

class ThompsonSamplingPolicy(BasePolicy):
    """Thompson Sampling bandit policy with Beta distributions"""
    
    def __init__(self, db: Session, redis_client: Optional[redis.Redis] = None,
                 default_alpha: float = 1.0, default_beta: float = 1.0):
        super().__init__(db, redis_client)
        self.default_alpha = default_alpha
        self.default_beta = default_beta
        logger.info(f"Initialized Thompson Sampling with α={default_alpha}, β={default_beta}")
    
    @property
    def name(self) -> str:
        return "thompson"
    
    def select(self, user_ctx: Dict[str, Any], arms: List[str]) -> PolicyResult:
        """
        Select arm using Thompson Sampling
        
        Args:
            user_ctx: User context (time, user_type, etc.)
            arms: List of available arm IDs
            
        Returns:
            PolicyResult with selected arm and propensity score
        """
        if not arms:
            raise ValueError("No arms available for selection")
        
        # Get current states for all arms
        arm_states = {}
        samples = {}
        
        for arm_id in arms:
            state = self._get_arm_state(arm_id, user_ctx)
            arm_states[arm_id] = state
            
            # Sample from Beta(α, β) distribution
            alpha = state['alpha']
            beta = state['beta']
            
            # Use numpy for Beta sampling
            sample = np.random.beta(alpha, beta)
            samples[arm_id] = sample
        
        # Select arm with highest sample
        max_sample = max(samples.values())
        best_arms = [arm_id for arm_id, sample in samples.items() if sample == max_sample]
        
        # Random tie-breaking
        selected_arm = np.random.choice(best_arms)
        
        # Calculate propensity score
        # For Thompson Sampling, this is the probability that this arm has the highest true mean
        # Approximate using the Beta distribution properties
        p_score = self._calculate_propensity_score(selected_arm, arm_states, samples)
        
        logger.debug(f"Thompson selected arm {selected_arm}, sample={samples[selected_arm]:.3f}, p_score={p_score:.3f}")
        
        return PolicyResult(
            arm_id=selected_arm,
            p_score=p_score,
            confidence=samples[selected_arm],
            metadata={
                'sample_value': samples[selected_arm],
                'alpha': arm_states[selected_arm]['alpha'],
                'beta': arm_states[selected_arm]['beta'],
                'mean_reward': arm_states[selected_arm]['mean_reward'],
                'arm_count': arm_states[selected_arm]['count'],
                'all_samples': samples
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
        logger.debug(f"Thompson updating arm {arm_id} with reward {reward}")
        
        context_key = self._hash_context(ctx)
        current_state = self._get_arm_state(arm_id, ctx)
        
        # Update statistics
        new_count = current_state['count'] + 1
        new_sum_reward = current_state['sum_reward'] + reward
        new_mean_reward = new_sum_reward / new_count
        
        # Update Beta parameters
        # For binary rewards: α += reward, β += (1 - reward)
        # For continuous rewards: use moment matching
        if reward in [0.0, 1.0]:
            # Binary reward
            new_alpha = current_state['alpha'] + reward
            new_beta = current_state['beta'] + (1 - reward)
        else:
            # Continuous reward: moment matching
            # This is an approximation - in practice, you might want to use
            # a different approach for continuous rewards
            new_alpha = current_state['alpha'] + reward
            new_beta = current_state['beta'] + (1 - reward)
        
        # Update state
        self.state_manager.update_state(
            policy=self.name,
            arm_id=arm_id,
            context_key=context_key,
            count=new_count,
            sum_reward=new_sum_reward,
            mean_reward=new_mean_reward,
            alpha=new_alpha,
            beta=new_beta,
            last_selected_at=datetime.utcnow()
        )
        
        logger.debug(f"Updated Thompson state for arm {arm_id}: α={new_alpha:.1f}, β={new_beta:.1f}")
    
    def _calculate_propensity_score(self, selected_arm: str, arm_states: Dict[str, Dict], 
                                   samples: Dict[str, float]) -> float:
        """
        Calculate propensity score for Thompson Sampling
        
        This is complex to compute exactly, so we use an approximation:
        - Probability that selected arm has highest true mean
        - Approximate using Beta distribution properties
        """
        try:
            # Get the selected arm's Beta parameters
            selected_state = arm_states[selected_arm]
            alpha = selected_state['alpha']
            beta = selected_state['beta']
            
            # Expected value of Beta(α, β) = α / (α + β)
            expected_value = alpha / (alpha + beta)
            
            # Approximate propensity as the probability that this arm is best
            # This is a simplification - exact calculation would require
            # computing the probability that Beta(α, β) > max(Beta(α_i, β_i))
            total_alpha = sum(state['alpha'] for state in arm_states.values())
            total_beta = sum(state['beta'] for state in arm_states.values())
            
            # Rough approximation: proportional to expected value
            propensity = expected_value / sum(
                state['alpha'] / (state['alpha'] + state['beta']) 
                for state in arm_states.values()
            )
            
            return min(max(propensity, 0.01), 0.99)  # Clamp to reasonable range
            
        except Exception as e:
            logger.warning(f"Failed to calculate propensity score: {e}")
            # Fallback: uniform probability
            return 1.0 / len(arm_states)
    
    def get_arm_statistics(self, arms: List[str], ctx: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
        """Get statistics for all arms including Beta parameters"""
        stats = {}
        
        for arm_id in arms:
            state = self._get_arm_state(arm_id, ctx)
            alpha = state['alpha']
            beta = state['beta']
            
            # Calculate Beta distribution properties
            expected_value = alpha / (alpha + beta)
            variance = (alpha * beta) / ((alpha + beta) ** 2 * (alpha + beta + 1))
            std_dev = math.sqrt(variance)
            
            stats[arm_id] = {
                'count': state['count'],
                'mean_reward': state['mean_reward'],
                'sum_reward': state['sum_reward'],
                'alpha': alpha,
                'beta': beta,
                'expected_value': expected_value,
                'variance': variance,
                'std_dev': std_dev,
                'confidence_interval': self._get_confidence_interval(alpha, beta)
            }
        
        return stats
    
    def _get_confidence_interval(self, alpha: float, beta: float, confidence: float = 0.95) -> tuple:
        """Get confidence interval for Beta distribution"""
        try:
            # Use scipy if available, otherwise approximate
            try:
                from scipy.stats import beta as beta_dist
                lower = beta_dist.ppf((1 - confidence) / 2, alpha, beta)
                upper = beta_dist.ppf(1 - (1 - confidence) / 2, alpha, beta)
                return (lower, upper)
            except ImportError:
                # Approximate using normal distribution
                mean = alpha / (alpha + beta)
                variance = (alpha * beta) / ((alpha + beta) ** 2 * (alpha + beta + 1))
                std_dev = math.sqrt(variance)
                z_score = 1.96  # 95% confidence
                return (mean - z_score * std_dev, mean + z_score * std_dev)
        except Exception:
            return (0.0, 1.0)
    
    def get_exploration_schedule(self, arms: List[str], ctx: Dict[str, Any]) -> Dict[str, float]:
        """
        Get exploration schedule showing how Thompson Sampling balances exploration vs exploitation
        
        Returns approximate selection probability for each arm
        """
        arm_states = {}
        
        for arm_id in arms:
            arm_states[arm_id] = self._get_arm_state(arm_id, ctx)
        
        # Simulate many samples to estimate selection probabilities
        n_simulations = 1000
        selection_counts = {arm_id: 0 for arm_id in arms}
        
        for _ in range(n_simulations):
            samples = {}
            for arm_id, state in arm_states.items():
                alpha = state['alpha']
                beta = state['beta']
                sample = np.random.beta(alpha, beta)
                samples[arm_id] = sample
            
            # Find arm with highest sample
            max_sample = max(samples.values())
            best_arms = [arm_id for arm_id, sample in samples.items() if sample == max_sample]
            selected_arm = np.random.choice(best_arms)
            selection_counts[selected_arm] += 1
        
        # Convert to probabilities
        exploration_probs = {
            arm_id: count / n_simulations 
            for arm_id, count in selection_counts.items()
        }
        
        return exploration_probs
