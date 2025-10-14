"""
Scheduler service for automated movie pipeline runs
"""
import os
import sys
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv

# Set up logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add project root to sys.path to import root-level modules in container
# In the container, we're running from /app/backend/, so we need to go up one level to /app/
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)
    
# Also add the tools directory specifically
TOOLS_PATH = os.path.join(PROJECT_ROOT, 'tools')
if TOOLS_PATH not in sys.path:
    sys.path.append(TOOLS_PATH)

# Import pipeline from tools directory
try:
    # Try direct import first
    from tools.movie_pipeline import MovieETLPipeline
    logger.info("✅ MovieETLPipeline imported successfully")
except ImportError:
    try:
        # Fallback: import directly from file
        import importlib.util
        movie_pipeline_path = os.path.join(TOOLS_PATH, 'movie_pipeline.py')
        spec = importlib.util.spec_from_file_location("movie_pipeline", movie_pipeline_path)
        movie_pipeline_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(movie_pipeline_module)
        MovieETLPipeline = movie_pipeline_module.MovieETLPipeline
        logger.info("✅ MovieETLPipeline imported successfully (direct file import)")
    except Exception as e:
        logger.warning(f"⚠️ Could not import MovieETLPipeline: {e}")
        MovieETLPipeline = None

# Optional historical importer; only schedule related jobs if import succeeds
try:
    # Try direct import first
    from tools.historical_movie_import import HistoricalMovieImporter
    HAS_HISTORICAL_IMPORTER = True
    logger.info("✅ HistoricalMovieImporter imported successfully")
except ImportError:
    try:
        # Fallback: import directly from file
        import importlib.util
        historical_import_path = os.path.join(TOOLS_PATH, 'historical_movie_import.py')
        spec = importlib.util.spec_from_file_location("historical_movie_import", historical_import_path)
        historical_import_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(historical_import_module)
        HistoricalMovieImporter = historical_import_module.HistoricalMovieImporter
        HAS_HISTORICAL_IMPORTER = True
        logger.info("✅ HistoricalMovieImporter imported successfully (direct file import)")
    except Exception as e:
        logger.warning(f"⚠️ Could not import HistoricalMovieImporter: {e}")
        HistoricalMovieImporter = None  # type: ignore
        HAS_HISTORICAL_IMPORTER = False

load_dotenv()


class PipelineScheduler:
    """Scheduler for automated movie data pipeline runs"""
    
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.tmdb_api_key = os.getenv('TMDB_API_KEY')
        self.database_url = os.getenv('DATABASE_URL')
        
        if not self.tmdb_api_key:
            raise ValueError("TMDB_API_KEY not found in environment")
        if not self.database_url:
            raise ValueError("DATABASE_URL not found in environment")
        
        self.pipeline = MovieETLPipeline(self.tmdb_api_key, self.database_url)
        self.historical_importer = HistoricalMovieImporter(self.tmdb_api_key, self.database_url) if HAS_HISTORICAL_IMPORTER else None
        self._setup_jobs()
    
    def _setup_jobs(self):
        """Setup scheduled jobs"""
        
        # Quick update: Every 6 hours (popular + trending)
        # Start 6 hours from now to avoid immediate execution on startup
        start_date = datetime.now() + timedelta(hours=6)
        self.scheduler.add_job(
            func=self._quick_update,
            trigger=IntervalTrigger(hours=6, start_date=start_date),
            id='quick_update',
            name='Quick Update (Popular + Trending)',
            replace_existing=True,
            max_instances=1
        )
        logger.info("✓ Scheduled: Quick update every 6 hours (first run in 6 hours)")
        
        # Daily update: Every day at 3 AM (all categories, no enrichment)
        self.scheduler.add_job(
            func=self._daily_update,
            trigger=CronTrigger(hour=3, minute=0),
            id='daily_update',
            name='Daily Update (All Categories)',
            replace_existing=True,
            max_instances=1
        )
        logger.info("✓ Scheduled: Daily update at 3:00 AM")
        
        # Weekly enrichment: Every Sunday at 2 AM (with full enrichment)
        self.scheduler.add_job(
            func=self._weekly_enrichment,
            trigger=CronTrigger(day_of_week='sun', hour=2, minute=0),
            id='weekly_enrichment',
            name='Weekly Enrichment (Full Data)',
            replace_existing=True,
            max_instances=1
        )
        logger.info("✓ Scheduled: Weekly enrichment on Sundays at 2:00 AM")
        
        # Embedding refresh: Every day at 4 AM (generate embeddings for new movies)
        self.scheduler.add_job(
            func=self._refresh_embeddings,
            trigger=CronTrigger(hour=4, minute=0),
            id='embedding_refresh',
            name='Embedding Refresh (New Movies)',
            replace_existing=True,
            max_instances=1
        )
        logger.info("✓ Scheduled: Embedding refresh daily at 4:00 AM")
        
        # Monitoring: Every day at 9 AM (check system health)
        self.scheduler.add_job(
            func=self._run_monitoring,
            trigger=CronTrigger(hour=9, minute=0),
            id='daily_monitoring',
            name='Daily System Monitoring',
            replace_existing=True,
            max_instances=1
        )
        logger.info("✓ Scheduled: System monitoring daily at 9:00 AM")
        
        # Historical jobs (optional)
        if HAS_HISTORICAL_IMPORTER and self.historical_importer is not None:
            self.scheduler.add_job(
                func=self._historical_recent_update,
                trigger=CronTrigger(day_of_week='mon', hour=1, minute=0),
                id='historical_recent',
                name='Historical Recent Update (Last 30 Days)',
                replace_existing=True,
                max_instances=1
            )
            logger.info("✓ Scheduled: Historical recent update on Mondays at 1:00 AM")

            self.scheduler.add_job(
                func=self._historical_batch_import,
                trigger=CronTrigger(day=1, day_of_week='sun', hour=0, minute=0),
                id='historical_batch',
                name='Historical Batch Import (5 Years)',
                replace_existing=True,
                max_instances=1
            )
            logger.info("✓ Scheduled: Historical batch import on first Sunday of month at 12:00 AM")
        else:
            logger.info("ℹ️ Historical importer not available; skipping historical jobs")
    
    def _quick_update(self):
        """Quick update with popular and trending movies"""
        logger.info("🚀 Starting quick update...")
        try:
            self.pipeline.run_quick_update()
            logger.info("✅ Quick update completed successfully")
        except Exception as e:
            logger.error(f"❌ Quick update failed: {e}", exc_info=True)
    
    def _daily_update(self):
        """Daily update with all categories"""
        logger.info("🚀 Starting daily update...")
        try:
            self.pipeline.run(
                categories=['popular', 'top_rated', 'upcoming', 'now_playing'],
                pages_per_category=5,
                include_trending=True,
                enrich_data=False,
                incremental=True
            )
            logger.info("✅ Daily update completed successfully")
        except Exception as e:
            logger.error(f"❌ Daily update failed: {e}", exc_info=True)
    
    def _weekly_enrichment(self):
        """Weekly enrichment with detailed data"""
        logger.info("🚀 Starting weekly enrichment...")
        try:
            self.pipeline.run_full_enrichment()
            logger.info("✅ Weekly enrichment completed successfully")
        except Exception as e:
            logger.error(f"❌ Weekly enrichment failed: {e}", exc_info=True)
    
    def _refresh_embeddings(self):
        """Refresh embeddings for new movies"""
        logger.info("🚀 Starting embedding refresh...")
        try:
            # Check if embeddings are available
            try:
                from generate_embeddings import EmbeddingGenerator, EMBEDDINGS_AVAILABLE
                from database import SessionLocal
                
                if not EMBEDDINGS_AVAILABLE:
                    logger.warning("⚠️  Embeddings not available, skipping refresh")
                    return
                
                # Generate embeddings for new movies
                db = SessionLocal()
                try:
                    generator = EmbeddingGenerator(db)
                    
                    # Get stats before
                    stats_before = generator.get_embedding_stats()
                    logger.info(f"Before: {stats_before['movies_without_embeddings']} movies need embeddings")
                    
                    if stats_before['movies_without_embeddings'] > 0:
                        # Generate embeddings (only for movies without embeddings)
                        generator.generate_all_embeddings(batch_size=100, force_regenerate=False)
                        
                        # Get stats after
                        stats_after = generator.get_embedding_stats()
                        logger.info(f"After: {stats_after['coverage_percentage']:.1f}% coverage")
                        logger.info(f"✅ Embedding refresh completed successfully")
                    else:
                        logger.info("✅ All movies already have embeddings")
                
                finally:
                    db.close()
                    
            except ImportError as e:
                logger.warning(f"⚠️  Embedding generator not available: {e}")
                
        except Exception as e:
            logger.error(f"❌ Embedding refresh failed: {e}", exc_info=True)
    
    def _run_monitoring(self):
        """Run system health monitoring and alerting"""
        logger.info("🔍 Starting system monitoring...")
        try:
            from ml.monitoring_alerts import MonitoringSystem
            import json
            
            monitor = MonitoringSystem()
            try:
                # Run all health checks
                results = monitor.check_all_metrics(days=7)
                
                # Log summary
                logger.info(f"Monitoring Status: {results['overall_status'].upper()}")
                
                # Log alerts
                if results['alerts']:
                    logger.warning(f"⚠️  {len(results['alerts'])} alerts detected:")
                    for alert in results['alerts']:
                        severity_emoji = "🔴" if alert['severity'] == 'critical' else "🟡"
                        logger.warning(f"{severity_emoji} {alert['message']}")
                else:
                    logger.info("✅ No alerts - system is healthy!")
                
                # Save detailed report
                report_path = os.path.join(PROJECT_ROOT, 'monitoring_report.json')
                with open(report_path, 'w') as f:
                    json.dump(results, f, indent=2, default=str)
                logger.info(f"📊 Detailed report saved to: {report_path}")
                
                # If critical alerts, could send notifications here
                critical_alerts = [a for a in results['alerts'] if a['severity'] == 'critical']
                if critical_alerts:
                    logger.error(f"🚨 {len(critical_alerts)} CRITICAL alerts detected!")
                    # TODO: Send email/Slack notification
                
                logger.info("✅ Monitoring completed successfully")
                
            finally:
                monitor.close()
                
        except Exception as e:
            logger.error(f"❌ Monitoring failed: {e}", exc_info=True)
    
    def _historical_recent_update(self):
        """Import recent movies from the last 30 days"""
        logger.info("🆕 Starting historical recent update...")
        try:
            result = self.historical_importer.import_recent_movies(days_back=30)
            if result['success']:
                logger.info(f"✅ Historical recent update completed: {result['movies_processed']} movies processed")
            else:
                logger.error(f"❌ Historical recent update failed: {result.get('error', 'Unknown error')}")
        except Exception as e:
            logger.error(f"❌ Historical recent update failed: {e}", exc_info=True)
    
    def _historical_batch_import(self):
        """Import a batch of historical movies (5 years)"""
        logger.info("📚 Starting historical batch import...")
        try:
            # Import movies from 5 years ago to current year
            current_year = datetime.now().year
            start_year = current_year - 5
            
            result = self.historical_importer.import_movies_by_year_range(
                start_year=start_year,
                end_year=current_year,
                pages_per_year=15,  # 15 pages = ~300 movies per year
                batch_years=2  # Process 2 years at a time
            )
            
            if result['success']:
                logger.info(f"✅ Historical batch import completed: {result['total_processed']} movies processed")
                logger.info(f"📅 Years processed: {len(result['years_processed'])}")
            else:
                logger.error(f"❌ Historical batch import failed: {result.get('error', 'Unknown error')}")
        except Exception as e:
            logger.error(f"❌ Historical batch import failed: {e}", exc_info=True)
    
    def run_manual_update(self, update_type: str = 'quick'):
        """
        Manually trigger a pipeline update
        
        Args:
            update_type: 'quick', 'daily', 'full', 'historical_recent', or 'historical_batch'
        """
        logger.info(f"🔧 Manual {update_type} update triggered")
        
        if update_type == 'quick':
            self._quick_update()
        elif update_type == 'daily':
            self._daily_update()
        elif update_type == 'full':
            self._weekly_enrichment()
        elif update_type == 'historical_recent':
            self._historical_recent_update()
        elif update_type == 'historical_batch':
            self._historical_batch_import()
        else:
            logger.error(f"Unknown update type: {update_type}")
            logger.info("Available types: quick, daily, full, historical_recent, historical_batch")
    
    def start(self):
        """Start the scheduler"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("🎬 Pipeline scheduler started")
            logger.info(f"Current jobs: {len(self.scheduler.get_jobs())}")
            self._print_schedule()
    
    def stop(self):
        """Stop the scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("🛑 Pipeline scheduler stopped")
    
    def _print_schedule(self):
        """Print current schedule"""
        logger.info("\n📅 Scheduled Jobs:")
        for job in self.scheduler.get_jobs():
            logger.info(f"  - {job.name} (ID: {job.id})")
            logger.info(f"    Next run: {job.next_run_time}")
    
    def get_job_status(self):
        """Get status of all scheduled jobs"""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger)
            })
        return jobs


# Global scheduler instance
_scheduler_instance = None


def get_scheduler() -> PipelineScheduler:
    """Get or create scheduler instance"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = PipelineScheduler()
    return _scheduler_instance


if __name__ == "__main__":
    # Run scheduler as standalone service
    try:
        scheduler = get_scheduler()
        scheduler.start()
        
        logger.info("\n" + "=" * 60)
        logger.info("🎬 Movie Pipeline Scheduler Running")
        logger.info("=" * 60)
        logger.info("Press Ctrl+C to exit")
        logger.info("=" * 60 + "\n")
        
        # Keep the script running
        import time
        while True:
            time.sleep(1)
            
    except (KeyboardInterrupt, SystemExit):
        logger.info("\n🛑 Shutting down scheduler...")
        scheduler.stop()
        logger.info("✅ Scheduler stopped gracefully")

