import requests
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
import time
import os
import json
import logging
from dotenv import load_dotenv
from typing import List, Dict, Optional
from urllib.parse import urlparse, urlunparse

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MovieETLPipeline:
    def __init__(self, api_key, db_url):
        self.api_key = api_key
        self.base_url = "https://api.themoviedb.org/3"
        # Normalize DATABASE_URL scheme for SQLAlchemy compatibility
        try:
            parsed = urlparse(db_url)
            if parsed.scheme == 'postgres':
                parsed = parsed._replace(scheme='postgresql')
                db_url = urlunparse(parsed)
                logger.info("Rewrote DATABASE_URL scheme postgres -> postgresql in movie_pipeline")
            elif db_url.startswith('postgresql+psycopg2://'):
                db_url = db_url.replace('postgresql+psycopg2://', 'postgresql://', 1)
                logger.info("Converted DATABASE_URL from postgresql+psycopg2:// to postgresql:// in movie_pipeline")
            elif db_url.startswith('postgres://'):
                db_url = db_url.replace('postgres://', 'postgresql://', 1)
                logger.info("Converted DATABASE_URL from postgres:// to postgresql:// in movie_pipeline")
        except Exception as e:
            logger.warning(f"Could not normalize DATABASE_URL in movie_pipeline: {e}")

        self.engine = create_engine(db_url)
        self.image_base = "https://image.tmdb.org/t/p"
        
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
            time.sleep(0.25)  # Rate limiting
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed for {endpoint}: {e}")
            return None
    
    def extract_movies_by_category(self, category: str = "popular", num_pages: int = 10) -> List[Dict]:
        """
        Extract movies from different TMDB categories
        Categories: popular, top_rated, upcoming, now_playing
        """
        logger.info(f"🎬 Extracting {category} movies (pages: {num_pages})...")
        movies = []
        
        for page in range(1, num_pages + 1):
            data = self._make_request(f"movie/{category}", {"page": page})
            if data and 'results' in data:
                movies.extend(data['results'])
                logger.info(f"  ✓ Page {page}: {len(data['results'])} movies")
        
        logger.info(f"✅ Extracted {len(movies)} {category} movies\n")
        return movies
    
    def extract_trending_movies(self, time_window: str = "week", num_pages: int = 5) -> List[Dict]:
        """Extract trending movies (day or week)"""
        logger.info(f"📈 Extracting trending movies ({time_window})...")
        movies = []
        
        for page in range(1, num_pages + 1):
            data = self._make_request(f"trending/movie/{time_window}", {"page": page})
            if data and 'results' in data:
                movies.extend(data['results'])
        
        logger.info(f"✅ Extracted {len(movies)} trending movies\n")
        return movies
    
    def extract_movie_details(self, movie_id: int) -> Optional[Dict]:
        """Extract detailed information for a specific movie"""
        data = self._make_request(
            f"movie/{movie_id}",
            {"append_to_response": "credits,keywords,videos,similar"}
        )
        return data
    
    def enrich_movies_with_details(self, movies: List[Dict], max_movies: int = 50) -> List[Dict]:
        """Enrich movie data with additional details (cast, crew, keywords)"""
        logger.info(f"🔍 Enriching movies with detailed information...")
        enriched = []
        
        # Limit enrichment to avoid too many API calls
        for movie in movies[:max_movies]:
            details = self.extract_movie_details(movie['id'])
            if details:
                # Add cast and crew
                movie['cast'] = details.get('credits', {}).get('cast', [])[:10]  # Top 10 cast
                movie['crew'] = details.get('credits', {}).get('crew', [])[:5]   # Top 5 crew
                movie['keywords'] = [k['name'] for k in details.get('keywords', {}).get('keywords', [])]
                movie['runtime'] = details.get('runtime')
                movie['budget'] = details.get('budget')
                movie['revenue'] = details.get('revenue')
                movie['tagline'] = details.get('tagline')
                movie['original_language'] = details.get('original_language')
                
                # Get similar movies
                similar = details.get('similar', {}).get('results', [])
                movie['similar_movie_ids'] = [m['id'] for m in similar[:5]]
                
                # Get trailer
                videos = details.get('videos', {}).get('results', [])
                trailers = [v for v in videos if v.get('type') == 'Trailer' and v.get('site') == 'YouTube']
                movie['trailer_key'] = trailers[0]['key'] if trailers else None
            
            enriched.append(movie)
        
        logger.info(f"✅ Enriched {len(enriched)} movies\n")
        return enriched

    def enrich_missing_trailers_and_details(self, limit_per_run: int = 500, force: bool = False):
        """Enrich movies already in the database that are missing trailers or details.

        Args:
            limit_per_run: Max movies to enrich in this run (protect API quotas)
            force: If True, re-fetch even if fields exist
        """
        logger.info(f"🔧 Enriching existing DB movies (limit={limit_per_run}, force={force})...")

        with self.engine.connect() as conn:
            # Select ids missing key enriched fields
            condition = (
                "trailer_key IS NULL OR runtime IS NULL OR keywords IS NULL OR \"cast\" IS NULL OR crew IS NULL"
            )
            if force:
                condition = "TRUE"  # Re-enrich everything (bounded by limit)

            ids = [row[0] for row in conn.execute(text(f"""
                SELECT id FROM movies
                WHERE {condition}
                ORDER BY popularity DESC NULLS LAST, vote_count DESC NULLS LAST
                LIMIT :limit
            """), {"limit": limit_per_run}).fetchall()]

        if not ids:
            logger.info("✅ Nothing to enrich – all movies have details")
            return {"updated": 0}

        updated = 0
        for movie_id in ids:
            details = self.extract_movie_details(movie_id)
            if not details:
                continue

            cast = details.get('credits', {}).get('cast', [])[:10]
            crew = details.get('credits', {}).get('crew', [])[:5]
            keywords = [k['name'] for k in details.get('keywords', {}).get('keywords', [])]
            runtime = details.get('runtime')
            budget = details.get('budget')
            revenue = details.get('revenue')
            tagline = details.get('tagline')
            original_language = details.get('original_language')

            similar = details.get('similar', {}).get('results', [])
            similar_ids = [m['id'] for m in similar[:5]] if similar else None

            videos = details.get('videos', {}).get('results', [])
            trailers = [v for v in videos if v.get('type') == 'Trailer' and v.get('site') == 'YouTube']
            trailer_key = trailers[0]['key'] if trailers else None

            payload = {
                "cast": json.dumps([{
                    'name': c['name'],
                    'character': c.get('character', ''),
                    'profile_path': c.get('profile_path', None)
                } for c in cast]) if cast else None,
                "crew": json.dumps([{'name': c['name'], 'job': c.get('job', '')} for c in crew]) if crew else None,
                "keywords": json.dumps(keywords) if keywords else None,
                "runtime": runtime,
                "budget": budget,
                "revenue": revenue,
                "tagline": tagline,
                "similar_movie_ids": json.dumps(similar_ids) if similar_ids else None,
                "trailer_key": trailer_key,
                "original_language": original_language
            }

            # Build dynamic SET clause only for non-null values unless force=True
            set_clauses = []
            params = {"id": movie_id}
            for col, val in payload.items():
                if force or val is not None:
                    set_clauses.append(f'"{col}" = :{col}')
                    params[col] = val

            if not set_clauses:
                continue

            with self.engine.connect() as conn:
                conn.execute(text(f"""
                    UPDATE movies
                    SET {', '.join(set_clauses)}, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """), params)
                conn.commit()
                updated += 1

        logger.info(f"✅ Enriched {updated} existing movies")
        return {"updated": updated}
    
    def extract_genres(self):
        """Extract genre list from TMDB"""
        logger.info("🎭 Extracting genres...")
        data = self._make_request("genre/movie/list")
        genres = data.get('genres', []) if data else []
        logger.info(f"✅ Extracted {len(genres)} genres\n")
        return genres
    
    def transform_movies(self, movies: List[Dict], genres: List[Dict]) -> pd.DataFrame:
        """Transform raw movie data into clean DataFrame"""
        logger.info("🔄 Transforming movie data...")
        
        if not movies:
            logger.warning("No movies to transform")
            return pd.DataFrame()
        
        # Create genre lookup dict
        genre_map = {g['id']: g['name'] for g in genres}
        
        # Build DataFrame
        df = pd.DataFrame(movies)
        
        # Define required columns
        required_cols = ['id', 'title', 'overview', 'release_date',
                        'vote_average', 'vote_count', 'popularity',
                        'genre_ids', 'poster_path', 'backdrop_path']
        
        # Handle optional enriched columns
        optional_cols = ['cast', 'crew', 'keywords', 'runtime', 'budget', 
                        'revenue', 'tagline', 'similar_movie_ids', 'trailer_key', 'original_language']
        
        # Select columns that exist
        cols_to_keep = [col for col in required_cols if col in df.columns]
        df_clean = df[cols_to_keep].copy()
        
        # Add optional columns if they exist
        for col in optional_cols:
            if col in df.columns:
                df_clean[col] = df[col]
        
        # Transform data
        df_clean['release_date'] = pd.to_datetime(df_clean['release_date'], errors='coerce')
        df_clean['poster_url'] = df_clean['poster_path'].apply(
            lambda x: f"{self.image_base}/w500{x}" if pd.notna(x) else None
        )
        df_clean['backdrop_url'] = df_clean['backdrop_path'].apply(
            lambda x: f"{self.image_base}/w1280{x}" if pd.notna(x) else None
        )
        
        # Map genre IDs to names
        df_clean['genres'] = df_clean['genre_ids'].apply(
            lambda ids: [genre_map.get(gid, 'Unknown') for gid in ids] if ids else []
        )
        
        # Transform cast and crew to JSON strings
        if 'cast' in df_clean.columns:
            df_clean['cast'] = df_clean['cast'].apply(
                lambda x: json.dumps([{
                    'name': c['name'], 
                    'character': c.get('character', ''),
                    'profile_path': c.get('profile_path', None)
                } for c in x[:10]]) if isinstance(x, list) else None
            )
        
        if 'crew' in df_clean.columns:
            df_clean['crew'] = df_clean['crew'].apply(
                lambda x: json.dumps([{'name': c['name'], 'job': c.get('job', '')} 
                                     for c in x[:5]]) if isinstance(x, list) else None
            )
        
        if 'keywords' in df_clean.columns:
            df_clean['keywords'] = df_clean['keywords'].apply(
                lambda x: json.dumps(x) if isinstance(x, list) else None
            )
        
        if 'similar_movie_ids' in df_clean.columns:
            df_clean['similar_movie_ids'] = df_clean['similar_movie_ids'].apply(
                lambda x: json.dumps(x) if isinstance(x, list) else None
            )
        
        # Drop unnecessary columns
        df_clean = df_clean.drop(['genre_ids', 'poster_path', 'backdrop_path'], axis=1, errors='ignore')
        
        # Remove duplicates and nulls
        df_clean = df_clean.drop_duplicates(subset=['id'])
        df_clean = df_clean.dropna(subset=['title', 'id'])
        
        logger.info(f"✅ Transformed {len(df_clean)} movies\n")
        return df_clean
    
    def load_to_database(self, df_movies: pd.DataFrame, genres: List[Dict], incremental: bool = True):
        """Load data into PostgreSQL database with upsert support"""
        logger.info("💾 Loading data to database...")
        
        if df_movies.empty:
            logger.warning("No movies to load")
            return
        
        try:
            # Create tables if they don't exist with enriched columns
            with self.engine.connect() as conn:
                # Movies table with enriched fields
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS movies (
                        id INTEGER PRIMARY KEY,
                        title VARCHAR(500),
                        overview TEXT,
                        release_date DATE,
                        vote_average FLOAT,
                        vote_count INTEGER,
                        popularity FLOAT,
                        poster_url VARCHAR(500),
                        backdrop_url VARCHAR(500),
                        genres JSONB,
                        "cast" JSONB,
                        crew JSONB,
                        keywords JSONB,
                        runtime INTEGER,
                        budget BIGINT,
                        revenue BIGINT,
                        tagline TEXT,
                        similar_movie_ids JSONB,
                        trailer_key VARCHAR(100),
                        original_language VARCHAR(10),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                
                # Genres table
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS genres (
                        id INTEGER PRIMARY KEY,
                        name VARCHAR(100)
                    )
                """))
                
                # Pipeline runs tracking table
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS pipeline_runs (
                        id SERIAL PRIMARY KEY,
                        run_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        movies_processed INTEGER,
                        status VARCHAR(50),
                        source_categories JSONB,
                        duration_seconds FLOAT
                    )
                """))
                
                conn.commit()
            
            # Prepare data for loading
            df_movies['genres'] = df_movies['genres'].apply(
                lambda x: json.dumps(x) if isinstance(x, list) else x
            )
            
            if incremental:
                # Use upsert logic for incremental updates
                logger.info("Using incremental update mode...")
                self._upsert_movies(df_movies)
            else:
                # Full load
                df_movies.to_sql('movies', self.engine, if_exists='append', 
                               index=False, method='multi')
            
            # Load genres (with conflict handling)
            if genres:
                self._upsert_genres(genres)
            
            logger.info(f"✅ Loaded {len(df_movies)} movies and {len(genres)} genres to database\n")
            
        except Exception as e:
            logger.error(f"Database error: {e}")
            raise
    
    def _upsert_movies(self, df_movies: pd.DataFrame):
        """Upsert movies to avoid duplicates"""
        with self.engine.connect() as conn:
            for _, row in df_movies.iterrows():
                # Convert row to dict and handle NaN values
                row_dict = row.to_dict()
                for key, value in row_dict.items():
                    if pd.isna(value):
                        row_dict[key] = None
                
                # Build column list dynamically based on available columns
                columns = list(row_dict.keys())
                # Quote column names to handle reserved keywords like 'cast'
                quoted_columns = [f'"{col}"' for col in columns]
                placeholders = ', '.join([f':{col}' for col in columns])
                update_set = ', '.join([f'"{col}" = :{col}' for col in columns if col != 'id'])
                
                query = text(f"""
                    INSERT INTO movies ({', '.join(quoted_columns)})
                    VALUES ({placeholders})
                    ON CONFLICT (id) DO UPDATE SET
                        {update_set},
                        updated_at = CURRENT_TIMESTAMP
                """)
                
                conn.execute(query, row_dict)
            conn.commit()
    
    def _upsert_genres(self, genres: List[Dict]):
        """Upsert genres to avoid duplicates"""
        with self.engine.connect() as conn:
            for genre in genres:
                query = text("""
                    INSERT INTO genres (id, name)
                    VALUES (:id, :name)
                    ON CONFLICT (id) DO UPDATE SET name = :name
                """)
                conn.execute(query, genre)
            conn.commit()
    
    def log_pipeline_run(self, movies_count: int, status: str, categories: List[str], duration: float):
        """Log pipeline execution details"""
        try:
            with self.engine.connect() as conn:
                # Explicitly set run_date to avoid NOT NULL errors on pre-existing schemas
                query = text("""
                    INSERT INTO pipeline_runs (run_date, movies_processed, status, source_categories, duration_seconds)
                    VALUES (CURRENT_TIMESTAMP, :movies_count, :status, :categories, :duration)
                """)
                conn.execute(query, {
                    'movies_count': movies_count,
                    'status': status,
                    'categories': json.dumps(categories),
                    'duration': duration
                })
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to log pipeline run: {e}")
    
    def run(self, 
            categories: List[str] = None,
            pages_per_category: int = 5,
            include_trending: bool = True,
            enrich_data: bool = False,
            max_enrichment: int = 50,
            incremental: bool = True):
        """
        Run the complete ETL pipeline with multiple data sources
        
        Args:
            categories: List of TMDB categories (popular, top_rated, upcoming, now_playing)
            pages_per_category: Number of pages to fetch per category
            include_trending: Whether to include trending movies
            enrich_data: Whether to enrich movies with detailed information
            max_enrichment: Maximum number of movies to enrich
            incremental: Use incremental updates (upsert) vs full load
        """
        logger.info("=" * 60)
        logger.info("🚀 ENHANCED MOVIE ETL PIPELINE STARTED")
        logger.info("=" * 60 + "\n")
        
        start_time = time.time()
        all_movies = []
        categories_used = []
        
        try:
            # Default categories if none specified
            if categories is None:
                categories = ['popular', 'top_rated', 'upcoming', 'now_playing']
            
            # Extract from multiple categories
            for category in categories:
                movies = self.extract_movies_by_category(category, pages_per_category)
                if movies:
                    all_movies.extend(movies)
                    categories_used.append(category)
            
            # Extract trending movies
            if include_trending:
                trending = self.extract_trending_movies('week', num_pages=3)
                if trending:
                    all_movies.extend(trending)
                    categories_used.append('trending')
            
            # Extract genres
            genres = self.extract_genres()
            
            if not all_movies:
                logger.error("❌ No movies extracted. Exiting.")
                self.log_pipeline_run(0, 'FAILED', categories_used, time.time() - start_time)
                return
            
            # Remove duplicates based on movie ID
            unique_movies = {movie['id']: movie for movie in all_movies}.values()
            all_movies = list(unique_movies)
            logger.info(f"📊 Total unique movies collected: {len(all_movies)}")
            
            # Enrich data if requested
            if enrich_data:
                all_movies = self.enrich_movies_with_details(all_movies, max_enrichment)
            
            # Transform
            df_movies = self.transform_movies(all_movies, genres)
            
            if df_movies.empty:
                logger.error("❌ No movies after transformation. Exiting.")
                self.log_pipeline_run(0, 'FAILED', categories_used, time.time() - start_time)
                return
            
            # Load
            self.load_to_database(df_movies, genres, incremental=incremental)
            
            # Log pipeline run
            elapsed = time.time() - start_time
            self.log_pipeline_run(len(df_movies), 'SUCCESS', categories_used, elapsed)
            
            # Summary
            logger.info("=" * 60)
            logger.info(f"✨ PIPELINE COMPLETE in {elapsed:.2f}s")
            logger.info(f"📊 Movies processed: {len(df_movies)}")
            logger.info(f"🎭 Genres: {len(genres)}")
            logger.info(f"📚 Categories used: {', '.join(categories_used)}")
            logger.info(f"🔍 Data enriched: {'Yes' if enrich_data else 'No'}")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"❌ Pipeline failed: {e}")
            elapsed = time.time() - start_time
            self.log_pipeline_run(len(all_movies), 'FAILED', categories_used, elapsed)
            raise
    
    def run_quick_update(self):
        """Quick update with just popular and trending movies"""
        logger.info("⚡ Running quick update...")
        self.run(
            categories=['popular'],
            pages_per_category=3,
            include_trending=True,
            enrich_data=False,
            incremental=True
        )
    
    def run_full_enrichment(self):
        """Full enrichment run with detailed information"""
        logger.info("🔍 Running full enrichment...")
        self.run(
            categories=['popular', 'top_rated', 'upcoming'],
            pages_per_category=10,  # Fetch more pages per category
            include_trending=True,
            enrich_data=True,
            max_enrichment=300,  # Enrich more movies per run
            incremental=True
        )


if __name__ == "__main__":
    # Configuration
    TMDB_API_KEY = os.getenv("TMDB_API_KEY")
    DATABASE_URL = os.getenv("DATABASE_URL")
    
    if not TMDB_API_KEY:
        logger.error("TMDB_API_KEY not found in environment variables")
        exit(1)
    
    if not DATABASE_URL:
        logger.error("DATABASE_URL not found in environment variables")
        exit(1)
    
    # Initialize pipeline
    pipeline = MovieETLPipeline(TMDB_API_KEY, DATABASE_URL)
    
    # Run enhanced pipeline with multiple sources
    pipeline.run(
        categories=['popular', 'top_rated', 'upcoming', 'now_playing'],
        pages_per_category=5,
        include_trending=True,
        enrich_data=True,
        max_enrichment=50,
        incremental=True
    )