#!/usr/bin/env python3
"""
Offline Metrics Evaluator

Evaluates bandit policies using comprehensive metrics including:
- CTR / Reward rate per policy
- Mean reward and cumulative reward
- Regret vs. best policy
- Cold-start performance breakdown
- Exploration rate and arm diversity
- IPS (Inverse Propensity Scoring) estimates
- Doubly Robust (DR) estimates
- Confidence intervals via bootstrap
- Temporal stability analysis

Usage:
    python tools/offline_evaluator.py --experiment-id <uuid>
"""

import sys
import os
import argparse
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
import numpy as np
import pandas as pd
from scipy import stats
import json

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from backend.database import SessionLocal
from backend.models import RecommendationEvent, Experiment

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OfflineEvaluator:
    """Evaluate offline bandit replay results"""
    
    def __init__(self, db: Session, experiment_id: uuid.UUID):
        self.db = db
        self.experiment_id = experiment_id
        self.policies = ['thompson', 'egreedy', 'ucb']
        self.arms = ['svd', 'embeddings', 'graph', 'item_cf', 'long_tail', 'serendipity']
        self.bootstrap_samples = 1000
        self.confidence_level = 0.95
    
    def load_experiment_data(self) -> pd.DataFrame:
        """Load all events for the experiment"""
        logger.info(f"Loading experiment data for {self.experiment_id}")
        
        events = self.db.execute(text("""
            SELECT 
                id, user_id, algorithm, position, score, context,
                experiment_id, policy, arm_id, p_score, latency_ms, reward, served_at
            FROM recommendation_events
            WHERE experiment_id = :experiment_id
            ORDER BY served_at
        """), {'experiment_id': self.experiment_id}).fetchall()
        
        if not events:
            raise ValueError(f"No events found for experiment {self.experiment_id}")
        
        # Convert to DataFrame
        df = pd.DataFrame(events, columns=[
            'id', 'user_id', 'algorithm', 'position', 'score', 'context',
            'experiment_id', 'policy', 'arm_id', 'p_score', 'latency_ms', 'reward', 'served_at'
        ])
        
        # Convert timestamp
        df['served_at'] = pd.to_datetime(df['served_at'])
        
        logger.info(f"Loaded {len(df)} events")
        return df
    
    def calculate_basic_metrics(self, df: pd.DataFrame) -> Dict[str, Dict]:
        """Calculate basic metrics per policy"""
        logger.info("Calculating basic metrics...")
        
        metrics = {}
        
        for policy in self.policies:
            policy_data = df[df['policy'] == policy]
            
            if len(policy_data) == 0:
                metrics[policy] = {
                    'total_events': 0,
                    'total_rewards': 0,
                    'reward_rate': 0,
                    'mean_reward': 0,
                    'cumulative_reward': 0
                }
                continue
            
            total_events = len(policy_data)
            total_rewards = policy_data['reward'].sum()
            reward_rate = total_rewards / total_events
            mean_reward = policy_data['reward'].mean()
            cumulative_reward = total_rewards
            
            metrics[policy] = {
                'total_events': total_events,
                'total_rewards': total_rewards,
                'reward_rate': reward_rate,
                'mean_reward': mean_reward,
                'cumulative_reward': cumulative_reward
            }
        
        return metrics
    
    def calculate_regret(self, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate regret vs. best policy"""
        logger.info("Calculating regret...")
        
        # Find the best policy (highest reward rate)
        policy_rewards = {}
        for policy in self.policies:
            policy_data = df[df['policy'] == policy]
            if len(policy_data) > 0:
                policy_rewards[policy] = policy_data['reward'].mean()
            else:
                policy_rewards[policy] = 0
        
        best_policy = max(policy_rewards, key=policy_rewards.get)
        best_reward = policy_rewards[best_policy]
        
        # Calculate regret for each policy
        regret = {}
        for policy in self.policies:
            policy_data = df[df['policy'] == policy]
            if len(policy_data) > 0:
                policy_reward = policy_data['reward'].mean()
                regret[policy] = best_reward - policy_reward
            else:
                regret[policy] = best_reward
        
        return regret
    
    def calculate_cold_start_metrics(self, df: pd.DataFrame) -> Dict[str, Dict]:
        """Calculate metrics for cold-start vs warm-start users"""
        logger.info("Calculating cold-start metrics...")
        
        # Determine user types based on context
        def get_user_type(context_str):
            if context_str and 'user_type' in context_str:
                try:
                    context = json.loads(context_str) if isinstance(context_str, str) else context_str
                    return context.get('user_type', 'regular')
                except:
                    return 'regular'
            return 'regular'
        
        df['user_type'] = df['context'].apply(get_user_type)
        
        cold_start_metrics = {}
        
        for policy in self.policies:
            policy_data = df[df['policy'] == policy]
            
            cold_start_data = policy_data[policy_data['user_type'] == 'cold_start']
            warm_start_data = policy_data[policy_data['user_type'] != 'cold_start']
            
            cold_start_metrics[policy] = {
                'cold_start': {
                    'events': len(cold_start_data),
                    'reward_rate': cold_start_data['reward'].mean() if len(cold_start_data) > 0 else 0,
                    'mean_reward': cold_start_data['reward'].mean() if len(cold_start_data) > 0 else 0
                },
                'warm_start': {
                    'events': len(warm_start_data),
                    'reward_rate': warm_start_data['reward'].mean() if len(warm_start_data) > 0 else 0,
                    'mean_reward': warm_start_data['reward'].mean() if len(warm_start_data) > 0 else 0
                }
            }
        
        return cold_start_metrics
    
    def calculate_exploration_metrics(self, df: pd.DataFrame) -> Dict[str, Dict]:
        """Calculate exploration and diversity metrics"""
        logger.info("Calculating exploration metrics...")
        
        exploration_metrics = {}
        
        for policy in self.policies:
            policy_data = df[df['policy'] == policy]
            
            if len(policy_data) == 0:
                exploration_metrics[policy] = {
                    'unique_arms': 0,
                    'exploration_rate': 0,
                    'arm_diversity': 0,
                    'arm_distribution': {}
                }
                continue
            
            # Count unique arms
            unique_arms = policy_data['arm_id'].nunique()
            
            # Calculate exploration rate (fraction of unique arms)
            exploration_rate = unique_arms / len(self.arms)
            
            # Calculate arm diversity (Shannon entropy)
            arm_counts = policy_data['arm_id'].value_counts()
            arm_probs = arm_counts / len(policy_data)
            arm_diversity = -np.sum(arm_probs * np.log2(arm_probs + 1e-10))
            
            # Arm distribution
            arm_distribution = arm_counts.to_dict()
            
            exploration_metrics[policy] = {
                'unique_arms': unique_arms,
                'exploration_rate': exploration_rate,
                'arm_diversity': arm_diversity,
                'arm_distribution': arm_distribution
            }
        
        return exploration_metrics
    
    def calculate_ips_estimates(self, df: pd.DataFrame) -> Dict[str, Dict]:
        """Calculate Inverse Propensity Scoring estimates"""
        logger.info("Calculating IPS estimates...")
        
        ips_estimates = {}
        
        for policy in self.policies:
            policy_data = df[df['policy'] == policy]
            
            if len(policy_data) == 0:
                ips_estimates[policy] = {
                    'ips_reward': 0,
                    'ips_variance': 0,
                    'ips_confidence_interval': (0, 0)
                }
                continue
            
            # Filter events with valid p_scores
            valid_data = policy_data[policy_data['p_score'].notna()]
            
            if len(valid_data) == 0:
                ips_estimates[policy] = {
                    'ips_reward': 0,
                    'ips_variance': 0,
                    'ips_confidence_interval': (0, 0)
                }
                continue
            
            # Calculate IPS estimate
            ips_weights = 1.0 / valid_data['p_score']
            ips_reward = np.mean(valid_data['reward'] * ips_weights)
            
            # Calculate variance
            ips_variance = np.var(valid_data['reward'] * ips_weights) / len(valid_data)
            
            # Bootstrap confidence interval
            bootstrap_samples = []
            for _ in range(self.bootstrap_samples):
                sample = valid_data.sample(n=len(valid_data), replace=True)
                sample_ips = np.mean(sample['reward'] * (1.0 / sample['p_score']))
                bootstrap_samples.append(sample_ips)
            
            alpha = 1 - self.confidence_level
            ci_lower = np.percentile(bootstrap_samples, 100 * alpha / 2)
            ci_upper = np.percentile(bootstrap_samples, 100 * (1 - alpha / 2))
            
            ips_estimates[policy] = {
                'ips_reward': ips_reward,
                'ips_variance': ips_variance,
                'ips_confidence_interval': (ci_lower, ci_upper)
            }
        
        return ips_estimates
    
    def calculate_doubly_robust_estimates(self, df: pd.DataFrame) -> Dict[str, Dict]:
        """Calculate Doubly Robust estimates"""
        logger.info("Calculating Doubly Robust estimates...")
        
        dr_estimates = {}
        
        for policy in self.policies:
            policy_data = df[df['policy'] == policy]
            
            if len(policy_data) == 0:
                dr_estimates[policy] = {
                    'dr_reward': 0,
                    'dr_variance': 0,
                    'dr_confidence_interval': (0, 0)
                }
                continue
            
            # Filter events with valid p_scores
            valid_data = policy_data[policy_data['p_score'].notna()]
            
            if len(valid_data) == 0:
                dr_estimates[policy] = {
                    'dr_reward': 0,
                    'dr_variance': 0,
                    'dr_confidence_interval': (0, 0)
                }
                continue
            
            # Simple model-based baseline (mean reward across all policies)
            baseline_reward = df['reward'].mean()
            
            # Calculate DR estimate
            ips_weights = 1.0 / valid_data['p_score']
            dr_reward = np.mean(
                baseline_reward + ips_weights * (valid_data['reward'] - baseline_reward)
            )
            
            # Calculate variance
            dr_variance = np.var(
                baseline_reward + ips_weights * (valid_data['reward'] - baseline_reward)
            ) / len(valid_data)
            
            # Bootstrap confidence interval
            bootstrap_samples = []
            for _ in range(self.bootstrap_samples):
                sample = valid_data.sample(n=len(valid_data), replace=True)
                sample_ips = 1.0 / sample['p_score']
                sample_dr = np.mean(
                    baseline_reward + sample_ips * (sample['reward'] - baseline_reward)
                )
                bootstrap_samples.append(sample_dr)
            
            alpha = 1 - self.confidence_level
            ci_lower = np.percentile(bootstrap_samples, 100 * alpha / 2)
            ci_upper = np.percentile(bootstrap_samples, 100 * (1 - alpha / 2))
            
            dr_estimates[policy] = {
                'dr_reward': dr_reward,
                'dr_variance': dr_variance,
                'dr_confidence_interval': (ci_lower, ci_upper)
            }
        
        return dr_estimates
    
    def calculate_temporal_stability(self, df: pd.DataFrame) -> Dict[str, Dict]:
        """Calculate temporal stability metrics"""
        logger.info("Calculating temporal stability...")
        
        # Group by day
        df['day'] = df['served_at'].dt.date
        
        temporal_metrics = {}
        
        for policy in self.policies:
            policy_data = df[df['policy'] == policy]
            
            if len(policy_data) == 0:
                temporal_metrics[policy] = {
                    'daily_reward_rates': [],
                    'reward_rate_std': 0,
                    'reward_rate_trend': 0
                }
                continue
            
            # Calculate daily reward rates
            daily_rates = policy_data.groupby('day')['reward'].mean()
            
            # Calculate stability metrics
            reward_rate_std = daily_rates.std()
            
            # Calculate trend (slope of linear regression)
            if len(daily_rates) > 1:
                x = np.arange(len(daily_rates))
                y = daily_rates.values
                slope, _, _, _, _ = stats.linregress(x, y)
                reward_rate_trend = slope
            else:
                reward_rate_trend = 0
            
            temporal_metrics[policy] = {
                'daily_reward_rates': daily_rates.tolist(),
                'reward_rate_std': reward_rate_std,
                'reward_rate_trend': reward_rate_trend
            }
        
        return temporal_metrics
    
    def calculate_arm_performance(self, df: pd.DataFrame) -> Dict[str, Dict]:
        """Calculate performance metrics per arm"""
        logger.info("Calculating arm performance...")
        
        arm_metrics = {}
        
        for arm in self.arms:
            arm_data = df[df['arm_id'] == arm]
            
            if len(arm_data) == 0:
                arm_metrics[arm] = {
                    'total_events': 0,
                    'total_rewards': 0,
                    'reward_rate': 0,
                    'mean_reward': 0,
                    'selection_rate': 0,
                    'policy_breakdown': {}
                }
                continue
            
            total_events = len(arm_data)
            total_rewards = arm_data['reward'].sum()
            reward_rate = total_rewards / total_events
            mean_reward = arm_data['reward'].mean()
            selection_rate = total_events / len(df)
            
            # Policy breakdown
            policy_breakdown = {}
            for policy in self.policies:
                policy_arm_data = arm_data[arm_data['policy'] == policy]
                policy_breakdown[policy] = {
                    'events': len(policy_arm_data),
                    'reward_rate': policy_arm_data['reward'].mean() if len(policy_arm_data) > 0 else 0
                }
            
            arm_metrics[arm] = {
                'total_events': total_events,
                'total_rewards': total_rewards,
                'reward_rate': reward_rate,
                'mean_reward': mean_reward,
                'selection_rate': selection_rate,
                'policy_breakdown': policy_breakdown
            }
        
        return arm_metrics
    
    def run_evaluation(self) -> Dict:
        """Run complete evaluation"""
        logger.info("Starting offline evaluation...")
        
        # Load data
        df = self.load_experiment_data()
        
        # Calculate all metrics
        results = {
            'experiment_id': str(self.experiment_id),
            'evaluation_timestamp': datetime.utcnow().isoformat(),
            'total_events': len(df),
            'evaluation_period': {
                'start': df['served_at'].min().isoformat(),
                'end': df['served_at'].max().isoformat()
            },
            'basic_metrics': self.calculate_basic_metrics(df),
            'regret': self.calculate_regret(df),
            'cold_start_metrics': self.calculate_cold_start_metrics(df),
            'exploration_metrics': self.calculate_exploration_metrics(df),
            'ips_estimates': self.calculate_ips_estimates(df),
            'doubly_robust_estimates': self.calculate_doubly_robust_estimates(df),
            'temporal_stability': self.calculate_temporal_stability(df),
            'arm_performance': self.calculate_arm_performance(df)
        }
        
        logger.info("Evaluation complete")
        return results
    
    def export_results(self, results: Dict, output_file: str):
        """Export results to JSON file"""
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"Results exported to {output_file}")
    
    def print_summary(self, results: Dict):
        """Print evaluation summary"""
        logger.info("="*60)
        logger.info("OFFLINE EVALUATION SUMMARY")
        logger.info("="*60)
        logger.info(f"Experiment ID: {results['experiment_id']}")
        logger.info(f"Total events: {results['total_events']:,}")
        logger.info(f"Evaluation period: {results['evaluation_period']['start']} to {results['evaluation_period']['end']}")
        logger.info("="*60)
        
        # Basic metrics
        logger.info("BASIC METRICS:")
        for policy, metrics in results['basic_metrics'].items():
            logger.info(f"  {policy}: {metrics['total_events']} events, {metrics['reward_rate']:.3f} reward rate")
        
        logger.info("="*60)
        
        # Regret
        logger.info("REGRET (vs. best policy):")
        for policy, regret in results['regret'].items():
            logger.info(f"  {policy}: {regret:.3f}")
        
        logger.info("="*60)
        
        # Cold-start performance
        logger.info("COLD-START PERFORMANCE:")
        for policy, metrics in results['cold_start_metrics'].items():
            cold_start = metrics['cold_start']
            warm_start = metrics['warm_start']
            logger.info(f"  {policy}:")
            logger.info(f"    Cold-start: {cold_start['events']} events, {cold_start['reward_rate']:.3f} reward rate")
            logger.info(f"    Warm-start: {warm_start['events']} events, {warm_start['reward_rate']:.3f} reward rate")
        
        logger.info("="*60)
        
        # Exploration metrics
        logger.info("EXPLORATION METRICS:")
        for policy, metrics in results['exploration_metrics'].items():
            logger.info(f"  {policy}: {metrics['unique_arms']} unique arms, {metrics['exploration_rate']:.3f} exploration rate")
        
        logger.info("="*60)
        
        # IPS estimates
        logger.info("IPS ESTIMATES:")
        for policy, estimates in results['ips_estimates'].items():
            ci = estimates['ips_confidence_interval']
            logger.info(f"  {policy}: {estimates['ips_reward']:.3f} [{ci[0]:.3f}, {ci[1]:.3f}]")
        
        logger.info("="*60)
        
        # Arm performance
        logger.info("ARM PERFORMANCE:")
        for arm, metrics in results['arm_performance'].items():
            logger.info(f"  {arm}: {metrics['total_events']} events, {metrics['reward_rate']:.3f} reward rate")
        
        logger.info("="*60)

def main():
    """Main function to run offline evaluation"""
    parser = argparse.ArgumentParser(description='Run offline bandit evaluation')
    parser.add_argument('--experiment-id', type=str, required=True,
                       help='Experiment ID to evaluate')
    parser.add_argument('--output-file', type=str, default='evaluation_results.json',
                       help='Output file for evaluation results')
    
    args = parser.parse_args()
    
    # Parse experiment ID
    try:
        experiment_id = uuid.UUID(args.experiment_id)
    except ValueError as e:
        logger.error(f"Invalid experiment ID: {e}")
        sys.exit(1)
    
    logger.info("="*60)
    logger.info("OFFLINE EVALUATOR")
    logger.info("="*60)
    logger.info(f"Experiment ID: {experiment_id}")
    logger.info("="*60)
    
    db = SessionLocal()
    
    try:
        # Create evaluator
        evaluator = OfflineEvaluator(db, experiment_id)
        
        # Run evaluation
        results = evaluator.run_evaluation()
        
        # Export results
        evaluator.export_results(results, args.output_file)
        
        # Print summary
        evaluator.print_summary(results)
        
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    main()
