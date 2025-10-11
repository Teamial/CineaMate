#!/usr/bin/env python3
"""
Database Monitoring and Progress Tracking Script
Monitors movie database growth and historical import progress
"""

import os
import sys
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, func
from sqlalchemy.orm import sessionmaker

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatabaseMonitor:
    """Monitor database growth and import progress"""
    
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.engine = create_engine(db_url)
        self.Session = sessionmaker(bind=self.engine)
    
    def get_database_status(self) -> Dict:
        """Get comprehensive database status"""
        with self.Session() as session:
            try:
                # Total movies
                total_movies = session.execute(text("SELECT COUNT(*) FROM movies")).scalar()
                
                # Movies with embeddings
                movies_with_embeddings = session.execute(
                    text("SELECT COUNT(*) FROM movies WHERE embedding IS NOT NULL")
                ).scalar()
                
                # Movies with full enrichment
                enriched_movies = session.execute(
                    text("SELECT COUNT(*) FROM movies WHERE \"cast\" IS NOT NULL")
                ).scalar()
                
                # Recent additions (last 24 hours)
                recent_movies = session.execute(
                    text("SELECT COUNT(*) FROM movies WHERE created_at > NOW() - INTERVAL '1 day'")
                ).scalar()
                
                # Movies added this week
                weekly_movies = session.execute(
                    text("SELECT COUNT(*) FROM movies WHERE created_at > NOW() - INTERVAL '7 days'")
                ).scalar()
                
                # Movies added this month
                monthly_movies = session.execute(
                    text("SELECT COUNT(*) FROM movies WHERE created_at > NOW() - INTERVAL '30 days'")
                ).scalar()
                
                # Database size
                db_size = session.execute(
                    text("SELECT pg_size_pretty(pg_total_relation_size('movies'))")
                ).scalar()
                
                # Genre distribution
                genre_stats = session.execute(text("""
                    SELECT 
                        jsonb_array_elements_text(genres::jsonb) as genre,
                        COUNT(*) as count
                    FROM movies 
                    WHERE genres IS NOT NULL
                    GROUP BY genre
                    ORDER BY count DESC
                    LIMIT 10
                """)).fetchall()
                
                # Year distribution
                year_stats = session.execute(text("""
                    SELECT 
                        EXTRACT(YEAR FROM release_date) as year,
                        COUNT(*) as count
                    FROM movies 
                    WHERE release_date IS NOT NULL
                    GROUP BY year
                    ORDER BY year DESC
                    LIMIT 10
                """)).fetchall()
                
                # Pipeline run history
                pipeline_runs = session.execute(text("""
                    SELECT 
                        run_date,
                        movies_processed,
                        status,
                        source_categories,
                        duration_seconds
                    FROM pipeline_runs
                    ORDER BY run_date DESC
                    LIMIT 10
                """)).fetchall()
                
                return {
                    'total_movies': total_movies,
                    'movies_with_embeddings': movies_with_embeddings,
                    'enriched_movies': enriched_movies,
                    'recent_movies_24h': recent_movies,
                    'recent_movies_week': weekly_movies,
                    'recent_movies_month': monthly_movies,
                    'database_size': db_size,
                    'embedding_coverage': (movies_with_embeddings / total_movies * 100) if total_movies > 0 else 0,
                    'enrichment_coverage': (enriched_movies / total_movies * 100) if total_movies > 0 else 0,
                    'top_genres': [{'genre': row[0], 'count': row[1]} for row in genre_stats],
                    'recent_years': [{'year': int(row[0]), 'count': row[1]} for row in year_stats],
                    'pipeline_runs': [
                        {
                            'date': row[0].isoformat() if row[0] else None,
                            'movies_processed': row[1],
                            'status': row[2],
                            'categories': row[3],
                            'duration': row[4]
                        } for row in pipeline_runs
                    ]
                }
                
            except Exception as e:
                logger.error(f"Error getting database status: {e}")
                return {}
    
    def get_import_progress(self, days_back: int = 30) -> Dict:
        """Get historical import progress over time"""
        with self.Session() as session:
            try:
                # Daily movie additions
                daily_additions = session.execute(text(f"""
                    SELECT 
                        DATE(created_at) as date,
                        COUNT(*) as movies_added
                    FROM movies 
                    WHERE created_at > NOW() - INTERVAL '{days_back} days'
                    GROUP BY DATE(created_at)
                    ORDER BY date DESC
                """)).fetchall()
                
                # Weekly movie additions
                weekly_additions = session.execute(text(f"""
                    SELECT 
                        DATE_TRUNC('week', created_at) as week,
                        COUNT(*) as movies_added
                    FROM movies 
                    WHERE created_at > NOW() - INTERVAL '{days_back} days'
                    GROUP BY DATE_TRUNC('week', created_at)
                    ORDER BY week DESC
                """)).fetchall()
                
                # Pipeline run success rate
                pipeline_stats = session.execute(text(f"""
                    SELECT 
                        status,
                        COUNT(*) as count,
                        AVG(movies_processed) as avg_movies,
                        AVG(duration_seconds) as avg_duration
                    FROM pipeline_runs
                    WHERE run_date > NOW() - INTERVAL '{days_back} days'
                    GROUP BY status
                """)).fetchall()
                
                return {
                    'daily_additions': [
                        {'date': row[0].isoformat(), 'movies_added': row[1]} 
                        for row in daily_additions
                    ],
                    'weekly_additions': [
                        {'week': row[0].isoformat(), 'movies_added': row[1]} 
                        for row in weekly_additions
                    ],
                    'pipeline_stats': [
                        {
                            'status': row[0],
                            'count': row[1],
                            'avg_movies': float(row[2]) if row[2] else 0,
                            'avg_duration': float(row[3]) if row[3] else 0
                        } for row in pipeline_stats
                    ]
                }
                
            except Exception as e:
                logger.error(f"Error getting import progress: {e}")
                return {}
    
    def print_status_report(self):
        """Print a comprehensive status report"""
        status = self.get_database_status()
        progress = self.get_import_progress()
        
        print("=" * 80)
        print("📊 MOVIE DATABASE STATUS REPORT")
        print("=" * 80)
        
        # Basic stats
        print(f"\n📈 Database Overview:")
        print(f"   Total Movies: {status.get('total_movies', 0):,}")
        print(f"   With Embeddings: {status.get('movies_with_embeddings', 0):,} ({status.get('embedding_coverage', 0):.1f}%)")
        print(f"   Fully Enriched: {status.get('enriched_movies', 0):,} ({status.get('enrichment_coverage', 0):.1f}%)")
        print(f"   Database Size: {status.get('database_size', 'Unknown')}")
        
        # Recent activity
        print(f"\n🆕 Recent Activity:")
        print(f"   Last 24 hours: {status.get('recent_movies_24h', 0):,} movies")
        print(f"   Last 7 days: {status.get('recent_movies_week', 0):,} movies")
        print(f"   Last 30 days: {status.get('recent_movies_month', 0):,} movies")
        
        # Top genres
        print(f"\n🎭 Top Genres:")
        for genre_info in status.get('top_genres', [])[:5]:
            print(f"   {genre_info['genre']}: {genre_info['count']:,} movies")
        
        # Recent years
        print(f"\n📅 Recent Years:")
        for year_info in status.get('recent_years', [])[:5]:
            print(f"   {year_info['year']}: {year_info['count']:,} movies")
        
        # Pipeline runs
        print(f"\n🔄 Recent Pipeline Runs:")
        for run in status.get('pipeline_runs', [])[:5]:
            date_str = run['date'][:10] if run['date'] else 'Unknown'
            print(f"   {date_str}: {run['movies_processed']} movies ({run['status']}) - {run['duration']:.1f}s")
        
        # Import progress
        if progress.get('daily_additions'):
            print(f"\n📊 Daily Import Progress (Last 7 days):")
            for day in progress['daily_additions'][:7]:
                print(f"   {day['date']}: {day['movies_added']} movies")
        
        print("=" * 80)
    
    def monitor_growth(self, interval_minutes: int = 60, duration_hours: int = 24):
        """Monitor database growth over time"""
        logger.info(f"🔍 Starting growth monitoring for {duration_hours} hours (checking every {interval_minutes} minutes)")
        
        start_time = time.time()
        end_time = start_time + (duration_hours * 3600)
        initial_count = self.get_database_status().get('total_movies', 0)
        
        logger.info(f"📊 Initial movie count: {initial_count:,}")
        
        while time.time() < end_time:
            try:
                status = self.get_database_status()
                current_count = status.get('total_movies', 0)
                growth = current_count - initial_count
                
                logger.info(f"📈 Current movies: {current_count:,} (+{growth:,} since start)")
                logger.info(f"🆕 Recent additions: {status.get('recent_movies_24h', 0)} in last 24h")
                
                # Sleep until next check
                time.sleep(interval_minutes * 60)
                
            except KeyboardInterrupt:
                logger.info("⏹️  Monitoring stopped by user")
                break
            except Exception as e:
                logger.error(f"❌ Monitoring error: {e}")
                time.sleep(60)  # Wait 1 minute before retrying
        
        final_count = self.get_database_status().get('total_movies', 0)
        total_growth = final_count - initial_count
        
        logger.info(f"✅ Monitoring complete!")
        logger.info(f"📊 Final movie count: {final_count:,}")
        logger.info(f"📈 Total growth: +{total_growth:,} movies")
    
    def estimate_completion_time(self, target_movies: int) -> Dict:
        """Estimate time to reach target movie count"""
        status = self.get_database_status()
        current_count = status.get('total_movies', 0)
        recent_growth = status.get('recent_movies_month', 0)
        
        if recent_growth == 0:
            return {'error': 'No recent growth data available'}
        
        movies_needed = target_movies - current_count
        if movies_needed <= 0:
            return {'message': 'Target already reached', 'current': current_count}
        
        # Estimate based on monthly growth
        days_to_complete = (movies_needed / recent_growth) * 30
        
        return {
            'current_movies': current_count,
            'target_movies': target_movies,
            'movies_needed': movies_needed,
            'recent_monthly_growth': recent_growth,
            'estimated_days': days_to_complete,
            'estimated_date': (datetime.now() + timedelta(days=days_to_complete)).isoformat()
        }


def main():
    """Main function for command-line usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Database Monitoring Tool')
    parser.add_argument('--status', action='store_true', help='Show current status')
    parser.add_argument('--monitor', action='store_true', help='Monitor growth over time')
    parser.add_argument('--interval', type=int, default=60, help='Monitoring interval in minutes')
    parser.add_argument('--duration', type=int, default=24, help='Monitoring duration in hours')
    parser.add_argument('--estimate', type=int, help='Estimate time to reach target movie count')
    
    args = parser.parse_args()
    
    # Get database URL
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        logger.error("❌ DATABASE_URL not found in environment variables")
        sys.exit(1)
    
    # Initialize monitor
    monitor = DatabaseMonitor(db_url)
    
    try:
        if args.status:
            monitor.print_status_report()
        elif args.monitor:
            monitor.monitor_growth(args.interval, args.duration)
        elif args.estimate:
            result = monitor.estimate_completion_time(args.estimate)
            if 'error' in result:
                print(f"❌ {result['error']}")
            elif 'message' in result:
                print(f"✅ {result['message']}")
            else:
                print(f"📊 Completion Estimate:")
                print(f"   Current: {result['current_movies']:,} movies")
                print(f"   Target: {result['target_movies']:,} movies")
                print(f"   Needed: {result['movies_needed']:,} movies")
                print(f"   Monthly Growth: {result['recent_monthly_growth']:,} movies")
                print(f"   Estimated Days: {result['estimated_days']:.1f}")
                print(f"   Estimated Date: {result['estimated_date'][:10]}")
        else:
            parser.print_help()
            
    except KeyboardInterrupt:
        logger.info("⏹️  Operation interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
