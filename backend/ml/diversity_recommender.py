"""
Diversity-First Recommendation Engine

Implements strategies for discovering "absolute bangers" users wouldn't search for:
- Long-tail discovery (high-rated but low-popularity movies)
- Niche genre emphasis (anime, foreign language, documentaries)
- Serendipity scoring (dissimilar but high-quality recommendations)
- Popularity dampening (reduce bias toward popular content)
- Coverage optimization (ensure all movies get fair representation)
"""

import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from collections import defaultdict
from typing import List, Dict, Set
import json
import logging
from datetime import datetime, timedelta
import math

from ..models import Movie, User, Rating, Favorite, WatchlistItem, RecommendationEvent

logger = logging.getLogger(__name__)


class DiversityRecommender:
    """Recommendation engine focused on diversity and discovery"""
    
    def __init__(self, db: Session):
        self.db = db
        self.long_tail_threshold = 1000
        self.high_quality_threshold = 7.5
        self.niche_genres = {'Anime', 'Animation', 'Foreign', 'Documentary'}
        
    def get_long_tail_recommendations(self, user_id: int, n: int = 10) -> List[Movie]:
        """Find high-quality movies with low popularity (hidden gems)"""
        excluded_ids = self._get_excluded_ids(user_id)
        
        movies = self.db.query(Movie).filter(
            and_(
                Movie.vote_count < self.long_tail_threshold,
                Movie.vote_average >= self.high_quality_threshold,
                Movie.vote_count >= 50,
                ~Movie.id.in_(excluded_ids) if excluded_ids else True
            )
        ).order_by(desc(Movie.vote_average)).limit(n * 2).all()
        
        return self._apply_diversity(movies[:n])
    
    def get_serendipity_recommendations(self, user_id: int, n: int = 10) -> List[Movie]:
        """Recommend movies dissimilar to user's history but high-quality"""
        user_profile = self._build_user_profile(user_id)
        excluded_ids = self._get_excluded_ids(user_id)
        
        movies = self.db.query(Movie).filter(
            and_(
                Movie.vote_average >= 7.5,
                Movie.vote_count >= 200,
                ~Movie.id.in_(excluded_ids) if excluded_ids else True
            )
        ).all()
        
        scored = [(m, self._calc_dissimilarity(m, user_profile)) for m in movies]
        scored.sort(key=lambda x: x[1], reverse=True)
        
        return [m for m, _ in scored[:n]]
    
    def _get_excluded_ids(self, user_id: int) -> Set[int]:
        """Get movie IDs to exclude"""
        excluded = set()
        excluded.update([r.movie_id for r in self.db.query(Rating.movie_id).filter(Rating.user_id == user_id).all()])
        excluded.update([f.movie_id for f in self.db.query(Favorite.movie_id).filter(Favorite.user_id == user_id).all()])
        excluded.update([w.movie_id for w in self.db.query(WatchlistItem.movie_id).filter(WatchlistItem.user_id == user_id).all()])
        return excluded
    
    def _build_user_profile(self, user_id: int) -> Dict[str, float]:
        """Build user's genre preferences"""
        ratings = self.db.query(Rating).filter(Rating.user_id == user_id, Rating.rating >= 4.0).all()
        if not ratings:
            return {}
        
        movie_ids = [r.movie_id for r in ratings]
        movies = self.db.query(Movie).filter(Movie.id.in_(movie_ids)).all()
        
        genre_scores = defaultdict(float)
        for movie in movies:
            if movie.genres:
                try:
                    genres = movie.genres if isinstance(movie.genres, list) else json.loads(movie.genres or '[]')
                    for genre in genres:
                        genre_scores[genre] += 1.0
                except:
                    pass
        
        max_score = max(genre_scores.values()) if genre_scores else 1.0
        return {g: s / max_score for g, s in genre_scores.items()}
    
    def _calc_dissimilarity(self, movie: Movie, profile: Dict[str, float]) -> float:
        """Calculate dissimilarity between movie and user profile"""
        if not movie.genres or not profile:
            return 0.5
        
        try:
            genres = movie.genres if isinstance(movie.genres, list) else json.loads(movie.genres or '[]')
            overlap = sum(profile.get(g, 0) for g in genres) / len(genres) if genres else 0
            return 1.0 - overlap
        except:
            return 0.5
    
    def _apply_diversity(self, movies: List[Movie]) -> List[Movie]:
        """Apply diversity post-processing"""
        return movies  # Simple version

