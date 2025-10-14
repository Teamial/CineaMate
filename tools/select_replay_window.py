#!/usr/bin/env python3
"""
Replay Window Selection Script

Analyzes MovieLens 1M timestamp distribution to select the optimal 14-day window
for offline bandit replay. Considers factors like:
- User activity density
- Rating distribution
- Temporal continuity
- Cold-start user availability

Usage:
    python tools/select_replay_window.py
"""

import sys
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
import pandas as pd
import numpy as np

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from backend.database import SessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ReplayWindowSelector:
    """Select optimal 14-day window for offline replay"""
    
    def __init__(self, db: Session):
        self.db = db
        self.window_days = 14
        self.min_users_per_day = 50  # Minimum users needed per day
        self.min_ratings_per_day = 100  # Minimum ratings needed per day
    
    def analyze_timestamp_distribution(self) -> pd.DataFrame:
        """Analyze rating timestamp distribution"""
        logger.info("Analyzing timestamp distribution...")
        
        # Get daily statistics
        daily_stats = self.db.execute(text("""
            SELECT 
                DATE(timestamp) as date,
                COUNT(*) as rating_count,
                COUNT(DISTINCT ml_user_id) as unique_users,
                COUNT(DISTINCT ml_movie_id) as unique_movies,
                AVG(rating) as avg_rating,
                MIN(timestamp) as first_rating,
                MAX(timestamp) as last_rating
            FROM ml_ratings
            GROUP BY DATE(timestamp)
            ORDER BY date
        """)).fetchall()
        
        # Convert to DataFrame
        df = pd.DataFrame(daily_stats, columns=[
            'date', 'rating_count', 'unique_users', 'unique_movies', 
            'avg_rating', 'first_rating', 'last_rating'
        ])
        
        # Convert date column
        df['date'] = pd.to_datetime(df['date'])
        
        logger.info(f"Analyzed {len(df)} days of data")
        logger.info(f"Date range: {df['date'].min()} to {df['date'].max()}")
        
        return df
    
    def find_continuous_windows(self, df: pd.DataFrame) -> List[Tuple[datetime, datetime]]:
        """Find all possible 14-day continuous windows"""
        logger.info("Finding continuous 14-day windows...")
        
        windows = []
        start_date = df['date'].min()
        end_date = df['date'].max()
        
        current_date = start_date
        while current_date + timedelta(days=self.window_days) <= end_date:
            window_end = current_date + timedelta(days=self.window_days - 1)
            
            # Check if all days in window have data
            window_data = df[(df['date'] >= current_date) & (df['date'] <= window_end)]
            
            if len(window_data) == self.window_days:
                windows.append((current_date, window_end))
            
            current_date += timedelta(days=1)
        
        logger.info(f"Found {len(windows)} continuous 14-day windows")
        return windows
    
    def score_window(self, df: pd.DataFrame, start_date: datetime, end_date: datetime) -> Dict[str, float]:
        """Score a window based on various criteria"""
        
        window_data = df[(df['date'] >= start_date) & (df['date'] <= end_date)]
        
        if len(window_data) == 0:
            return {'score': 0, 'details': {}}
        
        # Calculate metrics
        total_ratings = window_data['rating_count'].sum()
        total_users = window_data['unique_users'].sum()
        total_movies = window_data['unique_movies'].sum()
        avg_rating = window_data['avg_rating'].mean()
        
        # User activity consistency (lower std = more consistent)
        user_consistency = 1.0 / (1.0 + window_data['unique_users'].std())
        
        # Rating volume consistency
        rating_consistency = 1.0 / (1.0 + window_data['rating_count'].std())
        
        # Average rating quality (higher is better)
        rating_quality = avg_rating / 5.0
        
        # User diversity (more unique users is better)
        user_diversity = min(total_users / 1000.0, 1.0)  # Cap at 1.0
        
        # Movie diversity (more unique movies is better)
        movie_diversity = min(total_movies / 500.0, 1.0)  # Cap at 1.0
        
        # Overall volume (more ratings is better, but not too much)
        volume_score = min(total_ratings / 10000.0, 1.0)  # Cap at 1.0
        
        # Calculate composite score
        score = (
            user_consistency * 0.25 +
            rating_consistency * 0.25 +
            rating_quality * 0.20 +
            user_diversity * 0.15 +
            movie_diversity * 0.10 +
            volume_score * 0.05
        )
        
        return {
            'score': score,
            'details': {
                'total_ratings': total_ratings,
                'total_users': total_users,
                'total_movies': total_movies,
                'avg_rating': avg_rating,
                'user_consistency': user_consistency,
                'rating_consistency': rating_consistency,
                'rating_quality': rating_quality,
                'user_diversity': user_diversity,
                'movie_diversity': movie_diversity,
                'volume_score': volume_score
            }
        }
    
    def analyze_cold_start_users(self, start_date: datetime, end_date: datetime) -> Dict[str, int]:
        """Analyze cold-start user availability in the window"""
        logger.info(f"Analyzing cold-start users for window {start_date} to {end_date}")
        
        # Get users who have ratings in the window
        window_users = self.db.execute(text("""
            SELECT DISTINCT ml_user_id
            FROM ml_ratings
            WHERE timestamp >= :start_date AND timestamp <= :end_date
        """), {
            'start_date': start_date,
            'end_date': end_date
        }).fetchall()
        
        window_user_ids = [row[0] for row in window_users]
        
        if not window_user_ids:
            return {'cold_start_users': 0, 'warm_start_users': 0, 'total_users': 0}
        
        # For each user, count their ratings before the window
        user_stats = []
        for user_id in window_user_ids:
            pre_window_ratings = self.db.execute(text("""
                SELECT COUNT(*) as rating_count
                FROM ml_ratings
                WHERE ml_user_id = :user_id AND timestamp < :start_date
            """), {
                'user_id': user_id,
                'start_date': start_date
            }).scalar()
            
            user_stats.append({
                'user_id': user_id,
                'pre_window_ratings': pre_window_ratings
            })
        
        # Categorize users
        cold_start_users = sum(1 for u in user_stats if u['pre_window_ratings'] < 5)
        warm_start_users = sum(1 for u in user_stats if u['pre_window_ratings'] >= 5)
        
        return {
            'cold_start_users': cold_start_users,
            'warm_start_users': warm_start_users,
            'total_users': len(window_user_ids)
        }
    
    def select_best_window(self, df: pd.DataFrame) -> Tuple[datetime, datetime, Dict]:
        """Select the best 14-day window"""
        logger.info("Selecting best replay window...")
        
        windows = self.find_continuous_windows(df)
        
        if not windows:
            raise ValueError("No continuous 14-day windows found in the data")
        
        best_window = None
        best_score = -1
        best_details = {}
        
        for start_date, end_date in windows:
            score_result = self.score_window(df, start_date, end_date)
            score = score_result['score']
            
            if score > best_score:
                best_score = score
                best_window = (start_date, end_date)
                best_details = score_result['details']
        
        if best_window is None:
            raise ValueError("No suitable window found")
        
        # Analyze cold-start users for the best window
        cold_start_analysis = self.analyze_cold_start_users(best_window[0], best_window[1])
        
        return best_window[0], best_window[1], {
            'score': best_score,
            'details': best_details,
            'cold_start_analysis': cold_start_analysis
        }
    
    def export_window_metadata(self, start_date: datetime, end_date: datetime, 
                             analysis: Dict, output_file: str):
        """Export window metadata to JSON file"""
        import json
        
        metadata = {
            'window': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'duration_days': self.window_days
            },
            'analysis': analysis,
            'created_at': datetime.utcnow().isoformat(),
            'dataset': 'movielens_1m',
            'purpose': 'offline_bandit_replay'
        }
        
        with open(output_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"Window metadata exported to {output_file}")
    
    def get_window_summary(self, start_date: datetime, end_date: datetime) -> Dict:
        """Get summary statistics for the selected window"""
        
        # Get window data
        window_data = self.db.execute(text("""
            SELECT 
                COUNT(*) as total_ratings,
                COUNT(DISTINCT ml_user_id) as unique_users,
                COUNT(DISTINCT ml_movie_id) as unique_movies,
                AVG(rating) as avg_rating,
                MIN(rating) as min_rating,
                MAX(rating) as max_rating,
                STDDEV(rating) as rating_std
            FROM ml_ratings
            WHERE timestamp >= :start_date AND timestamp <= :end_date
        """), {
            'start_date': start_date,
            'end_date': end_date
        }).fetchone()
        
        # Get daily breakdown
        daily_breakdown = self.db.execute(text("""
            SELECT 
                DATE(timestamp) as date,
                COUNT(*) as ratings,
                COUNT(DISTINCT ml_user_id) as users,
                AVG(rating) as avg_rating
            FROM ml_ratings
            WHERE timestamp >= :start_date AND timestamp <= :end_date
            GROUP BY DATE(timestamp)
            ORDER BY date
        """), {
            'start_date': start_date,
            'end_date': end_date
        }).fetchall()
        
        return {
            'window': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'duration_days': self.window_days
            },
            'summary': {
                'total_ratings': window_data.total_ratings,
                'unique_users': window_data.unique_users,
                'unique_movies': window_data.unique_movies,
                'avg_rating': round(window_data.avg_rating, 2),
                'min_rating': window_data.min_rating,
                'max_rating': window_data.max_rating,
                'rating_std': round(window_data.rating_std, 2)
            },
            'daily_breakdown': [
                {
                    'date': row.date.isoformat(),
                    'ratings': row.ratings,
                    'users': row.users,
                    'avg_rating': round(row.avg_rating, 2)
                }
                for row in daily_breakdown
            ]
        }

def main():
    """Main function to select replay window"""
    logger.info("="*60)
    logger.info("REPLAY WINDOW SELECTOR")
    logger.info("="*60)
    
    db = SessionLocal()
    selector = ReplayWindowSelector(db)
    
    try:
        # Analyze timestamp distribution
        df = selector.analyze_timestamp_distribution()
        
        # Select best window
        start_date, end_date, analysis = selector.select_best_window(df)
        
        # Get summary
        summary = selector.get_window_summary(start_date, end_date)
        
        # Export metadata
        output_file = "replay_window_metadata.json"
        selector.export_window_metadata(start_date, end_date, analysis, output_file)
        
        logger.info("="*60)
        logger.info("WINDOW SELECTION COMPLETE")
        logger.info("="*60)
        logger.info(f"Selected window: {start_date.date()} to {end_date.date()}")
        logger.info(f"Duration: {selector.window_days} days")
        logger.info(f"Score: {analysis['score']:.3f}")
        logger.info("="*60)
        logger.info("WINDOW STATISTICS:")
        logger.info(f"  Total ratings: {summary['summary']['total_ratings']:,}")
        logger.info(f"  Unique users: {summary['summary']['unique_users']:,}")
        logger.info(f"  Unique movies: {summary['summary']['unique_movies']:,}")
        logger.info(f"  Average rating: {summary['summary']['avg_rating']}")
        logger.info(f"  Rating range: {summary['summary']['min_rating']} - {summary['summary']['max_rating']}")
        logger.info("="*60)
        logger.info("COLD-START ANALYSIS:")
        logger.info(f"  Cold-start users: {analysis['cold_start_analysis']['cold_start_users']:,}")
        logger.info(f"  Warm-start users: {analysis['cold_start_analysis']['warm_start_users']:,}")
        logger.info(f"  Total users: {analysis['cold_start_analysis']['total_users']:,}")
        logger.info("="*60)
        logger.info("DETAILED SCORES:")
        for metric, value in analysis['details'].items():
            logger.info(f"  {metric}: {value:.3f}")
        logger.info("="*60)
        
        return start_date, end_date, analysis
        
    except Exception as e:
        logger.error(f"Window selection failed: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    main()
