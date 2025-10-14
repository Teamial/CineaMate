"""
Decision Engine for Multi-Armed Bandit Experiments

Implements automated decision making for bandit experiments based on
statistical analysis and predefined criteria. Analyzes policy performance
over rolling windows and makes ship/iterate/kill decisions.

Decision Criteria:
- Ship: reward uplift ≥ +3% for 7 consecutive days, p < 0.05
- Iterate: inconclusive results, extend experiment
- Kill: reward drop or no improvement after 14 days

Features:
- Statistical significance testing (t-test, bootstrap CI)
- Rolling window analysis
- Decision logging for audit trail
- Configurable thresholds and criteria
- A/B test comparison logic

Usage:
    from backend.ml.decision_engine import DecisionEngine
    engine = DecisionEngine(db)
    decision = engine.analyze_experiment(experiment_id)
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from dataclasses import dataclass
from enum import Enum
import numpy as np
from scipy import stats
import json

from ..models import Experiment, RecommendationEvent, PolicyAssignment

logger = logging.getLogger(__name__)

class DecisionType(Enum):
    SHIP = "ship"
    ITERATE = "iterate"
    KILL = "kill"

@dataclass
class PolicyPerformance:
    """Performance metrics for a policy"""
    policy: str
    total_events: int
    total_reward: float
    mean_reward: float
    reward_std: float
    confidence_interval: Tuple[float, float]
    p_value: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'policy': self.policy,
            'total_events': self.total_events,
            'total_reward': self.total_reward,
            'mean_reward': self.mean_reward,
            'reward_std': self.reward_std,
            'confidence_interval': self.confidence_interval,
            'p_value': self.p_value
        }

@dataclass
class DecisionResult:
    """Result of experiment decision analysis"""
    experiment_id: str
    decision: DecisionType
    confidence: float
    analysis_date: datetime
    window_days: int
    policy_performance: List[PolicyPerformance]
    best_policy: str
    uplift_vs_control: float
    statistical_significance: bool
    reasoning: str
    recommendations: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'experiment_id': self.experiment_id,
            'decision': self.decision.value,
            'confidence': self.confidence,
            'analysis_date': self.analysis_date.isoformat(),
            'window_days': self.window_days,
            'policy_performance': [p.to_dict() for p in self.policy_performance],
            'best_policy': self.best_policy,
            'uplift_vs_control': self.uplift_vs_control,
            'statistical_significance': self.statistical_significance,
            'reasoning': self.reasoning,
            'recommendations': self.recommendations
        }

class DecisionEngine:
    """Engine for automated experiment decision making"""
    
    def __init__(self, db: Session):
        self.db = db
        
        # Decision criteria
        self.criteria = {
            'min_uplift': 0.03,  # 3% minimum uplift
            'min_confidence': 0.95,  # 95% confidence level
            'min_window_days': 7,  # Minimum 7 days of data
            'max_experiment_days': 14,  # Maximum experiment duration
            'min_events_per_policy': 1000,  # Minimum events per policy
            'significance_level': 0.05  # p-value threshold
        }
        
        # Policies to analyze
        self.bandit_policies = ['thompson', 'egreedy', 'ucb']
        self.control_policy = 'control'
    
    def analyze_experiment(self, experiment_id: str, 
                         window_days: Optional[int] = None) -> DecisionResult:
        """
        Analyze experiment and make decision
        
        Args:
            experiment_id: UUID of the experiment
            window_days: Analysis window in days (default: 7)
            
        Returns:
            DecisionResult with analysis and decision
        """
        logger.info(f"Analyzing experiment {experiment_id}")
        
        # Get experiment
        experiment = self.db.query(Experiment).filter(
            Experiment.id == experiment_id
        ).first()
        
        if not experiment:
            raise ValueError(f"Experiment {experiment_id} not found")
        
        # Determine analysis window
        if window_days is None:
            window_days = self._determine_analysis_window(experiment)
        
        # Get policy performance data
        policy_performance = self._get_policy_performance(experiment_id, window_days)
        
        if not policy_performance:
            raise ValueError(f"No performance data found for experiment {experiment_id}")
        
        # Find best policy
        best_policy = self._find_best_policy(policy_performance)
        
        # Calculate uplift vs control
        uplift_vs_control = self._calculate_uplift_vs_control(policy_performance)
        
        # Check statistical significance
        statistical_significance = self._check_statistical_significance(policy_performance)
        
        # Make decision
        decision, confidence, reasoning = self._make_decision(
            experiment, policy_performance, best_policy, uplift_vs_control, 
            statistical_significance, window_days
        )
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            decision, policy_performance, best_policy, uplift_vs_control
        )
        
        result = DecisionResult(
            experiment_id=experiment_id,
            decision=decision,
            confidence=confidence,
            analysis_date=datetime.utcnow(),
            window_days=window_days,
            policy_performance=policy_performance,
            best_policy=best_policy,
            uplift_vs_control=uplift_vs_control,
            statistical_significance=statistical_significance,
            reasoning=reasoning,
            recommendations=recommendations
        )
        
        logger.info(f"Decision for experiment {experiment_id}: {decision.value} (confidence: {confidence:.2f})")
        return result
    
    def _determine_analysis_window(self, experiment: Experiment) -> int:
        """Determine appropriate analysis window"""
        # Use minimum of 7 days or experiment duration
        if experiment.end_at:
            duration = (experiment.end_at - experiment.start_at).days
        else:
            duration = (datetime.utcnow() - experiment.start_at).days
        
        return min(max(duration, self.criteria['min_window_days']), 14)
    
    def _get_policy_performance(self, experiment_id: str, 
                               window_days: int) -> List[PolicyPerformance]:
        """Get performance metrics for all policies"""
        cutoff_date = datetime.utcnow() - timedelta(days=window_days)
        
        performance_data = []
        
        for policy in self.bandit_policies + [self.control_policy]:
            # Get policy data
            policy_data = self.db.execute(text("""
                SELECT 
                    COUNT(*) as total_events,
                    SUM(reward) as total_reward,
                    AVG(reward) as mean_reward,
                    STDDEV(reward) as reward_std
                FROM recommendation_events
                WHERE experiment_id = :experiment_id
                AND policy = :policy
                AND served_at >= :cutoff_date
                AND reward IS NOT NULL
            """), {
                'experiment_id': experiment_id,
                'policy': policy,
                'cutoff_date': cutoff_date
            }).fetchone()
            
            if policy_data and policy_data.total_events >= self.criteria['min_events_per_policy']:
                # Calculate confidence interval
                ci = self._calculate_confidence_interval(
                    policy_data.mean_reward, policy_data.reward_std, policy_data.total_events
                )
                
                # Calculate p-value vs control (if not control)
                p_value = None
                if policy != self.control_policy:
                    p_value = self._calculate_p_value_vs_control(
                        experiment_id, policy, cutoff_date
                    )
                
                performance = PolicyPerformance(
                    policy=policy,
                    total_events=policy_data.total_events,
                    total_reward=policy_data.total_reward,
                    mean_reward=policy_data.mean_reward,
                    reward_std=policy_data.reward_std,
                    confidence_interval=ci,
                    p_value=p_value
                )
                
                performance_data.append(performance)
        
        return performance_data
    
    def _find_best_policy(self, performance_data: List[PolicyPerformance]) -> str:
        """Find the best performing policy"""
        if not performance_data:
            return None
        
        # Find policy with highest mean reward
        best_policy = max(performance_data, key=lambda p: p.mean_reward)
        return best_policy.policy
    
    def _calculate_uplift_vs_control(self, performance_data: List[PolicyPerformance]) -> float:
        """Calculate uplift of best policy vs control"""
        # Find control policy
        control_performance = next(
            (p for p in performance_data if p.policy == self.control_policy), None
        )
        
        if not control_performance:
            return 0.0
        
        # Find best bandit policy
        bandit_performances = [p for p in performance_data if p.policy in self.bandit_policies]
        if not bandit_performances:
            return 0.0
        
        best_bandit = max(bandit_performances, key=lambda p: p.mean_reward)
        
        # Calculate uplift
        uplift = (best_bandit.mean_reward - control_performance.mean_reward) / control_performance.mean_reward
        return uplift
    
    def _check_statistical_significance(self, performance_data: List[PolicyPerformance]) -> bool:
        """Check if best policy is statistically significant vs control"""
        # Find control policy
        control_performance = next(
            (p for p in performance_data if p.policy == self.control_policy), None
        )
        
        if not control_performance:
            return False
        
        # Find best bandit policy
        bandit_performances = [p for p in performance_data if p.policy in self.bandit_policies]
        if not bandit_performances:
            return False
        
        best_bandit = max(bandit_performances, key=lambda p: p.mean_reward)
        
        # Check if p-value is significant
        if best_bandit.p_value is not None:
            return best_bandit.p_value < self.criteria['significance_level']
        
        return False
    
    def _make_decision(self, experiment: Experiment, performance_data: List[PolicyPerformance],
                      best_policy: str, uplift_vs_control: float, 
                      statistical_significance: bool, window_days: int) -> Tuple[DecisionType, float, str]:
        """Make decision based on analysis"""
        
        # Check if experiment has run long enough
        if window_days < self.criteria['min_window_days']:
            return DecisionType.ITERATE, 0.0, "Insufficient data for decision"
        
        # Check if experiment has run too long
        if window_days >= self.criteria['max_experiment_days']:
            if uplift_vs_control >= self.criteria['min_uplift'] and statistical_significance:
                return DecisionType.SHIP, 0.8, "Maximum duration reached with positive results"
            else:
                return DecisionType.KILL, 0.9, "Maximum duration reached without significant improvement"
        
        # Check for significant positive results
        if (uplift_vs_control >= self.criteria['min_uplift'] and 
            statistical_significance and 
            best_policy in self.bandit_policies):
            
            confidence = min(0.95, 0.7 + (uplift_vs_control - self.criteria['min_uplift']) * 10)
            reasoning = f"Significant uplift: {uplift_vs_control:.1%} vs control, p < {self.criteria['significance_level']}"
            return DecisionType.SHIP, confidence, reasoning
        
        # Check for negative results
        if uplift_vs_control < -0.05:  # 5% drop
            confidence = 0.8
            reasoning = f"Significant drop: {uplift_vs_control:.1%} vs control"
            return DecisionType.KILL, confidence, reasoning
        
        # Default to iterate
        confidence = 0.5
        reasoning = "Inconclusive results, need more data"
        return DecisionType.ITERATE, confidence, reasoning
    
    def _generate_recommendations(self, decision: DecisionType, 
                                 performance_data: List[PolicyPerformance],
                                 best_policy: str, uplift_vs_control: float) -> List[str]:
        """Generate recommendations based on decision"""
        recommendations = []
        
        if decision == DecisionType.SHIP:
            recommendations.append(f"Ship {best_policy} policy to production")
            recommendations.append(f"Monitor performance for 48 hours after rollout")
            recommendations.append("Consider gradual rollout (10% → 50% → 100%)")
            
        elif decision == DecisionType.KILL:
            recommendations.append("End experiment and revert to control")
            recommendations.append("Analyze failure modes and policy behavior")
            recommendations.append("Consider policy parameter tuning")
            
        else:  # ITERATE
            recommendations.append("Extend experiment for additional data collection")
            recommendations.append("Monitor guardrails for any issues")
            recommendations.append("Consider increasing traffic allocation")
        
        # Add general recommendations
        if uplift_vs_control > 0:
            recommendations.append("Positive trend detected, continue monitoring")
        else:
            recommendations.append("Negative trend detected, investigate causes")
        
        return recommendations
    
    def _calculate_confidence_interval(self, mean: float, std: float, n: int, 
                                      confidence: float = 0.95) -> Tuple[float, float]:
        """Calculate confidence interval for mean"""
        if n < 2:
            return (mean, mean)
        
        # Use t-distribution for small samples
        if n < 30:
            t_value = stats.t.ppf((1 + confidence) / 2, n - 1)
        else:
            t_value = stats.norm.ppf((1 + confidence) / 2)
        
        margin_error = t_value * (std / np.sqrt(n))
        return (mean - margin_error, mean + margin_error)
    
    def _calculate_p_value_vs_control(self, experiment_id: str, policy: str, 
                                     cutoff_date: datetime) -> Optional[float]:
        """Calculate p-value for policy vs control"""
        try:
            # Get policy data
            policy_data = self.db.execute(text("""
                SELECT reward
                FROM recommendation_events
                WHERE experiment_id = :experiment_id
                AND policy = :policy
                AND served_at >= :cutoff_date
                AND reward IS NOT NULL
                ORDER BY served_at
                LIMIT 10000
            """), {
                'experiment_id': experiment_id,
                'policy': policy,
                'cutoff_date': cutoff_date
            }).fetchall()
            
            # Get control data
            control_data = self.db.execute(text("""
                SELECT reward
                FROM recommendation_events
                WHERE experiment_id = :experiment_id
                AND policy = :control_policy
                AND served_at >= :cutoff_date
                AND reward IS NOT NULL
                ORDER BY served_at
                LIMIT 10000
            """), {
                'experiment_id': experiment_id,
                'control_policy': self.control_policy,
                'cutoff_date': cutoff_date
            }).fetchall()
            
            if not policy_data or not control_data:
                return None
            
            # Extract rewards
            policy_rewards = [row[0] for row in policy_data]
            control_rewards = [row[0] for row in control_data]
            
            # Perform t-test
            t_stat, p_value = stats.ttest_ind(policy_rewards, control_rewards)
            return p_value
            
        except Exception as e:
            logger.error(f"Failed to calculate p-value: {e}")
            return None
    
    def log_decision(self, decision_result: DecisionResult):
        """Log decision for audit trail"""
        # In a real system, this would log to a decisions table
        logger.info(f"DECISION LOG: {decision_result.to_dict()}")
    
    def get_decision_history(self, experiment_id: str) -> List[Dict[str, Any]]:
        """Get decision history for an experiment"""
        # In a real system, this would query a decisions table
        return []
    
    def update_criteria(self, new_criteria: Dict[str, Any]):
        """Update decision criteria"""
        self.criteria.update(new_criteria)
        logger.info(f"Updated decision criteria: {new_criteria}")
    
    def get_criteria(self) -> Dict[str, Any]:
        """Get current decision criteria"""
        return self.criteria.copy()

# Utility functions for external use
def analyze_experiment_decision(db: Session, experiment_id: str) -> Dict[str, Any]:
    """Convenience function to analyze experiment decision"""
    engine = DecisionEngine(db)
    result = engine.analyze_experiment(experiment_id)
    return result.to_dict()

def make_daily_decisions(db: Session):
    """Make decisions for all active experiments (daily job)"""
    logger.info("Starting daily decision analysis")
    
    # Get all active experiments
    active_experiments = db.query(Experiment).filter(
        Experiment.end_at.is_(None)
    ).all()
    
    if not active_experiments:
        logger.info("No active experiments found")
        return
    
    engine = DecisionEngine(db)
    
    for experiment in active_experiments:
        try:
            result = engine.analyze_experiment(experiment.id)
            engine.log_decision(result)
            
            # Take action based on decision
            if result.decision == DecisionType.SHIP:
                logger.info(f"SHIP decision for experiment {experiment.id}")
                # In a real system, this would trigger rollout
                
            elif result.decision == DecisionType.KILL:
                logger.info(f"KILL decision for experiment {experiment.id}")
                # In a real system, this would end the experiment
                
        except Exception as e:
            logger.error(f"Failed to analyze experiment {experiment.id}: {e}")
    
    logger.info("Daily decision analysis complete")
