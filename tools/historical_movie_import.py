#!/usr/bin/env python3
"""
Historical Movie Import Script
Imports movies by year range with batch processing to avoid API rate limits
"""

import os
import sys
import time
import logging
import json
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from movie_pipeline import MovieETLPipeline
from urllib.parse import urlparse, urlunparse

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HistoricalMovieImporter:
    """Import movies by year range with batch processing"""
    
    def __init__(self, api_key: str, db_url: str):
        self.api_key = api_key
        # Normalize DB URL scheme for SQLAlchemy
        try:
            parsed = urlparse(db_url)
            if parsed.scheme == 'postgres':
                parsed = parsed._replace(scheme='postgresql')
                db_url = urlunparse(parsed)
                logger.info("Rewrote DATABASE_URL scheme postgres -> postgresql in historical importer")
            elif db_url.startswith('postgresql+psycopg2://'):
                db_url = db_url.replace('postgresql+psycopg2://', 'postgresql://', 1)
            elif db_url.startswith('postgres://'):
                db_url = db_url.replace('postgres://', 'postgresql://', 1)
        except Exception as e:
            logger.warning(f"Could not normalize DATABASE_URL in historical importer: {e}")
        self.db_url = db_url
        self.base_url = "https://api.themoviedb.org/3"
        self.pipeline = MovieETLPipeline(api_key, db_url)
        
        # Batch processing settings
        self.batch_size = 50  # Movies per batch
        self.api_delay = 0.3  # Seconds between API calls
        self.batch_delay = 5  # Seconds between batches
        
        # Progress tracking
        self.total_movies_collected = 0
        self.total_movies_processed = 0
        self.failed_requests = 0
        
    def _make_request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """Make API request with error handling and rate limiting"""
        try:
            default_params = {"api_key": self.api_key, "language": "en-US"}
            if params:
                default_params.update(params)
            
            response = requests.get(
                f"{self.base_url}/{endpoint}",
                params=default_params,
                timeout=10
            )
            response.raise_for_status()
            time.sleep(self.api_delay)
            return response.json()
        except Exception as e:
            logger.error(f"API request failed for {endpoint}: {e}")
            self.failed_requests += 1
            return None
    
    def import_movies_by_year_range(self, 
                                   start_year: int = 1990, 
                                   end_year: int = 2024,
                                   pages_per_year: int = 20,
                                   min_vote_count: int = 10,
                                   batch_years: int = 5) -> Dict:
        """
        Import movies by year range with batch processing
        
        Args:
            start_year: Starting year for import
            end_year: Ending year for import
            pages_per_year: Pages to fetch per year (20 movies per page)
            min_vote_count: Minimum vote count to filter low-quality movies
            batch_years: Number of years to process in each batch
        """
        logger.info("=" * 80)
        logger.info("🎬 HISTORICAL MOVIE IMPORT STARTED")
        logger.info(f"📅 Year Range: {start_year} - {end_year}")
        logger.info(f"📄 Pages per year: {pages_per_year}")
        logger.info(f"📦 Batch size: {batch_years} years")
        logger.info("=" * 80)
        
        start_time = time.time()
        all_movies = []
        years_processed = []
        
        try:
            # Process years in batches
            year_batches = self._create_year_batches(start_year, end_year, batch_years)
            
            for batch_idx, year_batch in enumerate(year_batches, 1):
                logger.info(f"\n📦 Processing Batch {batch_idx}/{len(year_batches)}: Years {year_batch[0]}-{year_batch[-1]}")
                
                batch_movies = self._process_year_batch(
                    year_batch, pages_per_year, min_vote_count
                )
                
                if batch_movies:
                    all_movies.extend(batch_movies)
                    years_processed.extend(year_batch)
                    logger.info(f"✅ Batch {batch_idx} complete: {len(batch_movies)} movies collected")
                
                # Batch delay to respect API limits
                if batch_idx < len(year_batches):
                    logger.info(f"⏳ Waiting {self.batch_delay}s before next batch...")
                    time.sleep(self.batch_delay)
            
            # Process collected movies
            if all_movies:
                logger.info(f"\n🔄 Processing {len(all_movies)} collected movies...")
                processed_count = self._process_collected_movies(all_movies)
                
                # Log completion
                elapsed = time.time() - start_time
                self._log_completion(elapsed, len(all_movies), processed_count, years_processed)
                
                return {
                    'success': True,
                    'total_collected': len(all_movies),
                    'total_processed': processed_count,
                    'years_processed': years_processed,
                    'duration_seconds': elapsed,
                    'failed_requests': self.failed_requests
                }
            else:
                logger.error("❌ No movies collected")
                return {'success': False, 'error': 'No movies collected'}
                
        except Exception as e:
            logger.error(f"❌ Historical import failed: {e}")
            elapsed = time.time() - start_time
            return {
                'success': False,
                'error': str(e),
                'duration_seconds': elapsed,
                'movies_collected': len(all_movies)
            }
    
    def _create_year_batches(self, start_year: int, end_year: int, batch_size: int) -> List[List[int]]:
        """Create batches of years to process"""
        years = list(range(start_year, end_year + 1))
        batches = []
        
        for i in range(0, len(years), batch_size):
            batch = years[i:i + batch_size]
            batches.append(batch)
        
        return batches
    
    def _process_year_batch(self, years: List[int], pages_per_year: int, min_vote_count: int) -> List[Dict]:
        """Process a batch of years"""
        batch_movies = []
        
        for year in years:
            logger.info(f"  📅 Processing year {year}...")
            year_movies = self._fetch_movies_for_year(year, pages_per_year, min_vote_count)
            
            if year_movies:
                batch_movies.extend(year_movies)
                logger.info(f"    ✅ {year}: {len(year_movies)} movies")
            else:
                logger.warning(f"    ⚠️  {year}: No movies found")
        
        return batch_movies
    
    def _fetch_movies_for_year(self, year: int, pages: int, min_vote_count: int) -> List[Dict]:
        """Fetch movies for a specific year"""
        movies = []
        
        for page in range(1, pages + 1):
            data = self._make_request(
                "discover/movie",
                {
                    "primary_release_year": year,
                    "page": page,
                    "sort_by": "popularity.desc",
                    "vote_count.gte": min_vote_count,
                    "include_adult": False,
                    "with_original_language": "en"  # Focus on English movies
                }
            )
            
            if data and 'results' in data:
                movies.extend(data['results'])
                logger.debug(f"    Page {page}: {len(data['results'])} movies")
            else:
                logger.warning(f"    Page {page}: No data returned")
                break
        
        return movies
    
    def _process_collected_movies(self, movies: List[Dict]) -> int:
        """Process collected movies through the pipeline"""
        try:
            # Remove duplicates
            unique_movies = {movie['id']: movie for movie in movies}.values()
            movies = list(unique_movies)
            logger.info(f"📊 Removed duplicates: {len(movies)} unique movies")
            
            # Extract genres
            genres = self.pipeline.extract_genres()
            
            # Transform movies
            df_movies = self.pipeline.transform_movies(movies, genres)
            
            if df_movies.empty:
                logger.error("❌ No movies after transformation")
                return 0
            
            # Load to database
            self.pipeline.load_to_database(df_movies, genres, incremental=True)
            
            # Log pipeline run
            self.pipeline.log_pipeline_run(
                movies_count=len(df_movies),
                status='SUCCESS',
                categories=['historical_import'],
                duration=1.0  # Set a small duration instead of 0
            )
            
            return len(df_movies)
            
        except Exception as e:
            logger.error(f"❌ Failed to process collected movies: {e}")
            return 0
    
    def _log_completion(self, duration: float, collected: int, processed: int, years: List[int]):
        """Log completion statistics"""
        logger.info("=" * 80)
        logger.info("✨ HISTORICAL IMPORT COMPLETE")
        logger.info(f"⏱️  Duration: {duration:.2f} seconds ({duration/60:.1f} minutes)")
        logger.info(f"📊 Movies collected: {collected:,}")
        logger.info(f"💾 Movies processed: {processed:,}")
        logger.info(f"📅 Years processed: {len(years)} ({years[0]}-{years[-1]})")
        logger.info(f"❌ Failed requests: {self.failed_requests}")
        logger.info(f"📈 Success rate: {((collected-self.failed_requests)/collected*100):.1f}%")
        logger.info("=" * 80)
    
    def import_recent_movies(self, days_back: int = 30) -> Dict:
        """Import recent movies from the last N days"""
        logger.info(f"🆕 Importing movies from last {days_back} days...")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        movies = []
        
        # Fetch recent movies
        for page in range(1, 21):  # Up to 20 pages
            data = self._make_request(
                "discover/movie",
                {
                    "primary_release_date.gte": start_date.strftime("%Y-%m-%d"),
                    "primary_release_date.lte": end_date.strftime("%Y-%m-%d"),
                    "page": page,
                    "sort_by": "popularity.desc",
                    "vote_count.gte": 5
                }
            )
            
            if data and 'results' in data:
                movies.extend(data['results'])
                logger.info(f"  Page {page}: {len(data['results'])} movies")
            else:
                break
        
        if movies:
            processed_count = self._process_collected_movies(movies)
            return {
                'success': True,
                'movies_collected': len(movies),
                'movies_processed': processed_count
            }
        else:
            return {'success': False, 'error': 'No recent movies found'}


def main():
    """Main function for command-line usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Historical Movie Import')
    parser.add_argument('--start-year', type=int, default=1990, help='Starting year')
    parser.add_argument('--end-year', type=int, default=2024, help='Ending year')
    parser.add_argument('--pages-per-year', type=int, default=20, help='Pages per year')
    parser.add_argument('--batch-years', type=int, default=5, help='Years per batch')
    parser.add_argument('--recent-only', action='store_true', help='Import only recent movies')
    parser.add_argument('--days-back', type=int, default=30, help='Days back for recent import')
    
    args = parser.parse_args()
    
    # Get environment variables
    api_key = os.getenv('TMDB_API_KEY')
    db_url = os.getenv('DATABASE_URL')
    
    if not api_key:
        logger.error("❌ TMDB_API_KEY not found in environment variables")
        sys.exit(1)
    
    if not db_url:
        logger.error("❌ DATABASE_URL not found in environment variables")
        sys.exit(1)
    
    # Initialize importer
    importer = HistoricalMovieImporter(api_key, db_url)
    
    try:
        if args.recent_only:
            # Import recent movies only
            result = importer.import_recent_movies(args.days_back)
        else:
            # Import historical movies
            result = importer.import_movies_by_year_range(
                start_year=args.start_year,
                end_year=args.end_year,
                pages_per_year=args.pages_per_year,
                batch_years=args.batch_years
            )
        
        if result['success']:
            logger.info("✅ Import completed successfully!")
            sys.exit(0)
        else:
            logger.error(f"❌ Import failed: {result.get('error', 'Unknown error')}")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("⏹️  Import interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
