"""
Comprehensive Evaluation Framework for Recommendation Systems
"""

import numpy as np
from sqlalchemy.orm import Session
from typing import List, Dict
import json
import logging
from datetime import datetime, timedelta

from ..models import Movie, RecommendationEvent

logger = logging.getLogger(__name__)


class RecommendationEvaluator:
    """Comprehensive evaluation framework"""
    
    def __init__(self, db: Session):
        self.db = db
        
    def evaluate_online_metrics(self, days: int = 30, algorithm: str = None) -> Dict[str, float]:
        """Calculate online evaluation metrics from live traffic"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        query = self.db.query(RecommendationEvent).filter(RecommendationEvent.created_at >= cutoff)
        if algorithm:
            query = query.filter(RecommendationEvent.algorithm == algorithm)
        
        events = query.all()
        
        if not events:
            return {'ctr': 0.0, 'avg_rating': 0.0}
        
        clicks = sum(1 for e in events if e.clicked)
        ratings = [e.rating_value for e in events if e.rated and e.rating_value]
        
        return {
            'ctr': clicks / len(events) if events else 0.0,
            'avg_rating': np.mean(ratings) if ratings else 0.0,
            'total_events': len(events)
        }
    
    def calculate_diversity_metrics(self, recommendations: List[Movie]) -> Dict[str, float]:
        """Calculate diversity metrics"""
        if not recommendations:
            return {
                'gini_coefficient': 0.0,
                'long_tail_percentage': 0.0,
                'genre_diversity': 0.0
            }
        
        long_tail = sum(1 for m in recommendations if (m.vote_count or 0) < 1000)
        
        all_genres = set()
        for movie in recommendations:
            if movie.genres:
                try:
                    genres = movie.genres if isinstance(movie.genres, list) else json.loads(movie.genres or '[]')
                    all_genres.update(genres)
                except:
                    pass
        
        return {
            'gini_coefficient': 0.0,
            'long_tail_percentage': long_tail / len(recommendations),
            'genre_diversity': len(all_genres) / len(recommendations) if recommendations else 0.0
        }

