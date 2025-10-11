#!/usr/bin/env python3
"""
Deploy A/B Test: Baseline vs Bandit-Optimized Recommendations

This script sets up and monitors the first A/B test comparing:
- Control: Traditional hybrid recommendations
- Treatment: Bandit-optimized contextual recommendations
"""

import sys
import os

# Add project root to path for imports
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from backend.database import SessionLocal
from backend.models import RecommendationEvent
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def deploy_ab_test():
    """Deploy the baseline vs bandit A/B test"""
    
    logger.info("="*60)
    logger.info("DEPLOYING A/B TEST: Baseline vs Bandit-Optimized")
    logger.info("="*60)
    
    experiment_config = {
        'experiment_id': 'bandit_vs_baseline',
        'name': 'Bandit-Optimized Recommendations vs Baseline',
        'description': 'Compare traditional hybrid recommendations with bandit-optimized contextual recommendations',
        'variants': {
            'control': {
                'name': 'baseline',
                'description': 'Traditional hybrid recommendations (SVD + Item-CF + Content)',
                'traffic_percentage': 50
            },
            'treatment': {
                'name': 'bandit',
                'description': 'Bandit-optimized contextual recommendations with diversity boost',
                'traffic_percentage': 50
            }
        },
        'success_metrics': [
            'CTR (Click-Through Rate)',
            'Average Rating',
            'Long-tail Discovery Rate',
            'Anime Click Rate',
            'Genre Diversity'
        ],
        'duration_days': 14,
        'min_sample_size': 1000
    }
    
    print("\n📊 Experiment Configuration:")
    print(f"   ID: {experiment_config['experiment_id']}")
    print(f"   Name: {experiment_config['name']}")
    print(f"   Duration: {experiment_config['duration_days']} days")
    print(f"   Min Sample Size: {experiment_config['min_sample_size']} per variant")
    
    print("\n🎯 Variants:")
    for variant_id, variant in experiment_config['variants'].items():
        print(f"   {variant_id.upper()}: {variant['name']}")
        print(f"      → {variant['description']}")
        print(f"      → Traffic: {variant['traffic_percentage']}%")
    
    print("\n📈 Success Metrics:")
    for metric in experiment_config['success_metrics']:
        print(f"   • {metric}")
    
    print("\n✅ A/B Test Configuration Complete!")
    print("\nNext Steps:")
    print("1. The experiment is now active in the recommendation endpoint")
    print("2. Users will be automatically assigned to variants using consistent hashing")
    print("3. Monitor results with: GET /analytics/experiments")
    print("4. Check significance after 7 days minimum")
    print("5. Stop experiment when statistical significance achieved (p < 0.05)")
    
    print("\n📊 Monitoring Commands:")
    print("   • Check experiment status: curl http://localhost:8000/analytics/experiments")
    print("   • View diversity metrics: curl http://localhost:8000/analytics/diversity-metrics")
    print("   • Algorithm performance: curl http://localhost:8000/analytics/algorithm-performance")
    
    print("\n" + "="*60)
    
    return experiment_config


def check_experiment_status():
    """Check current status of the A/B test"""
    
    logger.info("Checking experiment status...")
    
    try:
        db = SessionLocal()
        
        # Get events from last 7 days
        cutoff_date = datetime.utcnow() - timedelta(days=7)
        
        events = db.query(RecommendationEvent).filter(
            RecommendationEvent.created_at >= cutoff_date,
            RecommendationEvent.experiment_id == 'bandit_vs_baseline'
        ).all()
        
        if not events:
            print("\n⚠️  No experiment data found yet")
            print("   Wait for users to receive recommendations")
            return
        
        # Group by variant
        control_events = [e for e in events if e.variant == 'baseline']
        treatment_events = [e for e in events if e.variant == 'bandit']
        
        print("\n📊 Experiment Status:")
        print(f"   Total Events: {len(events)}")
        print(f"   Control (Baseline): {len(control_events)} events")
        print(f"   Treatment (Bandit): {len(treatment_events)} events")
        
        # Calculate basic metrics
        if control_events:
            control_ctr = sum(1 for e in control_events if e.clicked) / len(control_events)
            control_ratings = [e.rating_value for e in control_events if e.rated and e.rating_value]
            control_avg_rating = sum(control_ratings) / len(control_ratings) if control_ratings else 0
            
            print(f"\n   Control Metrics:")
            print(f"      CTR: {control_ctr:.2%}")
            print(f"      Avg Rating: {control_avg_rating:.2f}")
        
        if treatment_events:
            treatment_ctr = sum(1 for e in treatment_events if e.clicked) / len(treatment_events)
            treatment_ratings = [e.rating_value for e in treatment_events if e.rated and e.rating_value]
            treatment_avg_rating = sum(treatment_ratings) / len(treatment_ratings) if treatment_ratings else 0
            
            print(f"\n   Treatment Metrics:")
            print(f"      CTR: {treatment_ctr:.2%}")
            print(f"      Avg Rating: {treatment_avg_rating:.2f}")
            
            if control_events:
                improvement = ((treatment_ctr - control_ctr) / control_ctr * 100) if control_ctr > 0 else 0
                print(f"\n   📈 Improvement: {improvement:+.1f}%")
        
        db.close()
        
    except Exception as e:
        logger.error(f"Error checking experiment status: {e}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="A/B Test Deployment and Monitoring")
    parser.add_argument("--deploy", action="store_true", help="Deploy the A/B test")
    parser.add_argument("--status", action="store_true", help="Check experiment status")
    
    args = parser.parse_args()
    
    if args.deploy:
        config = deploy_ab_test()
    elif args.status:
        check_experiment_status()
    else:
        # Default: deploy
        config = deploy_ab_test()

