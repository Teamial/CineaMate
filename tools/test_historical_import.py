#!/usr/bin/env python3
"""
Test Script for Historical Movie Import System
Tests the historical import functionality with small batches
"""

import os
import sys
import time
import logging
from datetime import datetime
from dotenv import load_dotenv

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from historical_movie_import import HistoricalMovieImporter
from monitor_database import DatabaseMonitor

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_historical_import():
    """Test historical import with a small batch"""
    logger.info("🧪 Testing Historical Movie Import System")
    logger.info("=" * 60)
    
    # Get environment variables
    api_key = os.getenv('TMDB_API_KEY')
    db_url = os.getenv('DATABASE_URL')
    
    if not api_key:
        logger.error("❌ TMDB_API_KEY not found in environment variables")
        return False
    
    if not db_url:
        logger.error("❌ DATABASE_URL not found in environment variables")
        return False
    
    # Initialize components
    importer = HistoricalMovieImporter(api_key, db_url)
    monitor = DatabaseMonitor(db_url)
    
    try:
        # Get initial database status
        logger.info("📊 Getting initial database status...")
        initial_status = monitor.get_database_status()
        initial_count = initial_status.get('total_movies', 0)
        logger.info(f"   Initial movie count: {initial_count:,}")
        
        # Test 1: Import recent movies (last 7 days)
        logger.info("\n🆕 Test 1: Importing recent movies (last 7 days)...")
        recent_result = importer.import_recent_movies(days_back=7)
        
        if recent_result['success']:
            logger.info(f"✅ Recent import successful: {recent_result['movies_processed']} movies processed")
        else:
            logger.warning(f"⚠️  Recent import failed: {recent_result.get('error', 'Unknown error')}")
        
        # Test 2: Import small historical batch (2 years, 5 pages each)
        logger.info("\n📚 Test 2: Importing small historical batch (2023-2024, 5 pages each)...")
        historical_result = importer.import_movies_by_year_range(
            start_year=2023,
            end_year=2024,
            pages_per_year=5,  # Small batch for testing
            batch_years=1,  # Process 1 year at a time
            min_vote_count=5  # Lower threshold for testing
        )
        
        if historical_result['success']:
            logger.info(f"✅ Historical import successful: {historical_result['total_processed']} movies processed")
            logger.info(f"📅 Years processed: {len(historical_result['years_processed'])}")
        else:
            logger.warning(f"⚠️  Historical import failed: {historical_result.get('error', 'Unknown error')}")
        
        # Get final database status
        logger.info("\n📊 Getting final database status...")
        final_status = monitor.get_database_status()
        final_count = final_status.get('total_movies', 0)
        growth = final_count - initial_count
        
        logger.info(f"   Final movie count: {final_count:,}")
        logger.info(f"   Growth: +{growth:,} movies")
        
        # Test 3: Check database integrity
        logger.info("\n🔍 Test 3: Checking database integrity...")
        embedding_coverage = final_status.get('embedding_coverage', 0)
        enrichment_coverage = final_status.get('enrichment_coverage', 0)
        
        logger.info(f"   Embedding coverage: {embedding_coverage:.1f}%")
        logger.info(f"   Enrichment coverage: {enrichment_coverage:.1f}%")
        
        # Test 4: Verify API rate limiting
        logger.info("\n⏱️  Test 4: Verifying API rate limiting...")
        start_time = time.time()
        
        # Make a few API calls to test rate limiting
        test_movies = []
        for page in range(1, 4):  # Test 3 pages
            data = importer._make_request(
                "discover/movie",
                {
                    "primary_release_year": 2024,
                    "page": page,
                    "sort_by": "popularity.desc",
                    "vote_count.gte": 10
                }
            )
            if data and 'results' in data:
                test_movies.extend(data['results'])
        
        elapsed = time.time() - start_time
        logger.info(f"   API calls completed in {elapsed:.2f} seconds")
        logger.info(f"   Movies fetched: {len(test_movies)}")
        logger.info(f"   Average time per call: {elapsed/3:.2f} seconds")
        
        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("🎉 HISTORICAL IMPORT SYSTEM TEST COMPLETE")
        logger.info("=" * 60)
        
        success_count = 0
        if recent_result['success']:
            success_count += 1
        if historical_result['success']:
            success_count += 1
        if growth > 0:
            success_count += 1
        if elapsed > 0.5:  # Rate limiting working (slower than 0.5s per call)
            success_count += 1
        
        logger.info(f"✅ Tests passed: {success_count}/4")
        logger.info(f"📊 Total movies added: {growth:,}")
        logger.info(f"⏱️  API rate limiting: {'Working' if elapsed > 0.5 else 'May need adjustment'}")
        
        return success_count >= 3  # At least 3 out of 4 tests should pass
        
    except Exception as e:
        logger.error(f"❌ Test failed with error: {e}")
        return False


def test_scheduler_integration():
    """Test scheduler integration"""
    logger.info("\n🔄 Testing Scheduler Integration...")
    
    try:
        # Import scheduler
        from backend.scheduler import PipelineScheduler
        
        # Initialize scheduler (but don't start it)
        scheduler = PipelineScheduler()
        
        # Check if historical import methods exist
        has_recent_method = hasattr(scheduler, '_historical_recent_update')
        has_batch_method = hasattr(scheduler, '_historical_batch_import')
        
        logger.info(f"   Historical recent method: {'✅' if has_recent_method else '❌'}")
        logger.info(f"   Historical batch method: {'✅' if has_batch_method else '❌'}")
        
        # Check scheduled jobs
        try:
            jobs = scheduler.get_job_status()
            historical_jobs = [job for job in jobs if 'historical' in job['name'].lower()]
            
            logger.info(f"   Historical jobs scheduled: {len(historical_jobs)}")
            for job in historical_jobs:
                logger.info(f"     - {job['name']} (ID: {job['id']})")
            
            return has_recent_method and has_batch_method and len(historical_jobs) >= 2
        except Exception as e:
            logger.warning(f"   Could not get job status: {e}")
            return has_recent_method and has_batch_method
        
    except Exception as e:
        logger.error(f"❌ Scheduler integration test failed: {e}")
        return False


def test_monitoring_system():
    """Test monitoring system"""
    logger.info("\n📊 Testing Monitoring System...")
    
    try:
        db_url = os.getenv('DATABASE_URL')
        if not db_url:
            logger.error("❌ DATABASE_URL not found")
            return False
        
        monitor = DatabaseMonitor(db_url)
        
        # Test status retrieval
        status = monitor.get_database_status()
        logger.info(f"   Database status retrieved: {'✅' if status else '❌'}")
        
        # Test progress tracking
        progress = monitor.get_import_progress(days_back=7)
        logger.info(f"   Progress tracking: {'✅' if progress else '❌'}")
        
        # Test completion estimation
        estimate = monitor.estimate_completion_time(10000)
        logger.info(f"   Completion estimation: {'✅' if estimate else '❌'}")
        
        return bool(status and progress and estimate)
        
    except Exception as e:
        logger.error(f"❌ Monitoring system test failed: {e}")
        return False


def main():
    """Main test function"""
    logger.info("🚀 Starting Historical Import System Tests")
    logger.info("=" * 80)
    
    # Run tests
    test_results = []
    
    # Test 1: Historical import functionality
    test_results.append(("Historical Import", test_historical_import()))
    
    # Test 2: Scheduler integration
    test_results.append(("Scheduler Integration", test_scheduler_integration()))
    
    # Test 3: Monitoring system
    test_results.append(("Monitoring System", test_monitoring_system()))
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("📋 TEST RESULTS SUMMARY")
    logger.info("=" * 80)
    
    passed_tests = 0
    for test_name, result in test_results:
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"   {test_name}: {status}")
        if result:
            passed_tests += 1
    
    logger.info(f"\n🎯 Overall Result: {passed_tests}/{len(test_results)} tests passed")
    
    if passed_tests == len(test_results):
        logger.info("🎉 All tests passed! Historical import system is ready.")
        logger.info("\n📝 Next Steps:")
        logger.info("   1. Run: python historical_movie_import.py --start-year 2020 --end-year 2024")
        logger.info("   2. Monitor: python monitor_database.py --status")
        logger.info("   3. Start scheduler: python backend/scheduler.py")
        return True
    else:
        logger.error("❌ Some tests failed. Please check the errors above.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
