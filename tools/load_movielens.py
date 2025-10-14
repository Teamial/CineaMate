#!/usr/bin/env python3
"""
MovieLens 1M Data Ingestion Tool

Downloads and processes the MovieLens 1M dataset for offline bandit replay:
- Downloads users.dat, movies.dat, ratings.dat
- Maps MovieLens IDs to internal movie IDs via title matching
- Creates arm_catalog entries for MovieLens items
- Stores in staging tables: ml_users, ml_movies, ml_ratings

Usage:
    python tools/load_movielens.py
"""

import sys
import os
import requests
import zipfile
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from backend.database import SessionLocal, engine
from backend.models import Movie, ArmCatalog

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MovieLensLoader:
    """Load and process MovieLens 1M dataset"""
    
    def __init__(self, db: Session):
        self.db = db
        self.dataset_url = "https://files.grouplens.org/datasets/movielens/ml-1m.zip"
        self.temp_dir = "/tmp/movielens"
        self.movie_id_mapping = {}  # ML ID -> internal ID
        self.user_id_mapping = {}   # ML ID -> internal ID
    
    def download_dataset(self) -> str:
        """Download MovieLens 1M dataset"""
        logger.info("Downloading MovieLens 1M dataset...")
        
        # Create temp directory
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # Download zip file
        zip_path = os.path.join(self.temp_dir, "ml-1m.zip")
        
        if os.path.exists(zip_path):
            logger.info("Dataset already downloaded")
            return zip_path
        
        try:
            response = requests.get(self.dataset_url, stream=True)
            response.raise_for_status()
            
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"Downloaded dataset to {zip_path}")
            return zip_path
            
        except Exception as e:
            logger.error(f"Failed to download dataset: {e}")
            raise
    
    def extract_dataset(self, zip_path: str) -> str:
        """Extract dataset files"""
        logger.info("Extracting dataset...")
        
        extract_dir = os.path.join(self.temp_dir, "ml-1m")
        
        if os.path.exists(extract_dir):
            logger.info("Dataset already extracted")
            return extract_dir
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(self.temp_dir)
        
        logger.info(f"Extracted to {extract_dir}")
        return extract_dir
    
    def create_staging_tables(self):
        """Create staging tables for MovieLens data"""
        logger.info("Creating staging tables...")
        
        # Create ml_users table
        self.db.execute(text("""
            CREATE TABLE IF NOT EXISTS ml_users (
                ml_user_id INTEGER PRIMARY KEY,
                gender VARCHAR(1),
                age INTEGER,
                occupation INTEGER,
                zip_code VARCHAR(10),
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """))
        
        # Create ml_movies table
        self.db.execute(text("""
            CREATE TABLE IF NOT EXISTS ml_movies (
                ml_movie_id INTEGER PRIMARY KEY,
                title VARCHAR(500),
                genres VARCHAR(500),
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """))
        
        # Create ml_ratings table
        self.db.execute(text("""
            CREATE TABLE IF NOT EXISTS ml_ratings (
                id SERIAL PRIMARY KEY,
                ml_user_id INTEGER NOT NULL,
                ml_movie_id INTEGER NOT NULL,
                rating FLOAT NOT NULL,
                timestamp TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                FOREIGN KEY (ml_user_id) REFERENCES ml_users(ml_user_id),
                FOREIGN KEY (ml_movie_id) REFERENCES ml_movies(ml_movie_id)
            );
        """))
        
        # Create indexes
        self.db.execute(text("CREATE INDEX IF NOT EXISTS idx_ml_ratings_user_id ON ml_ratings(ml_user_id);"))
        self.db.execute(text("CREATE INDEX IF NOT EXISTS idx_ml_ratings_movie_id ON ml_ratings(ml_movie_id);"))
        self.db.execute(text("CREATE INDEX IF NOT EXISTS idx_ml_ratings_timestamp ON ml_ratings(timestamp);"))
        
        self.db.commit()
        logger.info("Staging tables created")
    
    def load_users(self, data_dir: str) -> int:
        """Load users from users.dat"""
        logger.info("Loading users...")
        
        users_file = os.path.join(data_dir, "users.dat")
        user_count = 0
        
        with open(users_file, 'r', encoding='latin-1') as f:
            for line in f:
                parts = line.strip().split('::')
                if len(parts) >= 4:
                    ml_user_id = int(parts[0])
                    gender = parts[1]
                    age = int(parts[2])
                    occupation = int(parts[3])
                    zip_code = parts[4] if len(parts) > 4 else None
                    
                    # Insert into staging table
                    self.db.execute(text("""
                        INSERT INTO ml_users (ml_user_id, gender, age, occupation, zip_code)
                        VALUES (:ml_user_id, :gender, :age, :occupation, :zip_code)
                        ON CONFLICT (ml_user_id) DO NOTHING
                    """), {
                        'ml_user_id': ml_user_id,
                        'gender': gender,
                        'age': age,
                        'occupation': occupation,
                        'zip_code': zip_code
                    })
                    
                    user_count += 1
        
        self.db.commit()
        logger.info(f"Loaded {user_count} users")
        return user_count
    
    def load_movies(self, data_dir: str) -> int:
        """Load movies from movies.dat"""
        logger.info("Loading movies...")
        
        movies_file = os.path.join(data_dir, "movies.dat")
        movie_count = 0
        
        with open(movies_file, 'r', encoding='latin-1') as f:
            for line in f:
                parts = line.strip().split('::')
                if len(parts) >= 3:
                    ml_movie_id = int(parts[0])
                    title = parts[1]
                    genres = parts[2]
                    
                    # Insert into staging table
                    self.db.execute(text("""
                        INSERT INTO ml_movies (ml_movie_id, title, genres)
                        VALUES (:ml_movie_id, :title, :genres)
                        ON CONFLICT (ml_movie_id) DO NOTHING
                    """), {
                        'ml_movie_id': ml_movie_id,
                        'title': title,
                        'genres': genres
                    })
                    
                    movie_count += 1
        
        self.db.commit()
        logger.info(f"Loaded {movie_count} movies")
        return movie_count
    
    def load_ratings(self, data_dir: str) -> int:
        """Load ratings from ratings.dat"""
        logger.info("Loading ratings...")
        
        ratings_file = os.path.join(data_dir, "ratings.dat")
        rating_count = 0
        
        with open(ratings_file, 'r', encoding='latin-1') as f:
            for line in f:
                parts = line.strip().split('::')
                if len(parts) >= 4:
                    ml_user_id = int(parts[0])
                    ml_movie_id = int(parts[1])
                    rating = float(parts[2])
                    timestamp = datetime.fromtimestamp(int(parts[3]))
                    
                    # Insert into staging table
                    self.db.execute(text("""
                        INSERT INTO ml_ratings (ml_user_id, ml_movie_id, rating, timestamp)
                        VALUES (:ml_user_id, :ml_movie_id, :rating, :timestamp)
                    """), {
                        'ml_user_id': ml_user_id,
                        'ml_movie_id': ml_movie_id,
                        'rating': rating,
                        'timestamp': timestamp
                    })
                    
                    rating_count += 1
                    
                    if rating_count % 100000 == 0:
                        logger.info(f"Loaded {rating_count} ratings...")
                        self.db.commit()
        
        self.db.commit()
        logger.info(f"Loaded {rating_count} ratings")
        return rating_count
    
    def map_movies_to_internal_ids(self) -> int:
        """Map MovieLens movie IDs to internal movie IDs via title matching"""
        logger.info("Mapping MovieLens movies to internal movies...")
        
        # Get all MovieLens movies
        ml_movies = self.db.execute(text("""
            SELECT ml_movie_id, title FROM ml_movies
            ORDER BY ml_movie_id
        """)).fetchall()
        
        # Get all internal movies
        internal_movies = self.db.query(Movie).all()
        internal_title_map = {movie.title.lower().strip(): movie.id for movie in internal_movies}
        
        mapped_count = 0
        
        for ml_movie_id, ml_title in ml_movies:
            # Clean title for matching
            clean_title = ml_title.lower().strip()
            
            # Try exact match first
            if clean_title in internal_title_map:
                internal_id = internal_title_map[clean_title]
                self.movie_id_mapping[ml_movie_id] = internal_id
                mapped_count += 1
                continue
            
            # Try removing year from title (e.g., "Toy Story (1995)" -> "Toy Story")
            if '(' in clean_title and ')' in clean_title:
                title_without_year = clean_title.split('(')[0].strip()
                if title_without_year in internal_title_map:
                    internal_id = internal_title_map[title_without_year]
                    self.movie_id_mapping[ml_movie_id] = internal_id
                    mapped_count += 1
                    continue
            
            # Try partial matching (first 20 characters)
            title_prefix = clean_title[:20]
            for internal_title, internal_id in internal_title_map.items():
                if internal_title.startswith(title_prefix):
                    self.movie_id_mapping[ml_movie_id] = internal_id
                    mapped_count += 1
                    break
        
        logger.info(f"Mapped {mapped_count} out of {len(ml_movies)} MovieLens movies")
        return mapped_count
    
    def create_arm_catalog_entries(self) -> int:
        """Create arm_catalog entries for MovieLens movies"""
        logger.info("Creating arm_catalog entries...")
        
        # Get mapped movies
        ml_movies = self.db.execute(text("""
            SELECT mm.ml_movie_id, mm.title, mm.genres
            FROM ml_movies mm
            WHERE mm.ml_movie_id IN :mapped_ids
        """), {'mapped_ids': list(self.movie_id_mapping.keys())}).fetchall()
        
        created_count = 0
        
        for ml_movie_id, title, genres in ml_movies:
            internal_id = self.movie_id_mapping[ml_movie_id]
            
            # Create arm catalog entry
            arm_id = f"ml_movie_{ml_movie_id}"
            metadata = {
                'ml_movie_id': ml_movie_id,
                'internal_movie_id': internal_id,
                'title': title,
                'genres': genres.split('|') if genres else [],
                'source': 'movielens_1m'
            }
            
            try:
                arm_catalog = ArmCatalog(
                    arm_id=arm_id,
                    title=f"MovieLens: {title}",
                    metadata=metadata
                )
                self.db.add(arm_catalog)
                created_count += 1
                
            except Exception as e:
                logger.warning(f"Failed to create arm catalog for {arm_id}: {e}")
        
        self.db.commit()
        logger.info(f"Created {created_count} arm_catalog entries")
        return created_count
    
    def get_dataset_statistics(self) -> Dict[str, any]:
        """Get statistics about the loaded dataset"""
        
        # User statistics
        user_stats = self.db.execute(text("""
            SELECT 
                COUNT(*) as total_users,
                COUNT(DISTINCT gender) as gender_count,
                AVG(age) as avg_age,
                COUNT(DISTINCT occupation) as occupation_count
            FROM ml_users
        """)).fetchone()
        
        # Movie statistics
        movie_stats = self.db.execute(text("""
            SELECT 
                COUNT(*) as total_movies,
                COUNT(DISTINCT genres) as genre_combinations
            FROM ml_movies
        """)).fetchone()
        
        # Rating statistics
        rating_stats = self.db.execute(text("""
            SELECT 
                COUNT(*) as total_ratings,
                AVG(rating) as avg_rating,
                MIN(timestamp) as earliest_rating,
                MAX(timestamp) as latest_rating,
                COUNT(DISTINCT ml_user_id) as active_users,
                COUNT(DISTINCT ml_movie_id) as rated_movies
            FROM ml_ratings
        """)).fetchone()
        
        # Mapping statistics
        mapped_movies = len(self.movie_id_mapping)
        total_movies = self.db.execute(text("SELECT COUNT(*) FROM ml_movies")).scalar()
        
        return {
            'users': {
                'total': user_stats.total_users,
                'genders': user_stats.gender_count,
                'avg_age': round(user_stats.avg_age, 1),
                'occupations': user_stats.occupation_count
            },
            'movies': {
                'total': movie_stats.total_movies,
                'genre_combinations': movie_stats.genre_combinations
            },
            'ratings': {
                'total': rating_stats.total_ratings,
                'avg_rating': round(rating_stats.avg_rating, 2),
                'earliest': rating_stats.earliest_rating,
                'latest': rating_stats.latest_rating,
                'active_users': rating_stats.active_users,
                'rated_movies': rating_stats.rated_movies
            },
            'mapping': {
                'mapped_movies': mapped_movies,
                'total_movies': total_movies,
                'mapping_rate': round(mapped_movies / total_movies * 100, 1) if total_movies > 0 else 0
            }
        }
    
    def cleanup_temp_files(self):
        """Clean up temporary files"""
        import shutil
        
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            logger.info("Cleaned up temporary files")

def main():
    """Main function to load MovieLens dataset"""
    logger.info("="*60)
    logger.info("MOVIELENS 1M DATA LOADER")
    logger.info("="*60)
    
    db = SessionLocal()
    loader = MovieLensLoader(db)
    
    try:
        # Download and extract dataset
        zip_path = loader.download_dataset()
        data_dir = loader.extract_dataset(zip_path)
        
        # Create staging tables
        loader.create_staging_tables()
        
        # Load data
        user_count = loader.load_users(data_dir)
        movie_count = loader.load_movies(data_dir)
        rating_count = loader.load_ratings(data_dir)
        
        # Map movies to internal IDs
        mapped_count = loader.map_movies_to_internal_ids()
        
        # Create arm catalog entries
        arm_count = loader.create_arm_catalog_entries()
        
        # Get statistics
        stats = loader.get_dataset_statistics()
        
        logger.info("="*60)
        logger.info("LOADING COMPLETE")
        logger.info("="*60)
        logger.info(f"Users loaded: {user_count:,}")
        logger.info(f"Movies loaded: {movie_count:,}")
        logger.info(f"Ratings loaded: {rating_count:,}")
        logger.info(f"Movies mapped: {mapped_count:,}")
        logger.info(f"Arm catalog entries: {arm_count:,}")
        logger.info("="*60)
        logger.info("DATASET STATISTICS:")
        logger.info(f"  Users: {stats['users']['total']:,} ({stats['users']['genders']} genders, avg age {stats['users']['avg_age']})")
        logger.info(f"  Movies: {stats['movies']['total']:,} ({stats['movies']['genre_combinations']} genre combinations)")
        logger.info(f"  Ratings: {stats['ratings']['total']:,} (avg {stats['ratings']['avg_rating']})")
        logger.info(f"  Time range: {stats['ratings']['earliest']} to {stats['ratings']['latest']}")
        logger.info(f"  Mapping rate: {stats['mapping']['mapping_rate']}%")
        logger.info("="*60)
        
        # Cleanup
        loader.cleanup_temp_files()
        
    except Exception as e:
        logger.error(f"Loading failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    main()
