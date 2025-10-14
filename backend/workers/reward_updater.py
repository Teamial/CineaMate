"""
Background Worker for Reward Updates and Policy State Synchronization

Handles async reward computation and policy state updates to avoid blocking
the main recommendation API. Uses APScheduler for periodic execution.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_

from ..database import SessionLocal
from ..models import RecommendationEvent
from .reward_calculator import RewardCalculator
from .policies import get_policy

logger = logging.getLogger(__name__)

class RewardUpdater:
    """Background worker for reward computation and policy updates"""
    
    def __init__(self, db: Optional[Session] = None):
        self.db = db or SessionLocal()
        self.reward_calculator = RewardCalculator(self.db)
        self.batch_size = 100
        self.max_retries = 3
        self.retry_delay = 300  # 5 minutes
    
    def process_pending_rewards(self, hours_back: int = 24) -> Dict[str, Any]:
        """
        Process all pending reward computations
        
        Args:
            hours_back: How many hours back to look for events
            
        Returns:
            Processing statistics
        """
        logger.info(f"Starting reward processing for events from last {hours_back} hours")
        
        # Get pending events
        pending_events = self.reward_calculator.get_pending_events(hours_back)
        
        if not pending_events:
            logger.info("No pending events found")
            return {
                'processed': 0,
                'failed': 0,
                'policy_updates': 0,
                'errors': []
            }
        
        logger.info(f"Found {len(pending_events)} pending events")
        
        processed = 0
        failed = 0
        policy_updates = 0
        errors = []
        
        # Process in batches
        for i in range(0, len(pending_events), self.batch_size):
            batch = pending_events[i:i + self.batch_size]
            
            try:
                # Compute rewards for batch
                rewards = self.reward_calculator.batch_compute_rewards(batch)
                
                # Update policy states
                batch_policy_updates = self._update_policy_states(batch, rewards)
                
                processed += len(batch)
                policy_updates += batch_policy_updates
                
                logger.info(f"Processed batch {i//self.batch_size + 1}: "
                           f"{len(batch)} events, {batch_policy_updates} policy updates")
                
            except Exception as e:
                logger.error(f"Failed to process batch {i//self.batch_size + 1}: {e}")
                failed += len(batch)
                errors.append(str(e))
        
        logger.info(f"Reward processing complete: {processed} processed, "
                   f"{failed} failed, {policy_updates} policy updates")
        
        return {
            'processed': processed,
            'failed': failed,
            'policy_updates': policy_updates,
            'errors': errors
        }
    
    def _update_policy_states(self, events: List[RecommendationEvent], 
                            rewards: Dict[int, float]) -> int:
        """
        Update policy states based on computed rewards
        
        Args:
            events: List of events with computed rewards
            rewards: Dictionary mapping event_id to reward value
            
        Returns:
            Number of policy updates performed
        """
        updates = 0
        
        # Group events by policy and context
        policy_events = {}
        
        for event in events:
            if not event.policy or not event.arm_id:
                continue
            
            reward = rewards.get(event.id)
            if reward is None:
                continue
            
            # Create context key
            context = event.context or {}
            
            policy_key = (event.policy, event.arm_id, str(context))
            if policy_key not in policy_events:
                policy_events[policy_key] = []
            
            policy_events[policy_key].append((event, reward))
        
        # Update each policy's state
        for (policy_name, arm_id, context_str), event_rewards in policy_events.items():
            try:
                # Get policy instance
                policy = get_policy(policy_name, self.db)
                
                # Parse context
                import json
                context = json.loads(context_str) if context_str != '{}' else {}
                
                # Update policy state for each event
                for event, reward in event_rewards:
                    policy.update(arm_id, reward, context)
                    updates += 1
                
                logger.debug(f"Updated {policy_name} policy for arm {arm_id}: "
                           f"{len(event_rewards)} rewards")
                
            except Exception as e:
                logger.error(f"Failed to update policy {policy_name} for arm {arm_id}: {e}")
        
        return updates
    
    def process_single_event(self, event_id: int) -> bool:
        """
        Process a single event's reward computation
        
        Args:
            event_id: ID of the event to process
            
        Returns:
            True if successful, False otherwise
        """
        try:
            event = self.db.query(RecommendationEvent).filter(
                RecommendationEvent.id == event_id
            ).first()
            
            if not event:
                logger.warning(f"Event {event_id} not found")
                return False
            
            if event.reward is not None:
                logger.debug(f"Event {event_id} already has reward {event.reward}")
                return True
            
            # Compute reward
            reward = self.reward_calculator.compute_reward(event)
            
            # Update policy state if applicable
            if event.policy and event.arm_id:
                try:
                    policy = get_policy(event.policy, self.db)
                    context = event.context or {}
                    policy.update(event.arm_id, reward, context)
                    
                    logger.debug(f"Updated policy {event.policy} for event {event_id}")
                    
                except Exception as e:
                    logger.error(f"Failed to update policy for event {event_id}: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to process event {event_id}: {e}")
            return False
    
    def cleanup_old_events(self, days_old: int = 30) -> int:
        """
        Clean up old events that no longer need processing
        
        Args:
            days_old: Age threshold in days
            
        Returns:
            Number of events cleaned up
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        # Find events older than cutoff that still have null rewards
        old_events = self.db.query(RecommendationEvent).filter(
            and_(
                RecommendationEvent.created_at < cutoff_date,
                RecommendationEvent.reward.is_(None)
            )
        ).all()
        
        if not old_events:
            return 0
        
        # Set default reward for old events (0.0 - no interaction)
        for event in old_events:
            event.reward = 0.0
        
        self.db.commit()
        
        logger.info(f"Cleaned up {len(old_events)} old events with null rewards")
        return len(old_events)
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Get statistics about reward processing"""
        
        # Count events by reward status
        total_events = self.db.query(RecommendationEvent).count()
        processed_events = self.db.query(RecommendationEvent).filter(
            RecommendationEvent.reward.isnot(None)
        ).count()
        pending_events = total_events - processed_events
        
        # Count events by experiment
        experiment_counts = {}
        experiments = self.db.query(RecommendationEvent.experiment_id).filter(
            RecommendationEvent.experiment_id.isnot(None)
        ).distinct().all()
        
        for (exp_id,) in experiments:
            count = self.db.query(RecommendationEvent).filter(
                RecommendationEvent.experiment_id == exp_id
            ).count()
            experiment_counts[str(exp_id)] = count
        
        # Count events by policy
        policy_counts = {}
        policies = self.db.query(RecommendationEvent.policy).filter(
            RecommendationEvent.policy.isnot(None)
        ).distinct().all()
        
        for (policy,) in policies:
            count = self.db.query(RecommendationEvent).filter(
                RecommendationEvent.policy == policy
            ).count()
            policy_counts[policy] = count
        
        return {
            'total_events': total_events,
            'processed_events': processed_events,
            'pending_events': pending_events,
            'processing_rate': processed_events / total_events if total_events > 0 else 0,
            'experiment_counts': experiment_counts,
            'policy_counts': policy_counts,
            'last_processed': self._get_last_processed_time()
        }
    
    def _get_last_processed_time(self) -> Optional[datetime]:
        """Get timestamp of last processed event"""
        last_event = self.db.query(RecommendationEvent).filter(
            RecommendationEvent.reward.isnot(None)
        ).order_by(RecommendationEvent.created_at.desc()).first()
        
        return last_event.created_at if last_event else None
    
    def retry_failed_events(self) -> int:
        """
        Retry processing events that failed previously
        
        Returns:
            Number of events retried
        """
        # Find events that are old enough to retry but still have null rewards
        retry_cutoff = datetime.utcnow() - timedelta(seconds=self.retry_delay)
        
        failed_events = self.db.query(RecommendationEvent).filter(
            and_(
                RecommendationEvent.created_at < retry_cutoff,
                RecommendationEvent.reward.is_(None)
            )
        ).limit(self.batch_size).all()
        
        if not failed_events:
            return 0
        
        retried = 0
        for event in failed_events:
            if self.process_single_event(event.id):
                retried += 1
        
        logger.info(f"Retried {retried} failed events")
        return retried

# Scheduler integration
def setup_reward_worker_scheduler(scheduler):
    """Set up scheduled jobs for reward processing"""
    
    def process_rewards_job():
        """Job to process pending rewards"""
        try:
            updater = RewardUpdater()
            stats = updater.process_pending_rewards()
            logger.info(f"Reward processing job completed: {stats}")
        except Exception as e:
            logger.error(f"Reward processing job failed: {e}")
    
    def cleanup_job():
        """Job to clean up old events"""
        try:
            updater = RewardUpdater()
            cleaned = updater.cleanup_old_events()
            logger.info(f"Cleanup job completed: {cleaned} events cleaned")
        except Exception as e:
            logger.error(f"Cleanup job failed: {e}")
    
    def retry_job():
        """Job to retry failed events"""
        try:
            updater = RewardUpdater()
            retried = updater.retry_failed_events()
            logger.info(f"Retry job completed: {retried} events retried")
        except Exception as e:
            logger.error(f"Retry job failed: {e}")
    
    # Schedule jobs
    scheduler.add_job(
        process_rewards_job,
        'interval',
        minutes=5,  # Every 5 minutes
        id='process_rewards',
        replace_existing=True
    )
    
    scheduler.add_job(
        cleanup_job,
        'interval',
        hours=1,  # Every hour
        id='cleanup_old_events',
        replace_existing=True
    )
    
    scheduler.add_job(
        retry_job,
        'interval',
        minutes=15,  # Every 15 minutes
        id='retry_failed_events',
        replace_existing=True
    )
    
    logger.info("Reward worker scheduler jobs configured")
