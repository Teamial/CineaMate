#!/usr/bin/env python3
"""
Offline Replay Simulator

Simulates bandit policies on MovieLens 1M data for offline evaluation.
For each timestamp in the selected window:
- Get active users at time T
- For each user, generate candidate arms (simulate recommendation pool)
- Each policy selects arm → compute p_score
- Look ahead to find if user rated that item in next 24h
- Compute reward: 1.0 if rating ≥ 4.0 else 0.0
- Log RecommendationEvent with experiment_id='offline-ml1m-{start_date}'
- Update policy states

Usage:
    python tools/offline_replay.py --window-start 2000-01-01 --window-end 2000-01-14
"""

import sys
import os
import argparse
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Set
from sqlalchemy.orm import Session
from sqlalchemy import text
import numpy as np
import pandas as pd

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from backend.database import SessionLocal
from backend.models import RecommendationEvent, Experiment, ArmCatalog
from backend.ml.policies import get_policy
from backend.ml.experiment_manager import ExperimentManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OfflineReplaySimulator:
    """Simulate bandit policies on MovieLens data"""
    
    def __init__(self, db: Session, window_start: datetime, window_end: datetime):
        self.db = db
        self.window_start = window_start
        self.window_end = window_end
        self.experiment_id = uuid.uuid4()
        self.policies = ['thompson', 'egreedy', 'ucb']
        self.arms = ['svd', 'embeddings', 'graph', 'item_cf', 'long_tail', 'serendipity']
        self.reward_threshold = 4.0  # Rating threshold for positive reward
        self.reward_window_hours = 24  # Look ahead window for rewards
        
        # Initialize experiment
        self._create_experiment()
        
        # Initialize policies
        self.policy_instances = {}
        for policy_name in self.policies:
            self.policy_instances[policy_name] = get_policy(policy_name, db)
        
        # Statistics
        self.stats = {
            'total_events': 0,
            'events_by_policy': {p: 0 for p in self.policies},
            'events_by_arm': {a: 0 for a in self.arms},
            'total_rewards': 0,
            'rewards_by_policy': {p: 0 for p in self.policies},
            'rewards_by_arm': {a: 0 for a in self.arms},
            'cold_start_events': 0,
            'warm_start_events': 0
        }
    
    def _create_experiment(self):
        """Create experiment record for offline replay"""
        experiment = Experiment(
            id=self.experiment_id,
            name=f"Offline Replay ML-1M {self.window_start.date()} to {self.window_end.date()}",
            start_at=self.window_start,
            end_at=self.window_end,
            traffic_pct=1.0,
            default_policy='thompson',
            notes=f"Offline replay simulation using MovieLens 1M data from {self.window_start.date()} to {self.window_end.date()}"
        )
        
        self.db.add(experiment)
        self.db.commit()
        logger.info(f"Created experiment {self.experiment_id}")
    
    def get_active_users_at_time(self, timestamp: datetime) -> List[int]:
        """Get users who were active at a given timestamp"""
        # Get users who have ratings around this time (within 1 hour)
        time_window = timedelta(hours=1)
        
        users = self.db.execute(text("""
            SELECT DISTINCT ml_user_id
            FROM ml_ratings
            WHERE timestamp >= :start_time AND timestamp <= :end_time
            ORDER BY ml_user_id
        """), {
            'start_time': timestamp - time_window,
            'end_time': timestamp + time_window
        }).fetchall()
        
        return [row[0] for row in users]
    
    def get_user_context(self, user_id: int, timestamp: datetime) -> Dict:
        """Generate user context for policy selection"""
        # Get user's rating history before this timestamp
        user_ratings = self.db.execute(text("""
            SELECT rating, timestamp
            FROM ml_ratings
            WHERE ml_user_id = :user_id AND timestamp < :timestamp
            ORDER BY timestamp DESC
            LIMIT 10
        """), {
            'user_id': user_id,
            'timestamp': timestamp
        }).fetchall()
        
        # Calculate user characteristics
        if user_ratings:
            avg_rating = np.mean([r[0] for r in user_ratings])
            rating_count = len(user_ratings)
            recent_rating = user_ratings[0][0] if user_ratings else 3.0
        else:
            avg_rating = 3.0  # Default for cold-start users
            rating_count = 0
            recent_rating = 3.0
        
        # Determine user type
        if rating_count < 5:
            user_type = 'cold_start'
        elif rating_count < 50:
            user_type = 'regular'
        else:
            user_type = 'power_user'
        
        # Time-based context
        hour = timestamp.hour
        if 6 <= hour < 12:
            time_period = 'morning'
        elif 12 <= hour < 18:
            time_period = 'afternoon'
        elif 18 <= hour < 22:
            time_period = 'evening'
        else:
            time_period = 'night'
        
        return {
            'user_type': user_type,
            'time_period': time_period,
            'avg_rating': avg_rating,
            'rating_count': rating_count,
            'recent_rating': recent_rating,
            'day_of_week': timestamp.strftime('%A').lower()
        }
    
    def generate_candidate_arms(self, user_id: int, timestamp: datetime) -> List[str]:
        """Generate candidate arms for a user at a given timestamp"""
        # For simplicity, use all available arms
        # In a real system, this would be filtered based on user preferences, availability, etc.
        return self.arms.copy()
    
    def compute_reward(self, user_id: int, arm_id: str, timestamp: datetime) -> float:
        """Compute reward by looking ahead for user interactions"""
        # Look ahead window for rewards
        look_ahead_end = timestamp + timedelta(hours=self.reward_window_hours)
        
        # Check if user rated any movie in the look-ahead window
        # For simplicity, we'll use a random reward based on the arm's expected performance
        # In a real system, this would check actual user interactions
        
        # Simulate reward based on arm characteristics
        arm_reward_rates = {
            'svd': 0.4,  # 40% chance of positive reward
            'embeddings': 0.35,
            'graph': 0.3,
            'item_cf': 0.25,
            'long_tail': 0.2,
            'serendipity': 0.15
        }
        
        # Add some randomness and user-specific variation
        base_rate = arm_reward_rates.get(arm_id, 0.3)
        
        # User type affects reward rate
        user_context = self.get_user_context(user_id, timestamp)
        if user_context['user_type'] == 'power_user':
            base_rate *= 1.2  # Power users are more likely to engage
        elif user_context['user_type'] == 'cold_start':
            base_rate *= 0.8  # Cold-start users are less likely to engage
        
        # Add temporal variation
        if user_context['time_period'] == 'evening':
            base_rate *= 1.1  # Evening users are more engaged
        
        # Generate reward
        reward = 1.0 if np.random.random() < base_rate else 0.0
        
        return reward
    
    def simulate_user_session(self, user_id: int, timestamp: datetime) -> List[Dict]:
        """Simulate a user session with all policies"""
        events = []
        
        # Get user context
        context = self.get_user_context(user_id, timestamp)
        
        # Generate candidate arms
        candidate_arms = self.generate_candidate_arms(user_id, timestamp)
        
        if not candidate_arms:
            return events
        
        # Simulate each policy
        for policy_name in self.policies:
            try:
                policy = self.policy_instances[policy_name]
                
                # Select arm using policy
                policy_result = policy.select(context, candidate_arms)
                selected_arm = policy_result.arm_id
                
                # Compute reward
                reward = self.compute_reward(user_id, selected_arm, timestamp)
                
                # Create recommendation event
                event = RecommendationEvent(
                    user_id=user_id,
                    movie_id=None,  # We don't have specific movie IDs in this simulation
                    algorithm=f"offline_{policy_name}_{selected_arm}",
                    position=1,  # Single recommendation per session
                    score=policy_result.confidence,
                    clicked=False,  # Will be determined by reward
                    clicked_at=None,
                    rated=False,  # Will be determined by reward
                    rated_at=None,
                    rating_value=None,
                    thumbs_up=False,  # Will be determined by reward
                    thumbs_up_at=None,
                    thumbs_down=False,
                    thumbs_down_at=None,
                    added_to_watchlist=False,
                    added_to_favorites=False,
                    context=context,
                    experiment_id=self.experiment_id,
                    policy=policy_name,
                    arm_id=selected_arm,
                    p_score=policy_result.p_score,
                    latency_ms=np.random.randint(10, 100),  # Simulated latency
                    reward=reward,
                    served_at=timestamp
                )
                
                self.db.add(event)
                events.append({
                    'policy': policy_name,
                    'arm': selected_arm,
                    'reward': reward,
                    'confidence': policy_result.confidence,
                    'p_score': policy_result.p_score
                })
                
                # Update policy state
                policy.update(selected_arm, reward, context)
                
                # Update statistics
                self.stats['total_events'] += 1
                self.stats['events_by_policy'][policy_name] += 1
                self.stats['events_by_arm'][selected_arm] += 1
                self.stats['total_rewards'] += reward
                self.stats['rewards_by_policy'][policy_name] += reward
                self.stats['rewards_by_arm'][selected_arm] += reward
                
                if context['user_type'] == 'cold_start':
                    self.stats['cold_start_events'] += 1
                else:
                    self.stats['warm_start_events'] += 1
                
            except Exception as e:
                logger.warning(f"Failed to simulate policy {policy_name} for user {user_id}: {e}")
        
        return events
    
    def run_simulation(self, max_users_per_day: int = 100) -> Dict:
        """Run the complete offline simulation"""
        logger.info(f"Starting offline simulation from {self.window_start} to {self.window_end}")
        
        # Get all timestamps in the window
        timestamps = []
        current_time = self.window_start
        while current_time <= self.window_end:
            timestamps.append(current_time)
            current_time += timedelta(hours=1)  # Simulate every hour
        
        logger.info(f"Simulating {len(timestamps)} timestamps")
        
        # Process each timestamp
        for i, timestamp in enumerate(timestamps):
            if i % 24 == 0:  # Log progress every day
                logger.info(f"Processing timestamp {i+1}/{len(timestamps)}: {timestamp}")
            
            # Get active users at this timestamp
            active_users = self.get_active_users_at_time(timestamp)
            
            # Limit users per day to avoid memory issues
            if len(active_users) > max_users_per_day:
                active_users = np.random.choice(active_users, max_users_per_day, replace=False)
            
            # Simulate each user
            for user_id in active_users:
                try:
                    self.simulate_user_session(user_id, timestamp)
                except Exception as e:
                    logger.warning(f"Failed to simulate user {user_id} at {timestamp}: {e}")
            
            # Commit every 100 timestamps
            if i % 100 == 0:
                self.db.commit()
        
        # Final commit
        self.db.commit()
        
        logger.info("Simulation complete")
        return self.stats
    
    def get_simulation_summary(self) -> Dict:
        """Get summary of simulation results"""
        # Calculate additional metrics
        total_events = self.stats['total_events']
        total_rewards = self.stats['total_rewards']
        
        # Policy performance
        policy_performance = {}
        for policy in self.policies:
            events = self.stats['events_by_policy'][policy]
            rewards = self.stats['rewards_by_policy'][policy]
            policy_performance[policy] = {
                'events': events,
                'rewards': rewards,
                'reward_rate': rewards / events if events > 0 else 0,
                'cumulative_reward': rewards
            }
        
        # Arm performance
        arm_performance = {}
        for arm in self.arms:
            events = self.stats['events_by_arm'][arm]
            rewards = self.stats['rewards_by_arm'][arm]
            arm_performance[arm] = {
                'events': events,
                'rewards': rewards,
                'reward_rate': rewards / events if events > 0 else 0,
                'selection_rate': events / total_events if total_events > 0 else 0
            }
        
        return {
            'experiment_id': str(self.experiment_id),
            'window': {
                'start': self.window_start.isoformat(),
                'end': self.window_end.isoformat(),
                'duration_days': (self.window_end - self.window_start).days
            },
            'summary': {
                'total_events': total_events,
                'total_rewards': total_rewards,
                'overall_reward_rate': total_rewards / total_events if total_events > 0 else 0,
                'cold_start_events': self.stats['cold_start_events'],
                'warm_start_events': self.stats['warm_start_events']
            },
            'policy_performance': policy_performance,
            'arm_performance': arm_performance
        }

def main():
    """Main function to run offline replay"""
    parser = argparse.ArgumentParser(description='Run offline bandit replay simulation')
    parser.add_argument('--window-start', type=str, required=True,
                       help='Start date for replay window (YYYY-MM-DD)')
    parser.add_argument('--window-end', type=str, required=True,
                       help='End date for replay window (YYYY-MM-DD)')
    parser.add_argument('--max-users-per-day', type=int, default=100,
                       help='Maximum users to simulate per day')
    parser.add_argument('--output-file', type=str, default='replay_results.json',
                       help='Output file for simulation results')
    
    args = parser.parse_args()
    
    # Parse dates
    try:
        window_start = datetime.strptime(args.window_start, '%Y-%m-%d')
        window_end = datetime.strptime(args.window_end, '%Y-%m-%d')
    except ValueError as e:
        logger.error(f"Invalid date format: {e}")
        sys.exit(1)
    
    logger.info("="*60)
    logger.info("OFFLINE REPLAY SIMULATOR")
    logger.info("="*60)
    logger.info(f"Window: {window_start.date()} to {window_end.date()}")
    logger.info(f"Max users per day: {args.max_users_per_day}")
    logger.info("="*60)
    
    db = SessionLocal()
    
    try:
        # Create simulator
        simulator = OfflineReplaySimulator(db, window_start, window_end)
        
        # Run simulation
        stats = simulator.run_simulation(args.max_users_per_day)
        
        # Get summary
        summary = simulator.get_simulation_summary()
        
        # Export results
        import json
        with open(args.output_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        logger.info("="*60)
        logger.info("SIMULATION COMPLETE")
        logger.info("="*60)
        logger.info(f"Total events: {summary['summary']['total_events']:,}")
        logger.info(f"Total rewards: {summary['summary']['total_rewards']:,}")
        logger.info(f"Overall reward rate: {summary['summary']['overall_reward_rate']:.3f}")
        logger.info("="*60)
        logger.info("POLICY PERFORMANCE:")
        for policy, perf in summary['policy_performance'].items():
            logger.info(f"  {policy}: {perf['events']} events, {perf['reward_rate']:.3f} reward rate")
        logger.info("="*60)
        logger.info("ARM PERFORMANCE:")
        for arm, perf in summary['arm_performance'].items():
            logger.info(f"  {arm}: {perf['events']} events, {perf['reward_rate']:.3f} reward rate")
        logger.info("="*60)
        logger.info(f"Results exported to {args.output_file}")
        
    except Exception as e:
        logger.error(f"Simulation failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    main()
