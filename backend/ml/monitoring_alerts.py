#!/usr/bin/env python3
"""
Monitoring and Alerting System

Monitors recommendation system health and sends alerts when:
- Diversity drops below threshold
- Quality degrades
- Bandit becomes imbalanced
- Model training fails
"""

import sys
import os

# Add project root to path for imports
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from backend.database import SessionLocal
from backend.models import RecommendationEvent, Movie
from backend.ml.evaluator import RecommendationEvaluator
import logging
from datetime import datetime, timedelta
import json
from typing import Dict, List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MonitoringSystem:
    """Monitoring and alerting for recommendation system"""
    
    def __init__(self):
        self.db = SessionLocal()
        self.evaluator = RecommendationEvaluator(self.db)
        
        # Alert thresholds
        self.thresholds = {
            'min_long_tail_rate': 0.20,  # 20% minimum long-tail recommendations
            'min_avg_rating': 3.5,  # Minimum average rating
            'max_algorithm_dominance': 0.70,  # Max 70% for single algorithm
            'min_ctr': 0.10,  # Minimum 10% CTR
            'min_genre_diversity': 0.30  # Minimum 30% genre diversity
        }
        
        self.alerts = []
    
    def check_all_metrics(self, days: int = 7) -> Dict:
        """Check all monitoring metrics"""
        
        logger.info(f"Running monitoring checks for last {days} days...")
        
        results = {
            'timestamp': datetime.utcnow().isoformat(),
            'period_days': days,
            'checks': {},
            'alerts': [],
            'overall_status': 'healthy'
        }
        
        # Check 1: Diversity metrics
        diversity_check = self._check_diversity(days)
        results['checks']['diversity'] = diversity_check
        if diversity_check['status'] != 'ok':
            results['alerts'].extend(diversity_check.get('alerts', []))
        
        # Check 2: Quality metrics
        quality_check = self._check_quality(days)
        results['checks']['quality'] = quality_check
        if quality_check['status'] != 'ok':
            results['alerts'].extend(quality_check.get('alerts', []))
        
        # Check 3: Algorithm balance
        balance_check = self._check_algorithm_balance(days)
        results['checks']['algorithm_balance'] = balance_check
        if balance_check['status'] != 'ok':
            results['alerts'].extend(balance_check.get('alerts', []))
        
        # Check 4: Engagement metrics
        engagement_check = self._check_engagement(days)
        results['checks']['engagement'] = engagement_check
        if engagement_check['status'] != 'ok':
            results['alerts'].extend(engagement_check.get('alerts', []))
        
        # Determine overall status
        if results['alerts']:
            if any('critical' in alert['severity'] for alert in results['alerts']):
                results['overall_status'] = 'critical'
            else:
                results['overall_status'] = 'warning'
        
        return results
    
    def _check_diversity(self, days: int) -> Dict:
        """Check diversity metrics"""
        
        cutoff = datetime.utcnow() - timedelta(days=days)
        events = self.db.query(RecommendationEvent).filter(
            RecommendationEvent.created_at >= cutoff
        ).all()
        
        if not events:
            return {'status': 'no_data', 'message': 'No recommendation events found'}
        
        # Get recommended movies
        movie_ids = list(set(e.movie_id for e in events))
        movies = self.db.query(Movie).filter(Movie.id.in_(movie_ids)).all()
        
        # Calculate metrics
        diversity_metrics = self.evaluator.calculate_diversity_metrics(movies)
        
        alerts = []
        
        # Check long-tail rate
        long_tail_rate = diversity_metrics['long_tail_percentage']
        if long_tail_rate < self.thresholds['min_long_tail_rate']:
            alerts.append({
                'severity': 'warning',
                'metric': 'long_tail_rate',
                'value': long_tail_rate,
                'threshold': self.thresholds['min_long_tail_rate'],
                'message': f"Long-tail recommendation rate ({long_tail_rate:.2%}) below threshold ({self.thresholds['min_long_tail_rate']:.2%})"
            })
        
        # Check genre diversity
        genre_diversity = diversity_metrics['genre_diversity']
        if genre_diversity < self.thresholds['min_genre_diversity']:
            alerts.append({
                'severity': 'warning',
                'metric': 'genre_diversity',
                'value': genre_diversity,
                'threshold': self.thresholds['min_genre_diversity'],
                'message': f"Genre diversity ({genre_diversity:.2%}) below threshold ({self.thresholds['min_genre_diversity']:.2%})"
            })
        
        return {
            'status': 'ok' if not alerts else 'warning',
            'metrics': diversity_metrics,
            'alerts': alerts
        }
    
    def _check_quality(self, days: int) -> Dict:
        """Check quality metrics"""
        
        metrics = self.evaluator.evaluate_online_metrics(days=days)
        
        alerts = []
        
        # Check average rating
        avg_rating = metrics.get('avg_rating', 0)
        if avg_rating > 0 and avg_rating < self.thresholds['min_avg_rating']:
            alerts.append({
                'severity': 'critical',
                'metric': 'avg_rating',
                'value': avg_rating,
                'threshold': self.thresholds['min_avg_rating'],
                'message': f"Average rating ({avg_rating:.2f}) below threshold ({self.thresholds['min_avg_rating']:.2f})"
            })
        
        return {
            'status': 'ok' if not alerts else 'critical',
            'metrics': metrics,
            'alerts': alerts
        }
    
    def _check_algorithm_balance(self, days: int) -> Dict:
        """Check if algorithms are balanced"""
        
        cutoff = datetime.utcnow() - timedelta(days=days)
        events = self.db.query(RecommendationEvent).filter(
            RecommendationEvent.created_at >= cutoff
        ).all()
        
        if not events:
            return {'status': 'no_data'}
        
        # Count algorithm usage
        algorithm_counts = {}
        for event in events:
            algo = event.algorithm or 'unknown'
            algorithm_counts[algo] = algorithm_counts.get(algo, 0) + 1
        
        total = len(events)
        algorithm_rates = {algo: count / total for algo, count in algorithm_counts.items()}
        
        alerts = []
        
        # Check for dominance
        for algo, rate in algorithm_rates.items():
            if rate > self.thresholds['max_algorithm_dominance']:
                alerts.append({
                    'severity': 'warning',
                    'metric': 'algorithm_dominance',
                    'value': rate,
                    'threshold': self.thresholds['max_algorithm_dominance'],
                    'message': f"Algorithm '{algo}' dominates with {rate:.2%} of recommendations (threshold: {self.thresholds['max_algorithm_dominance']:.2%})"
                })
        
        return {
            'status': 'ok' if not alerts else 'warning',
            'algorithm_rates': algorithm_rates,
            'alerts': alerts
        }
    
    def _check_engagement(self, days: int) -> Dict:
        """Check engagement metrics"""
        
        metrics = self.evaluator.evaluate_online_metrics(days=days)
        
        alerts = []
        
        # Check CTR
        ctr = metrics.get('ctr', 0)
        if ctr < self.thresholds['min_ctr']:
            alerts.append({
                'severity': 'warning',
                'metric': 'ctr',
                'value': ctr,
                'threshold': self.thresholds['min_ctr'],
                'message': f"CTR ({ctr:.2%}) below threshold ({self.thresholds['min_ctr']:.2%})"
            })
        
        return {
            'status': 'ok' if not alerts else 'warning',
            'metrics': metrics,
            'alerts': alerts
        }
    
    def print_monitoring_report(self, results: Dict):
        """Print formatted monitoring report"""
        
        print("\n" + "="*60)
        print("RECOMMENDATION SYSTEM MONITORING REPORT")
        print("="*60)
        
        print(f"\nTimestamp: {results['timestamp']}")
        print(f"Period: Last {results['period_days']} days")
        print(f"Overall Status: {results['overall_status'].upper()}")
        
        # Print checks
        print("\n📊 Health Checks:")
        for check_name, check_data in results['checks'].items():
            status_icon = "✅" if check_data['status'] == 'ok' else "⚠️" if check_data['status'] == 'warning' else "❌"
            print(f"\n{status_icon} {check_name.replace('_', ' ').title()}: {check_data['status'].upper()}")
            
            if 'metrics' in check_data:
                print("   Metrics:")
                for metric, value in check_data['metrics'].items():
                    if isinstance(value, (int, float)):
                        print(f"      • {metric}: {value:.3f}" if isinstance(value, float) else f"      • {metric}: {value}")
        
        # Print alerts
        if results['alerts']:
            print("\n🚨 ALERTS:")
            for alert in results['alerts']:
                severity_icon = "🔴" if alert['severity'] == 'critical' else "🟡"
                print(f"\n{severity_icon} {alert['severity'].upper()}: {alert['message']}")
                print(f"   Metric: {alert['metric']}")
                print(f"   Current: {alert['value']:.3f}")
                print(f"   Threshold: {alert['threshold']:.3f}")
        else:
            print("\n✅ No alerts - system is healthy!")
        
        print("\n" + "="*60)
    
    def close(self):
        """Close database connection"""
        self.db.close()


def run_monitoring_check():
    """Run monitoring check and print report"""
    
    monitor = MonitoringSystem()
    
    try:
        results = monitor.check_all_metrics(days=7)
        monitor.print_monitoring_report(results)
        
        # Save results to file
        output_file = 'monitoring_report.json'
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n💾 Report saved to: {output_file}")
        
    finally:
        monitor.close()


if __name__ == "__main__":
    run_monitoring_check()

