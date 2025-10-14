"""
Experiment Manager for Multi-Armed Bandit A/B Testing

Handles deterministic user-to-policy assignments, traffic allocation,
and experiment lifecycle management.
"""

import hashlib
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import redis
import uuid

from ..models import Experiment, PolicyAssignment, User

logger = logging.getLogger(__name__)

class ExperimentManager:
    """Manages bandit experiments and user assignments"""
    
    def __init__(self, db: Session, redis_client: Optional[redis.Redis] = None):
        self.db = db
        self.redis = redis_client
        self.cache_ttl = 3600  # 1 hour
    
    def create_experiment(self, name: str, start_at: datetime, 
                         traffic_pct: float = 1.0, default_policy: str = 'thompson',
                         end_at: Optional[datetime] = None, notes: Optional[str] = None) -> Experiment:
        """
        Create a new bandit experiment
        
        Args:
            name: Experiment name
            start_at: When experiment starts
            traffic_pct: Percentage of traffic to include (0.0-1.0)
            default_policy: Fallback policy if assignment fails
            end_at: When experiment ends (optional)
            notes: Additional notes
            
        Returns:
            Created experiment
        """
        if not 0 <= traffic_pct <= 1:
            raise ValueError(f"traffic_pct must be between 0 and 1, got {traffic_pct}")
        
        experiment = Experiment(
            name=name,
            start_at=start_at,
            end_at=end_at,
            traffic_pct=traffic_pct,
            default_policy=default_policy,
            notes=notes
        )
        
        self.db.add(experiment)
        self.db.commit()
        
        logger.info(f"Created experiment {experiment.id}: {name} ({traffic_pct:.1%} traffic)")
        return experiment
    
    def assign_user_to_policy(self, experiment_id: uuid.UUID, user_id: int, 
                             policies: List[str]) -> Tuple[str, int]:
        """
        Assign user to a policy deterministically
        
        Args:
            experiment_id: Experiment UUID
            user_id: User ID
            policies: List of available policies
            
        Returns:
            Tuple of (policy, bucket) assigned to user
        """
        # Check if user already assigned
        existing = self.db.query(PolicyAssignment).filter(
            PolicyAssignment.experiment_id == experiment_id,
            PolicyAssignment.user_id == user_id
        ).first()
        
        if existing:
            logger.debug(f"User {user_id} already assigned to {existing.policy} in experiment {experiment_id}")
            return existing.policy, existing.bucket
        
        # Get experiment
        experiment = self.db.query(Experiment).filter(Experiment.id == experiment_id).first()
        if not experiment:
            raise ValueError(f"Experiment {experiment_id} not found")
        
        # Check if experiment is active
        now = datetime.utcnow()
        if now < experiment.start_at:
            logger.warning(f"Experiment {experiment_id} not started yet")
            return experiment.default_policy, 0
        
        if experiment.end_at and now > experiment.end_at:
            logger.warning(f"Experiment {experiment_id} has ended")
            return experiment.default_policy, 0
        
        # Deterministic assignment using hash
        assignment_key = f"{experiment_id}:{user_id}"
        hash_value = int(hashlib.md5(assignment_key.encode()).hexdigest(), 16)
        
        # Check traffic allocation
        bucket = hash_value % 100
        traffic_threshold = int(experiment.traffic_pct * 100)
        
        if bucket >= traffic_threshold:
            # User not in experiment traffic
            logger.debug(f"User {user_id} not in experiment traffic (bucket {bucket} >= {traffic_threshold})")
            return experiment.default_policy, bucket
        
        # Assign to policy based on hash
        policy_index = hash_value % len(policies)
        assigned_policy = policies[policy_index]
        
        # Create assignment record
        assignment = PolicyAssignment(
            experiment_id=experiment_id,
            user_id=user_id,
            policy=assigned_policy,
            bucket=bucket
        )
        
        self.db.add(assignment)
        self.db.commit()
        
        # Cache assignment
        self._cache_assignment(experiment_id, user_id, assigned_policy, bucket)
        
        logger.debug(f"Assigned user {user_id} to policy {assigned_policy} (bucket {bucket})")
        return assigned_policy, bucket
    
    def get_user_assignment(self, experiment_id: uuid.UUID, user_id: int) -> Optional[Tuple[str, int]]:
        """
        Get user's policy assignment for an experiment
        
        Args:
            experiment_id: Experiment UUID
            user_id: User ID
            
        Returns:
            Tuple of (policy, bucket) or None if not assigned
        """
        # Try cache first
        cached = self._get_cached_assignment(experiment_id, user_id)
        if cached:
            return cached
        
        # Query database
        assignment = self.db.query(PolicyAssignment).filter(
            PolicyAssignment.experiment_id == experiment_id,
            PolicyAssignment.user_id == user_id
        ).first()
        
        if assignment:
            # Cache result
            self._cache_assignment(experiment_id, user_id, assignment.policy, assignment.bucket)
            return assignment.policy, assignment.bucket
        
        return None
    
    def get_experiment_stats(self, experiment_id: uuid.UUID) -> Dict[str, any]:
        """Get experiment statistics"""
        experiment = self.db.query(Experiment).filter(Experiment.id == experiment_id).first()
        if not experiment:
            raise ValueError(f"Experiment {experiment_id} not found")
        
        # Get assignment counts by policy
        assignments = self.db.query(PolicyAssignment).filter(
            PolicyAssignment.experiment_id == experiment_id
        ).all()
        
        policy_counts = {}
        for assignment in assignments:
            policy_counts[assignment.policy] = policy_counts.get(assignment.policy, 0) + 1
        
        # Get total users
        total_users = self.db.query(User).count()
        
        # Calculate traffic allocation
        traffic_users = int(total_users * experiment.traffic_pct)
        
        return {
            'experiment_id': str(experiment_id),
            'name': experiment.name,
            'start_at': experiment.start_at,
            'end_at': experiment.end_at,
            'traffic_pct': experiment.traffic_pct,
            'default_policy': experiment.default_policy,
            'status': self._get_experiment_status(experiment),
            'total_users': total_users,
            'traffic_users': traffic_users,
            'assigned_users': len(assignments),
            'policy_distribution': policy_counts,
            'created_at': experiment.created_at
        }
    
    def list_active_experiments(self) -> List[Experiment]:
        """Get list of currently active experiments"""
        now = datetime.utcnow()
        
        return self.db.query(Experiment).filter(
            Experiment.start_at <= now,
            (Experiment.end_at.is_(None)) | (Experiment.end_at > now)
        ).all()
    
    def end_experiment(self, experiment_id: uuid.UUID) -> None:
        """End an experiment"""
        experiment = self.db.query(Experiment).filter(Experiment.id == experiment_id).first()
        if not experiment:
            raise ValueError(f"Experiment {experiment_id} not found")
        
        experiment.end_at = datetime.utcnow()
        self.db.commit()
        
        # Clear cache for this experiment
        self._clear_experiment_cache(experiment_id)
        
        logger.info(f"Ended experiment {experiment_id}: {experiment.name}")
    
    def _get_experiment_status(self, experiment: Experiment) -> str:
        """Get human-readable experiment status"""
        now = datetime.utcnow()
        
        if now < experiment.start_at:
            return "scheduled"
        elif experiment.end_at and now > experiment.end_at:
            return "ended"
        else:
            return "active"
    
    def _cache_assignment(self, experiment_id: uuid.UUID, user_id: int, 
                         policy: str, bucket: int) -> None:
        """Cache user assignment in Redis"""
        if not self.redis:
            return
        
        cache_key = f"exp:{experiment_id}:user:{user_id}"
        cache_value = f"{policy}:{bucket}"
        
        try:
            self.redis.setex(cache_key, self.cache_ttl, cache_value)
        except Exception as e:
            logger.warning(f"Failed to cache assignment: {e}")
    
    def _get_cached_assignment(self, experiment_id: uuid.UUID, user_id: int) -> Optional[Tuple[str, int]]:
        """Get cached user assignment from Redis"""
        if not self.redis:
            return None
        
        cache_key = f"exp:{experiment_id}:user:{user_id}"
        
        try:
            cached = self.redis.get(cache_key)
            if cached:
                policy, bucket_str = cached.decode().split(':')
                return policy, int(bucket_str)
        except Exception as e:
            logger.warning(f"Failed to get cached assignment: {e}")
        
        return None
    
    def _clear_experiment_cache(self, experiment_id: uuid.UUID) -> None:
        """Clear all cached assignments for an experiment"""
        if not self.redis:
            return
        
        try:
            pattern = f"exp:{experiment_id}:user:*"
            keys = self.redis.keys(pattern)
            if keys:
                self.redis.delete(*keys)
                logger.debug(f"Cleared {len(keys)} cached assignments for experiment {experiment_id}")
        except Exception as e:
            logger.warning(f"Failed to clear experiment cache: {e}")
    
    def get_traffic_allocation(self, experiment_id: uuid.UUID, policies: List[str]) -> Dict[str, float]:
        """
        Get traffic allocation for policies in an experiment
        
        Args:
            experiment_id: Experiment UUID
            policies: List of policies to allocate traffic to
            
        Returns:
            Dictionary mapping policy to traffic percentage
        """
        experiment = self.db.query(Experiment).filter(Experiment.id == experiment_id).first()
        if not experiment:
            raise ValueError(f"Experiment {experiment_id} not found")
        
        # Equal allocation among policies
        policy_traffic = experiment.traffic_pct / len(policies)
        
        return {policy: policy_traffic for policy in policies}
    
    def validate_experiment(self, experiment_id: uuid.UUID) -> Dict[str, any]:
        """
        Validate experiment configuration and return health status
        
        Returns:
            Dictionary with validation results
        """
        experiment = self.db.query(Experiment).filter(Experiment.id == experiment_id).first()
        if not experiment:
            return {'valid': False, 'error': 'Experiment not found'}
        
        issues = []
        warnings = []
        
        # Check timing
        now = datetime.utcnow()
        if experiment.start_at > now + timedelta(days=30):
            warnings.append("Experiment starts more than 30 days in the future")
        
        if experiment.end_at and experiment.end_at < experiment.start_at:
            issues.append("End date is before start date")
        
        # Check traffic allocation
        if experiment.traffic_pct <= 0:
            issues.append("Traffic percentage must be positive")
        elif experiment.traffic_pct > 1:
            issues.append("Traffic percentage cannot exceed 100%")
        
        # Check assignments
        assignments = self.db.query(PolicyAssignment).filter(
            PolicyAssignment.experiment_id == experiment_id
        ).count()
        
        if assignments == 0 and now >= experiment.start_at:
            warnings.append("No user assignments found for active experiment")
        
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'warnings': warnings,
            'assignment_count': assignments,
            'status': self._get_experiment_status(experiment)
        }
