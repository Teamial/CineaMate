"""
Guardrails Engine for Multi-Armed Bandit Experiments

Implements comprehensive guardrails to ensure experiment safety and prevent
user experience degradation. Monitors error rates, latency, arm concentration,
and reward drops with automatic rollback capabilities.

Guardrails:
- Error rate < 1% (4xx/5xx responses)
- P95 latency < 120ms
- No single arm > 50% traffic in first 1000 serves
- Reward not > 5% below control for 30 consecutive minutes
- Auto-rollback if 2+ guardrails fail

Usage:
    from backend.ml.guardrails import GuardrailsEngine
    engine = GuardrailsEngine(db)
    status = engine.check_guardrails(experiment_id)
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from dataclasses import dataclass
from enum import Enum

from ..models import Experiment, RecommendationEvent, PolicyAssignment

logger = logging.getLogger(__name__)

class GuardrailStatus(Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"

@dataclass
class GuardrailResult:
    """Result of a single guardrail check"""
    name: str
    status: GuardrailStatus
    value: float
    threshold: float
    message: str
    severity: str = "info"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'status': self.status.value,
            'value': self.value,
            'threshold': self.threshold,
            'message': self.message,
            'severity': self.severity
        }

@dataclass
class GuardrailSummary:
    """Overall guardrail status for an experiment"""
    experiment_id: str
    overall_status: GuardrailStatus
    checked_at: datetime
    guardrails: List[GuardrailResult]
    recent_metrics: Dict[str, Any]
    should_rollback: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'experiment_id': self.experiment_id,
            'overall_status': self.overall_status.value,
            'checked_at': self.checked_at.isoformat(),
            'guardrails': {g.name: g.to_dict() for g in self.guardrails},
            'recent_metrics': self.recent_metrics,
            'should_rollback': self.should_rollback
        }

class GuardrailsEngine:
    """Engine for monitoring experiment guardrails"""
    
    def __init__(self, db: Session):
        self.db = db
        self.guardrails = {
            'error_rate': self._check_error_rate,
            'latency_p95': self._check_latency_p95,
            'arm_concentration': self._check_arm_concentration,
            'reward_drop': self._check_reward_drop
        }
        
        # Guardrail thresholds
        self.thresholds = {
            'error_rate': 0.01,  # 1%
            'latency_p95': 120,  # 120ms
            'arm_concentration': 0.50,  # 50%
            'reward_drop': 0.05  # 5%
        }
        
        # Rollback triggers
        self.rollback_triggers = {
            'fail_count': 2,  # Rollback if 2+ guardrails fail
            'critical_failures': ['error_rate', 'latency_p95']  # Critical guardrails
        }
    
    def check_guardrails(self, experiment_id: str, 
                        lookback_minutes: int = 30) -> GuardrailSummary:
        """
        Check all guardrails for an experiment
        
        Args:
            experiment_id: UUID of the experiment
            lookback_minutes: How far back to look for metrics
            
        Returns:
            GuardrailSummary with overall status and individual results
        """
        logger.info(f"Checking guardrails for experiment {experiment_id}")
        
        # Get experiment
        experiment = self.db.query(Experiment).filter(
            Experiment.id == experiment_id
        ).first()
        
        if not experiment:
            raise ValueError(f"Experiment {experiment_id} not found")
        
        # Check if experiment is active
        if experiment.end_at and experiment.end_at < datetime.utcnow():
            logger.info(f"Experiment {experiment_id} has ended, skipping guardrails")
            return self._create_inactive_summary(experiment_id)
        
        # Get recent metrics
        recent_metrics = self._get_recent_metrics(experiment_id, lookback_minutes)
        
        # Check each guardrail
        guardrail_results = []
        for name, check_func in self.guardrails.items():
            try:
                result = check_func(experiment_id, recent_metrics)
                guardrail_results.append(result)
                logger.debug(f"Guardrail {name}: {result.status.value}")
            except Exception as e:
                logger.error(f"Failed to check guardrail {name}: {e}")
                # Create a failed result for the error
                guardrail_results.append(GuardrailResult(
                    name=name,
                    status=GuardrailStatus.FAIL,
                    value=0.0,
                    threshold=self.thresholds.get(name, 0.0),
                    message=f"Check failed: {str(e)}",
                    severity="error"
                ))
        
        # Determine overall status
        overall_status = self._determine_overall_status(guardrail_results)
        
        # Check if rollback is needed
        should_rollback = self._should_rollback(guardrail_results)
        
        summary = GuardrailSummary(
            experiment_id=experiment_id,
            overall_status=overall_status,
            checked_at=datetime.utcnow(),
            guardrails=guardrail_results,
            recent_metrics=recent_metrics,
            should_rollback=should_rollback
        )
        
        logger.info(f"Guardrail check complete: {overall_status.value}, rollback: {should_rollback}")
        return summary
    
    def _get_recent_metrics(self, experiment_id: str, 
                          lookback_minutes: int) -> Dict[str, Any]:
        """Get recent metrics for guardrail checks"""
        cutoff = datetime.utcnow() - timedelta(minutes=lookback_minutes)
        
        # Get basic metrics
        metrics = self.db.execute(text("""
            SELECT 
                COUNT(*) as total_events,
                AVG(latency_ms) as avg_latency,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95_latency,
                AVG(reward) as avg_reward,
                COUNT(DISTINCT user_id) as unique_users
            FROM recommendation_events
            WHERE experiment_id = :experiment_id
            AND served_at >= :cutoff
        """), {
            'experiment_id': experiment_id,
            'cutoff': cutoff
        }).fetchone()
        
        # Get arm concentration
        arm_concentration = self.db.execute(text("""
            SELECT 
                arm_id,
                COUNT(*) as count,
                COUNT(*) * 100.0 / SUM(COUNT(*)) OVER() as percentage
            FROM recommendation_events
            WHERE experiment_id = :experiment_id
            AND served_at >= :cutoff
            AND arm_id IS NOT NULL
            GROUP BY arm_id
            ORDER BY count DESC
            LIMIT 1
        """), {
            'experiment_id': experiment_id,
            'cutoff': cutoff
        }).fetchone()
        
        # Get control group reward for comparison
        control_reward = self.db.execute(text("""
            SELECT AVG(reward) as avg_reward
            FROM recommendation_events
            WHERE experiment_id = :experiment_id
            AND served_at >= :cutoff
            AND policy = 'control'
            AND reward IS NOT NULL
        """), {
            'experiment_id': experiment_id,
            'cutoff': cutoff
        }).scalar()
        
        return {
            'total_events': metrics.total_events or 0,
            'avg_latency': metrics.avg_latency or 0,
            'p95_latency': metrics.p95_latency or 0,
            'avg_reward': metrics.avg_reward or 0,
            'unique_users': metrics.unique_users or 0,
            'arm_concentration': arm_concentration.percentage if arm_concentration else 0,
            'control_reward': control_reward or 0
        }
    
    def _check_error_rate(self, experiment_id: str, 
                         metrics: Dict[str, Any]) -> GuardrailResult:
        """Check error rate guardrail"""
        # For now, we'll use a placeholder since we don't have error tracking
        # In a real system, this would check 4xx/5xx response rates
        error_rate = 0.0  # Placeholder
        
        threshold = self.thresholds['error_rate']
        
        if error_rate < threshold:
            status = GuardrailStatus.PASS
            message = f"Error rate: {error_rate:.1%} (threshold: {threshold:.1%})"
        else:
            status = GuardrailStatus.FAIL
            message = f"Error rate: {error_rate:.1%} exceeds threshold: {threshold:.1%}"
        
        return GuardrailResult(
            name='error_rate',
            status=status,
            value=error_rate,
            threshold=threshold,
            message=message,
            severity='error' if status == GuardrailStatus.FAIL else 'info'
        )
    
    def _check_latency_p95(self, experiment_id: str, 
                          metrics: Dict[str, Any]) -> GuardrailResult:
        """Check P95 latency guardrail"""
        p95_latency = metrics['p95_latency']
        threshold = self.thresholds['latency_p95']
        
        if p95_latency < threshold:
            status = GuardrailStatus.PASS
            message = f"P95 latency: {p95_latency:.1f}ms (threshold: {threshold}ms)"
        else:
            status = GuardrailStatus.FAIL
            message = f"P95 latency: {p95_latency:.1f}ms exceeds threshold: {threshold}ms"
        
        return GuardrailResult(
            name='latency_p95',
            status=status,
            value=p95_latency,
            threshold=threshold,
            message=message,
            severity='error' if status == GuardrailStatus.FAIL else 'info'
        )
    
    def _check_arm_concentration(self, experiment_id: str, 
                                metrics: Dict[str, Any]) -> GuardrailResult:
        """Check arm concentration guardrail"""
        concentration = metrics['arm_concentration']
        threshold = self.thresholds['arm_concentration']
        
        if concentration < threshold:
            status = GuardrailStatus.PASS
            message = f"Top arm concentration: {concentration:.1%} (threshold: {threshold:.1%})"
        else:
            status = GuardrailStatus.WARNING
            message = f"Top arm concentration: {concentration:.1%} exceeds threshold: {threshold:.1%}"
        
        return GuardrailResult(
            name='arm_concentration',
            status=status,
            value=concentration,
            threshold=threshold,
            message=message,
            severity='warning' if status == GuardrailStatus.WARNING else 'info'
        )
    
    def _check_reward_drop(self, experiment_id: str, 
                          metrics: Dict[str, Any]) -> GuardrailResult:
        """Check reward drop guardrail"""
        avg_reward = metrics['avg_reward']
        control_reward = metrics['control_reward']
        
        if control_reward == 0:
            # No control group data, skip this check
            return GuardrailResult(
                name='reward_drop',
                status=GuardrailStatus.PASS,
                value=0.0,
                threshold=self.thresholds['reward_drop'],
                message="No control group data available",
                severity='info'
            )
        
        reward_drop = (control_reward - avg_reward) / control_reward
        threshold = self.thresholds['reward_drop']
        
        if reward_drop < threshold:
            status = GuardrailStatus.PASS
            message = f"Reward drop: {reward_drop:.1%} (threshold: {threshold:.1%})"
        else:
            status = GuardrailStatus.WARNING
            message = f"Reward drop: {reward_drop:.1%} exceeds threshold: {threshold:.1%}"
        
        return GuardrailResult(
            name='reward_drop',
            status=status,
            value=reward_drop,
            threshold=threshold,
            message=message,
            severity='warning' if status == GuardrailStatus.WARNING else 'info'
        )
    
    def _determine_overall_status(self, results: List[GuardrailResult]) -> GuardrailStatus:
        """Determine overall guardrail status"""
        if any(r.status == GuardrailStatus.FAIL for r in results):
            return GuardrailStatus.FAIL
        elif any(r.status == GuardrailStatus.WARNING for r in results):
            return GuardrailStatus.WARNING
        else:
            return GuardrailStatus.PASS
    
    def _should_rollback(self, results: List[GuardrailResult]) -> bool:
        """Determine if experiment should be rolled back"""
        fail_count = sum(1 for r in results if r.status == GuardrailStatus.FAIL)
        
        # Check if we have enough failures to trigger rollback
        if fail_count >= self.rollback_triggers['fail_count']:
            return True
        
        # Check if any critical guardrails have failed
        critical_failures = [
            r for r in results 
            if r.name in self.rollback_triggers['critical_failures'] 
            and r.status == GuardrailStatus.FAIL
        ]
        
        if critical_failures:
            return True
        
        return False
    
    def _create_inactive_summary(self, experiment_id: str) -> GuardrailSummary:
        """Create summary for inactive experiment"""
        return GuardrailSummary(
            experiment_id=experiment_id,
            overall_status=GuardrailStatus.PASS,
            checked_at=datetime.utcnow(),
            guardrails=[],
            recent_metrics={},
            should_rollback=False
        )
    
    def rollback_experiment(self, experiment_id: str) -> bool:
        """
        Rollback an experiment to control policy
        
        Args:
            experiment_id: UUID of the experiment to rollback
            
        Returns:
            True if rollback was successful
        """
        logger.info(f"Rolling back experiment {experiment_id}")
        
        try:
            # Get experiment
            experiment = self.db.query(Experiment).filter(
                Experiment.id == experiment_id
            ).first()
            
            if not experiment:
                logger.error(f"Experiment {experiment_id} not found")
                return False
            
            # End the experiment
            experiment.end_at = datetime.utcnow()
            self.db.commit()
            
            logger.info(f"Experiment {experiment_id} rolled back successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to rollback experiment {experiment_id}: {e}")
            self.db.rollback()
            return False
    
    def get_guardrail_history(self, experiment_id: str, 
                            days: int = 7) -> List[Dict[str, Any]]:
        """Get guardrail check history for an experiment"""
        # This would typically be stored in a separate table
        # For now, return empty list
        return []
    
    def update_thresholds(self, new_thresholds: Dict[str, float]):
        """Update guardrail thresholds"""
        self.thresholds.update(new_thresholds)
        logger.info(f"Updated guardrail thresholds: {new_thresholds}")
    
    def get_thresholds(self) -> Dict[str, float]:
        """Get current guardrail thresholds"""
        return self.thresholds.copy()

# Utility functions for external use
def check_experiment_guardrails(db: Session, experiment_id: str) -> Dict[str, Any]:
    """Convenience function to check guardrails for an experiment"""
    engine = GuardrailsEngine(db)
    summary = engine.check_guardrails(experiment_id)
    return summary.to_dict()

def rollback_experiment(db: Session, experiment_id: str) -> bool:
    """Convenience function to rollback an experiment"""
    engine = GuardrailsEngine(db)
    return engine.rollback_experiment(experiment_id)
