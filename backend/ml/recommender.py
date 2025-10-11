import pandas as pd
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import desc
from ..models import Rating, Movie, User, Favorite, WatchlistItem
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.decomposition import TruncatedSVD
from scipy.sparse import csr_matrix
from collections import defaultdict
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)

# Try importing graph recommender
try:
    from ml.graph_recommender import (
        GraphRecommender,
        GRAPH_LEARNING_AVAILABLE
    )
except ImportError:
    GRAPH_LEARNING_AVAILABLE = False
    GraphRecommender = None
    logger.warning("Graph recommender not available")

class MovieRecommender:
    def __init__(self, db: Session):
        self.db = db
        self.cold_start_threshold = 3  # Users with < 3 interactions are "cold start"
        
        # Matrix Factorization configuration
        self.svd_components = 20  # Number of latent factors
        self.svd_min_ratings = 5  # Minimum ratings needed for SVD (lowered from 10)
        self._svd_model = None  # Cached SVD model
        self._svd_user_factors = None  # Cached user factors
        self._svd_item_factors = None  # Cached item factors
        self._svd_movie_ids = None  # Movie IDs in SVD model
        self._svd_user_ids = None  # User IDs in SVD model
    
    def _get_excluded_movie_ids(self, user_id: int):
        """Get set of movie IDs to exclude from recommendations"""
        from ..models import RecommendationEvent
        
        excluded_ids = set()
        
        # Exclude movies rated 2 stars or less
        low_ratings = self.db.query(Rating.movie_id).filter(
            Rating.user_id == user_id,
            Rating.rating <= 2.0
        ).all()
        excluded_ids.update([r[0] for r in low_ratings])
        
        # Exclude movies that received thumbs down
        thumbs_down_events = self.db.query(RecommendationEvent.movie_id).filter(
            RecommendationEvent.user_id == user_id,
            RecommendationEvent.thumbs_down == True
        ).all()
        excluded_ids.update([r[0] for r in thumbs_down_events])
        
        return excluded_ids
    
    def _get_thumbs_up_movie_ids(self, user_id: int):
        """Get movie IDs that received thumbs up from user"""
        from ..models import RecommendationEvent
        
        thumbs_up_events = self.db.query(RecommendationEvent.movie_id).filter(
            RecommendationEvent.user_id == user_id,
            RecommendationEvent.thumbs_up == True
        ).all()
        
        return [r[0] for r in thumbs_up_events]
    
    def _get_thumbs_down_movie_ids(self, user_id: int):
        """Get movie IDs that received thumbs down from user"""
        from ..models import RecommendationEvent
        
        thumbs_down_events = self.db.query(RecommendationEvent.movie_id).filter(
            RecommendationEvent.user_id == user_id,
            RecommendationEvent.thumbs_down == True
        ).all()
        
        return [r[0] for r in thumbs_down_events]
    
    def _get_similar_movie_ids(self, movie_ids: list, similarity_threshold: float = 0.7) -> set:
        """
        Get movie IDs similar to the given movies based on genre overlap and ratings
        
        Args:
            movie_ids: List of movie IDs to find similar movies for
            similarity_threshold: Minimum similarity score (0-1)
            
        Returns:
            Set of similar movie IDs
        """
        if not movie_ids:
            return set()
        
        similar_ids = set()
        
        # Get the movies we're comparing against
        reference_movies = self.db.query(Movie).filter(Movie.id.in_(movie_ids)).all()
        if not reference_movies:
            return set()
        
        # Extract genres from reference movies
        reference_genres = set()
        for movie in reference_movies:
            if movie.genres:
                try:
                    genres = movie.genres if isinstance(movie.genres, list) else json.loads(movie.genres)
                    reference_genres.update(genres)
                except:
                    pass
        
        if not reference_genres:
            return set()
        
        # Find movies with similar genres
        all_movies = self.db.query(Movie).filter(
            Movie.id.notin_(movie_ids),  # Exclude the reference movies themselves
            Movie.vote_count >= 50  # Only consider movies with sufficient ratings
        ).all()
        
        for movie in all_movies:
            if movie.genres:
                try:
                    genres = movie.genres if isinstance(movie.genres, list) else json.loads(movie.genres)
                    movie_genres = set(genres)
                    
                    # Calculate genre overlap similarity
                    if movie_genres:
                        overlap = len(reference_genres.intersection(movie_genres))
                        total_genres = len(reference_genres.union(movie_genres))
                        similarity = overlap / total_genres if total_genres > 0 else 0
                        
                        # Also consider rating similarity for movies with similar ratings
                        if movie.vote_average and any(ref.vote_average for ref in reference_movies):
                            avg_ref_rating = sum(ref.vote_average for ref in reference_movies if ref.vote_average) / len([ref for ref in reference_movies if ref.vote_average])
                            rating_diff = abs(movie.vote_average - avg_ref_rating)
                            rating_similarity = max(0, 1 - (rating_diff / 5.0))  # Normalize to 0-1
                            
                            # Combine genre and rating similarity
                            combined_similarity = (similarity * 0.7) + (rating_similarity * 0.3)
                        else:
                            combined_similarity = similarity
                        
                        if combined_similarity >= similarity_threshold:
                            similar_ids.add(movie.id)
                            
                except:
                    pass
        
        return similar_ids
    
    def _filter_similar_to_thumbs_down(self, movies: list, user_id: int) -> list:
        """
        Filter out movies similar to movies that received thumbs down
        
        Args:
            movies: List of Movie objects
            user_id: User ID
            
        Returns:
            Filtered list of movies without those similar to thumbs down movies
        """
        thumbs_down_ids = self._get_thumbs_down_movie_ids(user_id)
        
        if not thumbs_down_ids:
            return movies
        
        # Get movies similar to thumbs down movies
        similar_to_thumbs_down = self._get_similar_movie_ids(thumbs_down_ids, similarity_threshold=0.6)
        
        if not similar_to_thumbs_down:
            return movies
        
        # Filter out similar movies
        filtered_movies = [movie for movie in movies if movie.id not in similar_to_thumbs_down]
        
        logger.info(f"Filtered out {len(movies) - len(filtered_movies)} movies similar to thumbs down movies")
        
        return filtered_movies
    
    def _boost_similar_to_thumbs_up(self, movies: list, user_id: int) -> list:
        """
        Boost movies similar to movies that received thumbs up
        
        Args:
            movies: List of Movie objects
            user_id: User ID
            
        Returns:
            Reordered list with similar movies boosted
        """
        thumbs_up_ids = self._get_thumbs_up_movie_ids(user_id)
        
        if not thumbs_up_ids:
            return movies
        
        # Get movies similar to thumbs up movies
        similar_to_thumbs_up = self._get_similar_movie_ids(thumbs_up_ids, similarity_threshold=0.5)
        
        if not similar_to_thumbs_up:
            return movies
        
        # Score movies based on similarity to thumbs up movies
        movie_scores = []
        for movie in movies:
            score = 1.0  # Base score
            
            # Boost if similar to thumbs up movies
            if movie.id in similar_to_thumbs_up:
                score += 2.0  # Significant boost for similarity to thumbs up
            
            movie_scores.append((movie, score))
        
        # Sort by score (descending)
        movie_scores.sort(key=lambda x: x[1], reverse=True)
        
        boosted_movies = [movie for movie, _ in movie_scores]
        
        logger.info(f"Boosted {len(similar_to_thumbs_up)} movies similar to thumbs up movies")
        
        return boosted_movies
    
    def _filter_disliked_genres(self, movies: list, user_id: int) -> list:
        """
        Filter out movies from genres the user explicitly disliked in onboarding
        
        Args:
            movies: List of Movie objects
            user_id: User ID
            
        Returns:
            Filtered list of movies without disliked genres
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        
        if not user or not user.genre_preferences:
            return movies  # No preferences to filter by
        
        try:
            # Get disliked genres (score < 0)
            genre_prefs = user.genre_preferences if isinstance(user.genre_preferences, dict) else json.loads(user.genre_preferences)
            disliked_genres = {genre for genre, score in genre_prefs.items() if score < 0}
            
            if not disliked_genres:
                return movies  # No disliked genres
            
            # Filter out movies that contain ANY disliked genre
            filtered_movies = []
            for movie in movies:
                if movie.genres:
                    try:
                        genres = movie.genres if isinstance(movie.genres, list) else json.loads(movie.genres)
                        movie_genre_set = set(genres)
                        
                        # Only include if movie has NO disliked genres
                        if not movie_genre_set.intersection(disliked_genres):
                            filtered_movies.append(movie)
                    except:
                        # If genre parsing fails, include the movie (benefit of doubt)
                        filtered_movies.append(movie)
                else:
                    # If no genres listed, include the movie
                    filtered_movies.append(movie)
            
            # Always return filtered list, even if empty
            # The recommendation system will handle backfilling if needed
            if len(movies) - len(filtered_movies) > 0:
                logger.info(f"Filtered {len(movies) - len(filtered_movies)} movies with disliked genres: {disliked_genres}")
            
            if not filtered_movies:
                logger.warning(f"Genre filtering removed ALL {len(movies)} movies. User may need more diverse recommendations.")
            
            return filtered_movies
                
        except Exception as e:
            logger.error(f"Error filtering disliked genres: {e}")
            return movies  # Return unfiltered on error
        
    def get_user_based_recommendations(self, user_id: int, n_recommendations: int = 10):
        """Collaborative filtering with implicit feedback"""
        
        # Get all interactions (ratings, favorites, watchlist)
        ratings = self.db.query(Rating).all()
        favorites = self.db.query(Favorite).all()
        watchlist = self.db.query(WatchlistItem).all()
        
        if len(ratings) < 3:
            return self._get_popular_movies(n_recommendations, user_id)
        
        # Create user-item matrix with weighted signals
        user_ratings = defaultdict(dict)
        
        # Explicit ratings (weight: 1.0)
        for rating in ratings:
            user_ratings[rating.user_id][rating.movie_id] = rating.rating
        
        # Favorites (implicit signal: 4.5 stars if no rating exists)
        for fav in favorites:
            if fav.movie_id not in user_ratings[fav.user_id]:
                user_ratings[fav.user_id][fav.movie_id] = 4.5
        
        # Watchlist (implicit signal: 3.5 stars if no rating exists)  
        for item in watchlist:
            if item.movie_id not in user_ratings[item.user_id]:
                user_ratings[item.user_id][item.movie_id] = 3.5
        
        # Convert to DataFrame
        df = pd.DataFrame(user_ratings).T.fillna(0)
        
        if user_id not in df.index:
            return self._get_popular_movies(n_recommendations, user_id)
        
        # Calculate user similarity
        user_similarity = cosine_similarity(df)
        user_similarity_df = pd.DataFrame(
            user_similarity, 
            index=df.index, 
            columns=df.index
        )
        
        # Get similar users
        similar_users = user_similarity_df[user_id].sort_values(ascending=False)[1:11]
        
        # Get movies to exclude
        excluded_ids = self._get_excluded_movie_ids(user_id)
        
        # Get movies from similar users
        user_movies = set(df.loc[user_id][df.loc[user_id] > 0].index)
        recommendations = {}
        
        for sim_user_id, similarity in similar_users.items():
            if similarity <= 0:
                continue
                
            sim_user_movies = df.loc[sim_user_id][df.loc[sim_user_id] > 0]
            
            for movie_id, rating in sim_user_movies.items():
                # Skip if movie is in user's library or excluded (low-rated)
                if movie_id not in user_movies and movie_id not in excluded_ids:
                    if movie_id not in recommendations:
                        recommendations[movie_id] = 0
                    recommendations[movie_id] += rating * similarity
        
        # Sort recommendations
        top_movie_ids = sorted(
            recommendations.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:n_recommendations]
        
        # Fetch movies
        movie_ids = [int(movie_id) for movie_id, _ in top_movie_ids]
        movies = self.db.query(Movie).filter(Movie.id.in_(movie_ids)).all()
        
        movie_dict = {m.id: m for m in movies}
        recommended_movies = [movie_dict[mid] for mid, _ in top_movie_ids if mid in movie_dict]
        
        return recommended_movies
    
    def get_content_based_recommendations(self, user_id: int, n_recommendations: int = 10):
        """Content-based using genres from all user interactions AND stated preferences"""
        
        # Get user for onboarding preferences
        user = self.db.query(User).filter(User.id == user_id).first()
        
        # Get all user interactions
        user_ratings = self.db.query(Rating).filter(Rating.user_id == user_id).all()
        user_favorites = self.db.query(Favorite).filter(Favorite.user_id == user_id).all()
        user_watchlist = self.db.query(WatchlistItem).filter(WatchlistItem.user_id == user_id).all()
        
        # Collect movie IDs with weights
        liked_movie_ids = []
        
        # High-rated movies (4+ stars)
        for r in user_ratings:
            if r.rating >= 4.0:
                liked_movie_ids.append((r.movie_id, 1.0))
        
        # Favorites
        for f in user_favorites:
            if not any(mid == f.movie_id for mid, _ in liked_movie_ids):
                liked_movie_ids.append((f.movie_id, 0.8))
        
        # Watchlist
        for w in user_watchlist:
            if not any(mid == w.movie_id for mid, _ in liked_movie_ids):
                liked_movie_ids.append((w.movie_id, 0.5))
        
        if not liked_movie_ids and not (user and user.genre_preferences):
            return self._get_popular_movies(n_recommendations, user_id)
        
        # Get movies and count genres with weights (from actual ratings)
        genre_scores = defaultdict(float)
        
        if liked_movie_ids:
            movie_ids = [mid for mid, _ in liked_movie_ids]
            liked_movies = self.db.query(Movie).filter(Movie.id.in_(movie_ids)).all()
            
            # Use square root dampening on rating-based genres
            import math
            genre_counts = defaultdict(int)
            for movie in liked_movies:
                if movie.genres:
                    try:
                        import json
                        genres = json.loads(movie.genres) if isinstance(movie.genres, str) else movie.genres
                        for genre in genres:
                            genre_counts[genre] += 1
                    except:
                        pass
            
            # Apply dampening
            for genre, count in genre_counts.items():
                genre_scores[genre] += math.sqrt(count) * 0.3  # Dampened weight
        
        # Add explicit genre preferences with STRONG weight
        if user and user.genre_preferences:
            try:
                import json
                prefs = user.genre_preferences if isinstance(user.genre_preferences, dict) else json.loads(user.genre_preferences)
                for genre, score in prefs.items():
                    if score > 0:
                        # Positive preferences get strong boost
                        genre_scores[genre] += score * 3.0  # Much stronger than rated movies
            except:
                pass
        
        # Get top genres (now includes stated preferences!)
        top_genres = sorted(genre_scores.items(), key=lambda x: x[1], reverse=True)[:5]  # Increased from 3 to 5
        top_genre_names = [g[0] for g in top_genres]
        
        if not top_genre_names:
            return self._get_popular_movies(n_recommendations, user_id)
        
        # Get movies to exclude
        excluded_ids = self._get_excluded_movie_ids(user_id)
        
        # Get disliked genres for early filtering
        disliked_genres = set()
        if user and user.genre_preferences:
            try:
                import json
                prefs = user.genre_preferences if isinstance(user.genre_preferences, dict) else json.loads(user.genre_preferences)
                disliked_genres = {genre for genre, score in prefs.items() if score < 0}
            except:
                pass
        
        # Find similar movies
        all_movies = self.db.query(Movie).filter(Movie.vote_count >= 50).all()
        recommendations = []
        
        # Build complete set of movies to exclude (all rated, favorites, watchlist)
        seen_movie_ids = set(movie_ids) if 'movie_ids' in locals() else set()
        # Add ALL rated movies (not just high-rated ones)
        all_rated_ids = [r.movie_id for r in user_ratings]
        seen_movie_ids.update(all_rated_ids)
        
        for movie in all_movies:
            # Skip if already seen or excluded (low-rated)
            if movie.id not in seen_movie_ids and movie.id not in excluded_ids:
                try:
                    import json
                    genres = json.loads(movie.genres) if isinstance(movie.genres, str) else movie.genres
                    
                    # EARLY FILTER: Skip if movie contains disliked genres
                    if disliked_genres and disliked_genres.intersection(set(genres)):
                        continue
                    
                    overlap = len(set(genres) & set(top_genre_names))
                    if overlap > 0:
                        # Score based on genre overlap and rating
                        score = overlap * 2 + (movie.vote_average or 0) / 2
                        recommendations.append((movie, score))
                except:
                    pass
        
        recommendations.sort(key=lambda x: x[1], reverse=True)
        
        return [movie for movie, _ in recommendations[:n_recommendations]]
    
    def _get_popular_movies(self, n: int = 10, exclude_user_id: int = None):
        """Fallback: return popular movies user hasn't seen (ultra-optimized)"""
        # Ultra-simple query for maximum performance
        query = self.db.query(Movie).filter(
            Movie.vote_count >= 500,  # Higher threshold for better movies
            Movie.vote_average >= 7.0  # Only very high-rated movies
        )
        
        if exclude_user_id:
            # Get seen movie IDs more efficiently
            seen_ids = self._get_excluded_movie_ids(exclude_user_id)
            if seen_ids:
                query = query.filter(~Movie.id.in_(seen_ids))
        
        return query.order_by(Movie.popularity.desc()).limit(n).all()
    
    def _is_cold_start_user(self, user_id: int) -> bool:
        """Check if user has insufficient data (cold start problem)"""
        # Count total interactions
        ratings_count = self.db.query(Rating).filter(Rating.user_id == user_id).count()
        favorites_count = self.db.query(Favorite).filter(Favorite.user_id == user_id).count()
        watchlist_count = self.db.query(WatchlistItem).filter(WatchlistItem.user_id == user_id).count()
        
        total_interactions = ratings_count + favorites_count + watchlist_count
        return total_interactions < self.cold_start_threshold
    
    def _get_contextual_features(self, user_id: int) -> dict:
        """
        Extract contextual features for context-aware recommendations
        
        Returns:
            dict: Contains temporal patterns, recent genres, and diversity metrics
        """
        context = {
            'temporal': {},
            'recent_genres': set(),
            'genre_saturation': {},
            'sequential_patterns': []
        }
        
        # 1. Temporal patterns
        now = datetime.now()
        context['temporal']['hour'] = now.hour
        context['temporal']['day_of_week'] = now.weekday()  # 0=Monday, 6=Sunday
        context['temporal']['is_weekend'] = now.weekday() >= 5
        context['temporal']['time_period'] = self._get_time_period(now.hour)
        
        # 2. Sequential patterns (recent viewing history)
        recent_ratings = self.db.query(Rating).filter(
            Rating.user_id == user_id
        ).order_by(desc(Rating.timestamp)).limit(10).all()
        
        if recent_ratings:
            # Get the 5 most recent ratings
            recent_views = recent_ratings[:5]
            context['sequential_patterns'] = [
                {
                    'movie_id': r.movie_id,
                    'rating': r.rating,
                    'timestamp': r.timestamp
                }
                for r in recent_views
            ]
            
            # 3. Extract recent genres for diversity calculation
            recent_movie_ids = [r.movie_id for r in recent_ratings]
            recent_movies = self.db.query(Movie).filter(Movie.id.in_(recent_movie_ids)).all()
            
            genre_count = defaultdict(int)
            for movie in recent_movies:
                if movie.genres:
                    try:
                        genres = movie.genres if isinstance(movie.genres, list) else json.loads(movie.genres)
                        for genre in genres:
                            context['recent_genres'].add(genre)
                            genre_count[genre] += 1
                    except:
                        pass
            
            # 4. Calculate genre saturation (how much of each genre user has seen recently)
            total_recent = len(recent_movies)
            if total_recent > 0:
                context['genre_saturation'] = {
                    genre: count / total_recent 
                    for genre, count in genre_count.items()
                }
        
        return context
    
    def _get_time_period(self, hour: int) -> str:
        """Categorize time of day into periods"""
        if 5 <= hour < 12:
            return 'morning'
        elif 12 <= hour < 17:
            return 'afternoon'
        elif 17 <= hour < 21:
            return 'evening'
        else:
            return 'night'
    
    def _apply_diversity_boost(self, movies: list, context: dict, boost_factor: float = 1.3) -> list:
        """
        Apply diversity boosting to recommendations
        Boost movies from underrepresented genres
        
        Args:
            movies: List of movie objects
            context: Context dict from _get_contextual_features
            boost_factor: Multiplier for underrepresented genres (default: 1.3)
        
        Returns:
            Reordered list of movies with diversity boost applied
        """
        if not context['recent_genres']:
            return movies  # No recent history, no diversity needed
        
        recent_genres = context['recent_genres']
        genre_saturation = context['genre_saturation']
        
        # Score each movie based on genre diversity
        movie_scores = []
        for movie in movies:
            diversity_score = 0.0
            
            if movie.genres:
                try:
                    genres = movie.genres if isinstance(movie.genres, list) else json.loads(movie.genres)
                    movie_genre_set = set(genres)
                    
                    # Calculate diversity score
                    # Higher score if movie has genres NOT in recent viewing
                    new_genres = movie_genre_set - recent_genres
                    diversity_score += len(new_genres) * boost_factor
                    
                    # Penalize oversaturated genres
                    for genre in movie_genre_set:
                        if genre in genre_saturation:
                            saturation = genre_saturation[genre]
                            # Higher saturation = lower score
                            diversity_score -= saturation * 0.5
                    
                    # Bonus for introducing completely new genres
                    if len(new_genres) > 0:
                        diversity_score += 1.0
                    
                except:
                    pass
            
            movie_scores.append((movie, diversity_score))
        
        # Sort by diversity score (descending)
        movie_scores.sort(key=lambda x: x[1], reverse=True)
        
        # Return reordered list
        return [movie for movie, _ in movie_scores]
    
    def _apply_temporal_filtering(self, movies: list, context: dict) -> list:
        """
        Apply temporal filtering based on time of day and day of week
        Adjust recommendations based on viewing context
        
        Args:
            movies: List of movie objects
            context: Context dict with temporal information
        
        Returns:
            Filtered/reordered list of movies
        """
        time_period = context['temporal'].get('time_period', 'evening')
        is_weekend = context['temporal'].get('is_weekend', False)
        
        # Define genre preferences by time period
        time_genre_preferences = {
            'morning': ['Animation', 'Family', 'Comedy', 'Adventure'],
            'afternoon': ['Action', 'Adventure', 'Comedy', 'Science Fiction'],
            'evening': ['Drama', 'Thriller', 'Mystery', 'Crime'],
            'night': ['Horror', 'Thriller', 'Mystery', 'Science Fiction']
        }
        
        # Weekend vs weekday preferences
        if is_weekend:
            # Longer, more epic movies on weekends
            preferred_genres = ['Action', 'Adventure', 'Science Fiction', 'Fantasy', 'Drama']
        else:
            # Shorter, lighter content on weekdays
            preferred_genres = ['Comedy', 'Animation', 'Romance', 'Documentary']
        
        # Get time-specific preferences
        time_preferences = time_genre_preferences.get(time_period, [])
        
        # Score movies based on temporal relevance
        movie_scores = []
        for movie in movies:
            temporal_score = 0.0
            
            if movie.genres:
                try:
                    genres = movie.genres if isinstance(movie.genres, list) else json.loads(movie.genres)
                    
                    # Boost if matches time period preferences
                    for genre in genres:
                        if genre in time_preferences:
                            temporal_score += 1.0
                        if genre in preferred_genres:
                            temporal_score += 0.5
                    
                    # Runtime consideration (if available)
                    if hasattr(movie, 'runtime') and movie.runtime:
                        if is_weekend and movie.runtime > 120:
                            temporal_score += 0.5  # Boost longer movies on weekends
                        elif not is_weekend and movie.runtime <= 120:
                            temporal_score += 0.3  # Boost shorter movies on weekdays
                    
                except:
                    pass
            
            movie_scores.append((movie, temporal_score))
        
        # Sort by temporal score (descending) while maintaining some original order
        # Mix of temporal relevance and original ranking
        movie_scores.sort(key=lambda x: x[1], reverse=True)
        
        return [movie for movie, _ in movie_scores]
    
    def _build_svd_model(self):
        """
        Build SVD model from all ratings data
        Uses matrix factorization to discover latent factors
        """
        try:
            # Get all ratings
            all_ratings = self.db.query(Rating).all()
            
            if len(all_ratings) < self.svd_min_ratings:
                logger.warning(f"Not enough ratings ({len(all_ratings)}) for SVD. Need at least {self.svd_min_ratings}")
                return False
            
            # Create user-item rating matrix
            user_item_data = defaultdict(lambda: defaultdict(float))
            for rating in all_ratings:
                user_item_data[rating.user_id][rating.movie_id] = rating.rating
            
            # Convert to DataFrame
            df = pd.DataFrame(user_item_data).T.fillna(0)
            
            if df.empty or len(df) < 2:
                logger.warning("Insufficient data for SVD model")
                return False
            
            # Store user and movie IDs
            self._svd_user_ids = list(df.index)
            self._svd_movie_ids = list(df.columns)
            
            # Convert to sparse matrix for efficiency
            sparse_matrix = csr_matrix(df.values)
            
            # Determine number of components (can't exceed matrix dimensions)
            n_components = min(self.svd_components, min(sparse_matrix.shape) - 1)
            
            if n_components < 2:
                logger.warning("Matrix too small for SVD")
                return False
            
            # Perform SVD
            svd = TruncatedSVD(n_components=n_components, random_state=42)
            self._svd_user_factors = svd.fit_transform(sparse_matrix)
            self._svd_item_factors = svd.components_.T
            self._svd_model = svd
            
            logger.info(f"SVD model built successfully with {n_components} components")
            logger.info(f"Explained variance ratio: {svd.explained_variance_ratio_.sum():.2%}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error building SVD model: {e}")
            return False
    
    def get_svd_recommendations(self, user_id: int, n_recommendations: int = 10):
        """
        Matrix Factorization recommendations using SVD
        
        SVD decomposes the user-item matrix into latent factors, capturing
        hidden patterns in user preferences and movie characteristics.
        
        Benefits over simple cosine similarity:
        - Handles sparsity better
        - Discovers latent features (e.g., "action-comedy blend")
        - More accurate predictions
        - Better scalability
        """
        # Build or use cached SVD model
        if self._svd_model is None:
            if not self._build_svd_model():
                # Fall back to item-based CF if SVD fails
                logger.warning("SVD model unavailable, falling back to item-based CF")
                return self.get_item_based_recommendations(user_id, n_recommendations)
        
        # Check if user exists in the model
        if user_id not in self._svd_user_ids:
            # For new users not in training data, fall back
            logger.info(f"User {user_id} not in SVD model, falling back")
            return self.get_item_based_recommendations(user_id, n_recommendations)
        
        try:
            # Get user's latent factors
            user_idx = self._svd_user_ids.index(user_id)
            user_factors = self._svd_user_factors[user_idx]
            
            # Calculate predicted ratings for all movies
            predicted_ratings = np.dot(user_factors, self._svd_item_factors.T)
            
            # Get movies to exclude (already seen/rated)
            excluded_ids = self._get_excluded_movie_ids(user_id)
            user_ratings = self.db.query(Rating).filter(Rating.user_id == user_id).all()
            user_favorites = self.db.query(Favorite).filter(Favorite.user_id == user_id).all()
            user_watchlist = self.db.query(WatchlistItem).filter(WatchlistItem.user_id == user_id).all()
            
            seen_movie_ids = set([r.movie_id for r in user_ratings] + 
                                 [f.movie_id for f in user_favorites] + 
                                 [w.movie_id for w in user_watchlist])
            seen_movie_ids.update(excluded_ids)
            
            # Sort movies by predicted rating
            movie_scores = []
            for idx, movie_id in enumerate(self._svd_movie_ids):
                if movie_id not in seen_movie_ids:
                    movie_scores.append((movie_id, predicted_ratings[idx]))
            
            # Sort by predicted rating
            movie_scores.sort(key=lambda x: x[1], reverse=True)
            top_movie_ids = [movie_id for movie_id, _ in movie_scores[:n_recommendations]]
            
            # Fetch movies from database
            movies = self.db.query(Movie).filter(Movie.id.in_(top_movie_ids)).all()
            
            # Maintain order by score
            movie_dict = {m.id: m for m in movies}
            recommended_movies = [movie_dict[mid] for mid in top_movie_ids if mid in movie_dict]
            
            logger.info(f"SVD recommendations generated for user {user_id}: {len(recommended_movies)} movies")
            
            return recommended_movies
            
        except Exception as e:
            logger.error(f"Error generating SVD recommendations: {e}")
            # Fall back to item-based CF
            return self.get_item_based_recommendations(user_id, n_recommendations)
    
    def invalidate_svd_cache(self):
        """Invalidate cached SVD model (call when ratings are updated)"""
        self._svd_model = None
        self._svd_user_factors = None
        self._svd_item_factors = None
        self._svd_movie_ids = None
        self._svd_user_ids = None
        logger.info("SVD cache invalidated")
    
    def get_item_based_recommendations(self, user_id: int, n_recommendations: int = 10):
        """
        Item-based collaborative filtering - better for sparse data
        Recommends movies similar to ones the user has liked
        """
        # Get user's liked movies (ratings >= 4.0)
        user_ratings = self.db.query(Rating).filter(
            Rating.user_id == user_id,
            Rating.rating >= 4.0
        ).all()
        
        if not user_ratings:
            # Fall back to favorites
            user_favorites = self.db.query(Favorite).filter(Favorite.user_id == user_id).all()
            if not user_favorites:
                return self._get_popular_movies(n_recommendations, user_id)
            liked_movie_ids = [f.movie_id for f in user_favorites]
        else:
            liked_movie_ids = [r.movie_id for r in user_ratings]
        
        # Get all ratings in the system
        all_ratings = self.db.query(Rating).all()
        
        if len(all_ratings) < 10:
            return self._get_popular_movies(n_recommendations, user_id)
        
        # Create item-user matrix
        item_ratings = defaultdict(dict)
        for rating in all_ratings:
            item_ratings[rating.movie_id][rating.user_id] = rating.rating
        
        # Convert to DataFrame for similarity calculation
        df = pd.DataFrame(item_ratings).T.fillna(0)
        
        if df.empty or len(df) < 2:
            return self._get_popular_movies(n_recommendations, user_id)
        
        # Calculate item similarity
        item_similarity = cosine_similarity(df)
        item_similarity_df = pd.DataFrame(
            item_similarity,
            index=df.index,
            columns=df.index
        )
        
        # Find similar items to user's liked movies
        movie_scores = defaultdict(float)
        excluded_ids = self._get_excluded_movie_ids(user_id)
        seen_movie_ids = set(liked_movie_ids)
        
        for movie_id in liked_movie_ids:
            if movie_id not in item_similarity_df.index:
                continue
            
            # Get similar movies
            similar_movies = item_similarity_df[movie_id].sort_values(ascending=False)[1:21]
            
            for similar_movie_id, similarity in similar_movies.items():
                if similar_movie_id not in seen_movie_ids and similar_movie_id not in excluded_ids:
                    movie_scores[similar_movie_id] += similarity
        
        # Sort by score
        top_movie_ids = sorted(
            movie_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:n_recommendations]
        
        # Fetch movies
        movie_ids = [int(movie_id) for movie_id, _ in top_movie_ids]
        movies = self.db.query(Movie).filter(Movie.id.in_(movie_ids)).all()
        
        movie_dict = {m.id: m for m in movies}
        recommended_movies = [movie_dict[mid] for mid, _ in top_movie_ids if mid in movie_dict]
        
        return recommended_movies
    
    def get_demographic_recommendations(self, user_id: int, n_recommendations: int = 10):
        """
        Demographic-based recommendations for cold start users
        Uses age and location to find similar users' preferences
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            return self._get_popular_movies(n_recommendations, user_id)
        
        # Find similar users by demographics
        similar_users_query = self.db.query(User).filter(User.id != user_id)
        
        # Filter by age range (±5 years)
        if user.age:
            similar_users_query = similar_users_query.filter(
                User.age.between(user.age - 5, user.age + 5)
            )
        
        # Filter by location
        if user.location:
            similar_users_query = similar_users_query.filter(User.location == user.location)
        
        similar_users = similar_users_query.limit(20).all()
        
        if not similar_users:
            return self._get_popular_movies(n_recommendations, user_id)
        
        # Get highly-rated movies from similar users
        similar_user_ids = [u.id for u in similar_users]
        top_rated = self.db.query(Rating).filter(
            Rating.user_id.in_(similar_user_ids),
            Rating.rating >= 4.0
        ).all()
        
        # Score movies by frequency and average rating
        movie_scores = defaultdict(lambda: {'count': 0, 'total_rating': 0})
        for rating in top_rated:
            movie_scores[rating.movie_id]['count'] += 1
            movie_scores[rating.movie_id]['total_rating'] += rating.rating
        
        # Calculate weighted scores
        scored_movies = []
        excluded_ids = self._get_excluded_movie_ids(user_id)
        
        for movie_id, scores in movie_scores.items():
            if movie_id not in excluded_ids:
                avg_rating = scores['total_rating'] / scores['count']
                # Weight by both frequency and average rating
                score = scores['count'] * avg_rating
                scored_movies.append((movie_id, score))
        
        # Sort by score
        scored_movies.sort(key=lambda x: x[1], reverse=True)
        top_movie_ids = [movie_id for movie_id, _ in scored_movies[:n_recommendations]]
        
        # Fetch movies
        movies = self.db.query(Movie).filter(Movie.id.in_(top_movie_ids)).all()
        
        if not movies:
            return self._get_popular_movies(n_recommendations, user_id)
        
        # Filter out disliked genres early
        user = self.db.query(User).filter(User.id == user_id).first()
        if user and user.genre_preferences:
            try:
                import json
                prefs = user.genre_preferences if isinstance(user.genre_preferences, dict) else json.loads(user.genre_preferences)
                disliked_genres = {genre for genre, score in prefs.items() if score < 0}
                
                if disliked_genres:
                    filtered_movies = []
                    for movie in movies:
                        if movie.genres:
                            try:
                                genres = movie.genres if isinstance(movie.genres, list) else json.loads(movie.genres)
                                # Skip if contains disliked genre
                                if not disliked_genres.intersection(set(genres)):
                                    filtered_movies.append(movie)
                            except:
                                filtered_movies.append(movie)
                        else:
                            filtered_movies.append(movie)
                    movies = filtered_movies
            except:
                pass
        
        # Sort movies by the score order
        movie_dict = {m.id: m for m in movies}
        return [movie_dict[mid] for mid in top_movie_ids if mid in movie_dict]
    
    def get_genre_based_recommendations(self, user_id: int, n_recommendations: int = 10):
        """
        Genre-based recommendations using user's genre preferences
        Good for users who completed onboarding quiz
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        
        if not user or not user.genre_preferences:
            return self._get_popular_movies(n_recommendations, user_id)
        
        # Get preferred genres (positive scores)
        try:
            import json
            genre_prefs = user.genre_preferences if isinstance(user.genre_preferences, dict) else json.loads(user.genre_preferences)
            preferred_genres = [genre for genre, score in genre_prefs.items() if score > 0]
        except:
            return self._get_popular_movies(n_recommendations, user_id)
        
        if not preferred_genres:
            return self._get_popular_movies(n_recommendations, user_id)
        
        # Get movies from preferred genres
        excluded_ids = self._get_excluded_movie_ids(user_id)
        all_movies = self.db.query(Movie).filter(Movie.vote_count >= 50).all()
        
        scored_movies = []
        for movie in all_movies:
            if movie.id in excluded_ids:
                continue
            
            try:
                import json
                genres = movie.genres if isinstance(movie.genres, list) else json.loads(movie.genres) if movie.genres else []
                
                # Calculate genre overlap score
                overlap = len(set(genres) & set(preferred_genres))
                if overlap > 0:
                    # Score based on genre match, popularity, and rating
                    score = overlap * 3 + (movie.vote_average or 0) + (movie.popularity or 0) / 100
                    scored_movies.append((movie, score))
            except:
                continue
        
        # Sort by score
        scored_movies.sort(key=lambda x: x[1], reverse=True)
        return [movie for movie, _ in scored_movies[:n_recommendations]]
    
    def get_embedding_recommendations(self, user_id: int, n_recommendations: int = 10):
        """
        Get recommendations using deep learning embeddings
        
        Prioritizes pgvector-based recommendations (database-backed) for speed.
        Falls back to BERT+ResNet embeddings or SVD if unavailable.
        
        Args:
            user_id: User ID
            n_recommendations: Number of recommendations to return
        
        Returns:
            List of Movie objects
        """
        try:
            # Try pgvector first (fastest, database-backed)
            from ml.pgvector_recommender import PgvectorRecommender
            
            pgvector_rec = PgvectorRecommender(self.db)
            recommendations = pgvector_rec.get_recommendations(
                user_id,
                n_recommendations,
                diversity_boost=0.2
            )
            
            if recommendations:
                # Apply genre filtering
                recommendations = self._filter_disliked_genres(recommendations, user_id)
                logger.info(f"Generated {len(recommendations)} pgvector-based recommendations for user {user_id}")
                return recommendations
            
        except Exception as e:
            logger.warning(f"pgvector recommender failed: {e}, trying fallback")
        
        # Fallback to original embedding recommender
        try:
            from ml.embedding_recommender import EmbeddingRecommender, DEEP_LEARNING_AVAILABLE
            
            if not DEEP_LEARNING_AVAILABLE:
                logger.warning("Deep learning libraries not available, falling back to SVD")
                return self.get_svd_recommendations(user_id, n_recommendations)
            
            # Initialize recommender (will reuse cache)
            embedding_rec = EmbeddingRecommender(self.db)
            
            # Get recommendations
            recommendations = embedding_rec.get_embedding_recommendations(
                user_id, 
                n_recommendations
            )
            
            # Apply genre filtering
            recommendations = self._filter_disliked_genres(recommendations, user_id)
            
            logger.info(f"Generated {len(recommendations)} embedding-based recommendations for user {user_id}")
            return recommendations
            
        except ImportError as e:
            logger.warning(f"Embedding recommender not available: {e}, falling back to SVD")
            return self.get_svd_recommendations(user_id, n_recommendations)
        except Exception as e:
            logger.error(f"Error in embedding recommendations: {e}, falling back to SVD")
            return self.get_svd_recommendations(user_id, n_recommendations)
    
    def get_graph_recommendations(self, user_id: int, n_recommendations: int = 10):
        """
        Get recommendations using graph-based learning (Node2Vec/GNN)
        
        Uses knowledge graph structure to discover non-obvious connections:
        - Nodes: Movies, Users, Actors, Genres, Directors
        - Edges: Ratings, Cast, Genre membership
        - Method: Node2Vec embeddings in graph space
        
        Args:
            user_id: User ID to generate recommendations for
            n_recommendations: Number of recommendations to return
            
        Returns:
            List of recommended Movie objects
        """
        
        if not GRAPH_LEARNING_AVAILABLE or GraphRecommender is None:
            logger.warning("Graph recommender not available, falling back to SVD")
            return self.get_svd_recommendations(user_id, n_recommendations)
        
        try:
            # Initialize graph recommender
            graph_rec = GraphRecommender(self.db)
            
            # Get recommendations
            recommendations = graph_rec.get_graph_recommendations(
                user_id,
                n_recommendations
            )
            
            # Apply genre filtering
            recommendations = self._filter_disliked_genres(recommendations, user_id)
            
            logger.info(f"Generated {len(recommendations)} graph-based recommendations for user {user_id}")
            return recommendations
            
        except Exception as e:
            logger.error(f"Error in graph recommendations: {e}, falling back to SVD")
            return self.get_svd_recommendations(user_id, n_recommendations)
    
    def get_hybrid_recommendations(self, user_id: int, n_recommendations: int = 10, 
                                   use_context: bool = True, use_embeddings: bool = False,
                                   use_graph: bool = False):
        """
        Intelligent hybrid recommendations with cold start handling and context-awareness
        Automatically selects best strategy based on user data
        
        Args:
            user_id: User ID to generate recommendations for
            n_recommendations: Number of recommendations to return
            use_context: Whether to apply contextual filtering (temporal, diversity)
            use_embeddings: Whether to use deep learning embeddings
            use_graph: Whether to use graph-based recommendations
        
        Returns:
            List of recommended Movie objects
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        
        # Extract contextual features
        context = None
        if use_context:
            context = self._get_contextual_features(user_id)
            logger.info(f"Context for user {user_id}: {context['temporal']['time_period']}, "
                       f"weekend={context['temporal']['is_weekend']}, "
                       f"recent_genres={len(context['recent_genres'])}")
        
        # Check if cold start user
        is_cold_start = self._is_cold_start_user(user_id)
        
        if is_cold_start:
            # Cold start strategy
            recommendations = []
            seen_ids = set()
            
            # 1. Genre-based (if preferences available)
            if user and user.genre_preferences:
                genre_recs = self.get_genre_based_recommendations(user_id, n_recommendations)
                for movie in genre_recs:
                    if movie.id not in seen_ids and len(recommendations) < n_recommendations:
                        recommendations.append(movie)
                        seen_ids.add(movie.id)
            
            # 2. Demographic-based (if demographics available)
            if len(recommendations) < n_recommendations and user and (user.age or user.location):
                demo_recs = self.get_demographic_recommendations(user_id, n_recommendations - len(recommendations))
                for movie in demo_recs:
                    if movie.id not in seen_ids and len(recommendations) < n_recommendations:
                        recommendations.append(movie)
                        seen_ids.add(movie.id)
            
            # 3. Fill with popular movies
            if len(recommendations) < n_recommendations:
                popular_recs = self._get_popular_movies(n_recommendations - len(recommendations), user_id)
                for movie in popular_recs:
                    if movie.id not in seen_ids and len(recommendations) < n_recommendations:
                        recommendations.append(movie)
                        seen_ids.add(movie.id)
            
            # Apply context-aware adjustments for cold start users too
            if use_context and context and len(recommendations) > 0:
                # Apply enhanced diversification (helps even for cold start)
                recommendations = self._apply_enhanced_diversification(recommendations, user_id, context)
                logger.info(f"Applied enhanced diversification to cold start recommendations")
            
            # Apply feedback-driven scoring (even for cold start users)
            recommendations = self._apply_feedback_driven_scoring(recommendations, user_id)
            logger.info(f"Applied feedback-driven scoring to cold start recommendations")
            
            # Filter out disliked genres from onboarding
            recommendations = self._filter_disliked_genres(recommendations, user_id)
            
            # Apply thumbs up/down filtering and boosting
            recommendations = self._filter_similar_to_thumbs_down(recommendations, user_id)
            recommendations = self._boost_similar_to_thumbs_up(recommendations, user_id)
            
            return recommendations
        
        else:
            # Advanced hybrid approach for users with sufficient data
            # Primary: Embeddings (if enabled) or SVD - best accuracy
            # Secondary: Item-based CF - good for sparse data
            # Tertiary: Content-based - diversity and cold items
            
            seen_ids = set()
            hybrid_recommendations = []
            
            if use_graph and use_embeddings:
                # Weighting with graph + embeddings:
                # - 30% from Graph (knowledge graph)
                # - 30% from Embeddings (deep learning)
                # - 25% from SVD (matrix factorization)
                # - 15% from Item-based CF (complementary)
                
                graph_movies = self.get_graph_recommendations(user_id, n_recommendations)
                embedding_movies = self.get_embedding_recommendations(user_id, n_recommendations)
                svd_movies = self.get_svd_recommendations(user_id, n_recommendations)
                item_movies = self.get_item_based_recommendations(user_id, n_recommendations)
                
                graph_weight = int(n_recommendations * 0.3)
                embedding_weight = int(n_recommendations * 0.3)
                svd_weight = int(n_recommendations * 0.25)
                item_weight = n_recommendations - graph_weight - embedding_weight - svd_weight
                
                # Add Graph recommendations (primary)
                for movie in graph_movies[:graph_weight]:
                    if movie.id not in seen_ids:
                        hybrid_recommendations.append(movie)
                        seen_ids.add(movie.id)
                
                # Add Embedding recommendations (co-primary)
                for movie in embedding_movies[:embedding_weight]:
                    if movie.id not in seen_ids and len(hybrid_recommendations) < n_recommendations:
                        hybrid_recommendations.append(movie)
                        seen_ids.add(movie.id)
                
                # Add SVD recommendations (secondary)
                for movie in svd_movies[:svd_weight]:
                    if movie.id not in seen_ids and len(hybrid_recommendations) < n_recommendations:
                        hybrid_recommendations.append(movie)
                        seen_ids.add(movie.id)
                
            elif use_graph:
                # Weighting with graph only:
                # - 40% from Graph (knowledge graph)
                # - 30% from SVD (matrix factorization)
                # - 20% from Item-based CF (complementary)
                # - 10% from Content-based (diversity)
                
                graph_movies = self.get_graph_recommendations(user_id, n_recommendations)
                svd_movies = self.get_svd_recommendations(user_id, n_recommendations)
                item_movies = self.get_item_based_recommendations(user_id, n_recommendations)
                content_movies = self.get_content_based_recommendations(user_id, n_recommendations)
                
                graph_weight = int(n_recommendations * 0.4)
                svd_weight = int(n_recommendations * 0.3)
                item_weight = int(n_recommendations * 0.2)
                content_weight = n_recommendations - graph_weight - svd_weight - item_weight
                
                # Add Graph recommendations (primary)
                for movie in graph_movies[:graph_weight]:
                    if movie.id not in seen_ids:
                        hybrid_recommendations.append(movie)
                        seen_ids.add(movie.id)
                
                # Add SVD recommendations (secondary)
                for movie in svd_movies[:svd_weight]:
                    if movie.id not in seen_ids and len(hybrid_recommendations) < n_recommendations:
                        hybrid_recommendations.append(movie)
                        seen_ids.add(movie.id)
                
            elif use_embeddings:
                # Weighting with embeddings:
                # - 40% from Embeddings (deep learning)
                # - 30% from SVD (matrix factorization)
                # - 20% from Item-based CF (complementary)
                # - 10% from Content-based (diversity)
                
                embedding_movies = self.get_embedding_recommendations(user_id, n_recommendations)
                svd_movies = self.get_svd_recommendations(user_id, n_recommendations)
                item_movies = self.get_item_based_recommendations(user_id, n_recommendations)
                content_movies = self.get_content_based_recommendations(user_id, n_recommendations)
                
                embedding_weight = int(n_recommendations * 0.4)
                svd_weight = int(n_recommendations * 0.3)
                item_weight = int(n_recommendations * 0.2)
                content_weight = n_recommendations - embedding_weight - svd_weight - item_weight
                
                # Add Embedding recommendations (primary)
                for movie in embedding_movies[:embedding_weight]:
                    if movie.id not in seen_ids:
                        hybrid_recommendations.append(movie)
                        seen_ids.add(movie.id)
                
                # Add SVD recommendations (secondary)
                for movie in svd_movies[:svd_weight]:
                    if movie.id not in seen_ids and len(hybrid_recommendations) < n_recommendations:
                        hybrid_recommendations.append(movie)
                        seen_ids.add(movie.id)
                
            else:
                # Standard weighting without embeddings:
                # - 60% from SVD (most accurate)
                # - 25% from Item-based CF (complementary)
                # - 15% from Content-based (diversity)
                
                svd_movies = self.get_svd_recommendations(user_id, n_recommendations)
                item_movies = self.get_item_based_recommendations(user_id, n_recommendations)
                content_movies = self.get_content_based_recommendations(user_id, n_recommendations)
                
                svd_weight = int(n_recommendations * 0.6)
                item_weight = int(n_recommendations * 0.25)
                content_weight = n_recommendations - svd_weight - item_weight
                
                # Add SVD recommendations (primary)
                for movie in svd_movies[:svd_weight]:
                    if movie.id not in seen_ids:
                        hybrid_recommendations.append(movie)
                        seen_ids.add(movie.id)
            
            # Add Item-based recommendations (secondary)
            for movie in item_movies[:item_weight]:
                if movie.id not in seen_ids and len(hybrid_recommendations) < n_recommendations:
                    hybrid_recommendations.append(movie)
                    seen_ids.add(movie.id)
            
            # Add Content-based recommendations (tertiary, for diversity)
            for movie in content_movies[:content_weight]:
                if movie.id not in seen_ids and len(hybrid_recommendations) < n_recommendations:
                    hybrid_recommendations.append(movie)
                    seen_ids.add(movie.id)
            
            # Fill remaining slots if needed (round-robin)
            if len(hybrid_recommendations) < n_recommendations:
                all_remaining = [m for m in svd_movies + item_movies + content_movies 
                                if m.id not in seen_ids]
                for movie in all_remaining:
                    if len(hybrid_recommendations) >= n_recommendations:
                        break
                    if movie.id not in seen_ids:
                        hybrid_recommendations.append(movie)
                        seen_ids.add(movie.id)
            
            logger.info(f"Hybrid recommendations: {len(hybrid_recommendations)} movies "
                       f"(SVD: {min(svd_weight, len([m for m in hybrid_recommendations if m in svd_movies]))}, "
                       f"Item: {len([m for m in hybrid_recommendations if m in item_movies])}, "
                       f"Content: {len([m for m in hybrid_recommendations if m in content_movies])})")
            
            # Apply context-aware adjustments
            if use_context and context:
                # Apply enhanced diversification (replaces temporal + diversity separately)
                hybrid_recommendations = self._apply_enhanced_diversification(
                    hybrid_recommendations,
                    user_id,
                    context
                )
                logger.info(f"Applied enhanced diversification with age, temporal, and genre preferences")
            
            # Apply feedback-driven scoring (heavily weights dislikes and star ratings)
            hybrid_recommendations = self._apply_feedback_driven_scoring(hybrid_recommendations, user_id)
            logger.info(f"Applied feedback-driven scoring with heavy dislike weighting")
            
            # Filter out disliked genres from onboarding (applies to ALL users)
            hybrid_recommendations = self._filter_disliked_genres(hybrid_recommendations, user_id)
            
            # Apply thumbs up/down filtering and boosting
            hybrid_recommendations = self._filter_similar_to_thumbs_down(hybrid_recommendations, user_id)
            hybrid_recommendations = self._boost_similar_to_thumbs_up(hybrid_recommendations, user_id)
            
            return hybrid_recommendations[:n_recommendations]
    
    def get_context_aware_recommendations(self, user_id: int, n_recommendations: int = 10):
        """
        Get context-aware recommendations with detailed context information
        
        This is a wrapper around get_hybrid_recommendations that returns both
        recommendations and the context used to generate them.
        
        Returns:
            dict: {
                'recommendations': List of Movie objects,
                'context': Context dict with temporal and diversity info
            }
        """
        context = self._get_contextual_features(user_id)
        recommendations = self.get_hybrid_recommendations(
            user_id, 
            n_recommendations,
            use_context=True
        )
        
        return {
            'recommendations': recommendations,
            'context': {
                'time_period': context['temporal']['time_period'],
                'is_weekend': context['temporal']['is_weekend'],
                'hour': context['temporal']['hour'],
                'recent_genres': list(context['recent_genres']),
                'genre_saturation': context['genre_saturation'],
                'recent_movies_count': len(context['sequential_patterns'])
            }
        }
    
    # =============================================================================
    # BANDIT-BASED ALGORITHM SELECTION
    # =============================================================================
    
    def get_bandit_recommendations(self, user_id: int, n_recommendations: int = 20, 
                                   n_algorithms: int = 3) -> dict:
        """
        Use Thompson Sampling bandit to select and blend recommendation algorithms
        
        This method:
        1. Extracts context (time, user type, etc.)
        2. Uses bandit to select best N algorithms for this context
        3. Generates recommendations from each selected algorithm
        4. Blends results using confidence weights
        5. Returns recommendations with algorithm attribution
        
        Args:
            user_id: User ID
            n_recommendations: Number of final recommendations to return
            n_algorithms: Number of algorithms to select (default 3)
            
        Returns:
            dict: {
                'recommendations': List of (movie, algorithm, confidence) tuples,
                'context': Context used for selection,
                'selected_algorithms': List of (algorithm, confidence) tuples,
                'bandit_info': Bandit state information
            }
        """
        from .bandit_selector import BanditSelector
        
        # Initialize bandit
        bandit = BanditSelector(self.db)
        
        # Extract context
        context = bandit.extract_context(user_id)
        logger.info(f"Bandit context for user {user_id}: {context}")
        
        # Select algorithms using bandit
        selected_algorithms, confidences = bandit.select_arms(context, n_arms=n_algorithms)
        logger.info(f"Bandit selected: {list(zip(selected_algorithms, confidences))}")
        
        # Map algorithm names to methods
        algorithm_methods = {
            'svd': self.get_svd_recommendations,
            'embeddings': self.get_embedding_recommendations,
            'graph': self.get_graph_recommendations,
            'item_cf': self.get_item_based_recommendations,
            'long_tail': self._get_long_tail_recommendations,
            'serendipity': self._get_serendipity_recommendations
        }
        
        # Generate recommendations from each selected algorithm
        algorithm_results = {}
        for algo, confidence in zip(selected_algorithms, confidences):
            try:
                method = algorithm_methods.get(algo)
                if method:
                    # Get extra recommendations to have a larger pool
                    pool_size = n_recommendations * 2
                    recommendations = method(user_id, n_recommendations=pool_size)
                    algorithm_results[algo] = {
                        'movies': recommendations,
                        'confidence': confidence
                    }
                    logger.info(f"Algorithm {algo} generated {len(recommendations)} recommendations")
                else:
                    logger.warning(f"Algorithm {algo} not found, skipping")
            except Exception as e:
                logger.error(f"Error generating recommendations with {algo}: {e}")
        
        # Blend recommendations using weighted round-robin
        blended_recommendations = []
        seen_movie_ids = set()
        
        # Create iterators for each algorithm's results
        algorithm_iters = {
            algo: iter(data['movies']) 
            for algo, data in algorithm_results.items()
        }
        
        # Round-robin selection weighted by confidence
        max_iterations = n_recommendations * 3  # Safety limit
        iteration = 0
        
        while len(blended_recommendations) < n_recommendations and iteration < max_iterations:
            iteration += 1
            
            for algo, data in algorithm_results.items():
                if len(blended_recommendations) >= n_recommendations:
                    break
                
                # Try to get next movie from this algorithm
                try:
                    movie = next(algorithm_iters[algo])
                    if movie.id not in seen_movie_ids:
                        seen_movie_ids.add(movie.id)
                        blended_recommendations.append({
                            'movie': movie,
                            'algorithm': algo,
                            'confidence': data['confidence']
                        })
                except StopIteration:
                    # This algorithm exhausted
                    continue
        
        # If we still need more recommendations, fall back to hybrid
        if len(blended_recommendations) < n_recommendations:
            logger.warning(f"Bandit only generated {len(blended_recommendations)} recommendations, filling with hybrid")
            hybrid_recs = self.get_hybrid_recommendations(
                user_id, 
                n_recommendations=(n_recommendations - len(blended_recommendations))
            )
            for movie in hybrid_recs:
                if movie.id not in seen_movie_ids:
                    blended_recommendations.append({
                        'movie': movie,
                        'algorithm': 'hybrid_fallback',
                        'confidence': 0.1
                    })
        
        # Get bandit stats for this context
        bandit_info = {
            'context_key': bandit._context_to_key(context),
            'selected_algorithms': list(zip(selected_algorithms, confidences)),
            'stats': bandit.get_bandit_stats(context)
        }
        
        return {
            'recommendations': blended_recommendations,
            'context': context,
            'selected_algorithms': list(zip(selected_algorithms, confidences)),
            'bandit_info': bandit_info
        }
    
    def _get_long_tail_recommendations(self, user_id: int, n_recommendations: int = 10):
        """
        Get long-tail recommendations (less popular but high quality movies)
        Focuses on diversity and discovery
        """
        # Get user's genre preferences
        genre_prefs = self._get_user_genre_preferences_combined(user_id)
        
        # Get movies with moderate popularity (not blockbusters)
        excluded_ids = self._get_excluded_movie_ids(user_id)
        
        query = self.db.query(Movie).filter(
            Movie.id.notin_(excluded_ids),
            Movie.vote_average >= 7.0,  # High quality
            Movie.vote_count >= 50,  # Some validation
            Movie.vote_count <= 500,  # Not too popular (long tail)
        )
        
        # Filter by preferred genres if available
        if genre_prefs:
            liked_genres = [g for g, score in genre_prefs.items() if score > 0]
            if liked_genres:
                # Use JSONB containment operator
                from sqlalchemy import cast, String
                movies = []
                for movie in query.all():
                    if movie.genres:
                        movie_genres = [g['name'] for g in movie.genres]
                        if any(g in movie_genres for g in liked_genres):
                            movies.append(movie)
                
                # Sort by diversity score (genre variety)
                if len(movies) > n_recommendations:
                    movies = self._apply_enhanced_diversification(movies, user_id, None)
                
                return movies[:n_recommendations]
        
        # No preference, return diverse long-tail movies
        movies = query.order_by(desc(Movie.vote_average)).limit(n_recommendations * 2).all()
        return self._apply_enhanced_diversification(movies, user_id, None)[:n_recommendations]
    
    def _get_serendipity_recommendations(self, user_id: int, n_recommendations: int = 10):
        """
        Get serendipitous recommendations (unexpected but quality movies)
        Uses genre expansion and keyword-based discovery
        """
        from sqlalchemy import func, cast, String
        
        # Get user's primary genres
        user_genres = self._get_user_genre_preferences_combined(user_id)
        excluded_ids = self._get_excluded_movie_ids(user_id)
        
        # Get complementary genres (expand beyond comfort zone)
        complementary_genres = {
            'Action': ['Thriller', 'Crime', 'Adventure'],
            'Comedy': ['Romance', 'Family', 'Animation'],
            'Drama': ['Biography', 'History', 'Mystery'],
            'Sci-Fi': ['Fantasy', 'Adventure', 'Mystery'],
            'Horror': ['Thriller', 'Mystery', 'Fantasy'],
        }
        
        # Find genres to explore
        explore_genres = set()
        if user_genres:
            for genre in user_genres.keys():
                if genre in complementary_genres:
                    explore_genres.update(complementary_genres[genre])
        
        # If no user history, use highly-rated diverse movies
        if not explore_genres:
            movies = self.db.query(Movie).filter(
                Movie.id.notin_(excluded_ids),
                Movie.vote_average >= 7.5,
                Movie.vote_count >= 100
            ).order_by(desc(Movie.vote_average)).limit(n_recommendations * 2).all()
            return self._apply_enhanced_diversification(movies, user_id, None)[:n_recommendations]
        
        # Find high-quality movies in complementary genres
        movies = []
        all_movies = self.db.query(Movie).filter(
            Movie.id.notin_(excluded_ids),
            Movie.vote_average >= 7.0,
            Movie.vote_count >= 100
        ).all()
        
        for movie in all_movies:
            if movie.genres:
                movie_genres = [g['name'] for g in movie.genres]
                if any(g in explore_genres for g in movie_genres):
                    movies.append(movie)
        
        # Sort by rating and diversify
        movies = sorted(movies, key=lambda m: m.vote_average, reverse=True)
        movies = self._apply_enhanced_diversification(movies[:n_recommendations * 2], user_id, None)
        
        return movies[:n_recommendations]
    
    # =============================================================================
    # CONTINUOUS LEARNING & A/B TESTING
    # =============================================================================
    
    def incremental_update(self, user_id: int, movie_id: int, rating: float) -> dict:
        """
        Update recommendation model incrementally with new rating
        
        Implements a warm-start approach:
        1. Check if model needs update (based on rating count threshold)
        2. Perform incremental update if threshold reached
        3. Log update metrics
        
        Args:
            user_id: User who added the rating
            movie_id: Movie that was rated
            rating: Rating value
            
        Returns:
            dict with update status and metrics
        """
        from ..models import ModelUpdateLog, Rating
        import time
        
        result = {
            'updated': False,
            'update_type': None,
            'reason': None,
            'metrics': {}
        }
        
        try:
            # Count ratings since last model update
            last_update = self.db.query(ModelUpdateLog)\
                .filter(ModelUpdateLog.model_type == 'svd')\
                .filter(ModelUpdateLog.success == True)\
                .order_by(ModelUpdateLog.created_at.desc())\
                .first()
            
            # Determine ratings threshold for update
            update_threshold = getattr(self, 'incremental_update_threshold', 50)
            
            if last_update:
                new_ratings_count = self.db.query(Rating)\
                    .filter(Rating.timestamp > last_update.created_at)\
                    .count()
            else:
                new_ratings_count = self.db.query(Rating).count()
            
            # Trigger update if threshold reached
            if new_ratings_count >= update_threshold:
                start_time = time.time()
                
                # Invalidate cache to force rebuild on next request
                self.invalidate_svd_cache()
                
                # Pre-build model now
                success = self._build_svd_model()
                
                duration = time.time() - start_time
                
                # Calculate metrics if model built successfully
                metrics = {}
                if success and self._svd_model:
                    metrics = {
                        'explained_variance_ratio': float(self._svd_model.explained_variance_ratio_.sum()),
                        'n_components': self._svd_model.n_components,
                        'n_users': len(self._svd_user_ids) if self._svd_user_ids else 0,
                        'n_movies': len(self._svd_movie_ids) if self._svd_movie_ids else 0
                    }
                
                # Log the update
                log_entry = ModelUpdateLog(
                    model_type='svd',
                    update_type='warm_start_rebuild',
                    ratings_processed=new_ratings_count,
                    update_trigger=f'threshold_reached_{update_threshold}',
                    metrics=metrics,
                    duration_seconds=duration,
                    success=success
                )
                self.db.add(log_entry)
                self.db.commit()
                
                result.update({
                    'updated': True,
                    'update_type': 'warm_start_rebuild',
                    'reason': f'{new_ratings_count} new ratings (threshold: {update_threshold})',
                    'metrics': metrics,
                    'duration_seconds': duration
                })
                
                logging.info(f"Incremental update completed: {new_ratings_count} ratings processed")
            else:
                result['reason'] = f'Threshold not reached ({new_ratings_count}/{update_threshold} ratings)'
        
        except Exception as e:
            logging.error(f"Error in incremental_update: {e}")
            result['error'] = str(e)
        
        return result
    
    def force_model_update(self, update_type: str = 'full_retrain') -> dict:
        """
        Force a model update regardless of threshold
        
        Args:
            update_type: Type of update ('full_retrain', 'warm_start')
            
        Returns:
            dict with update status and metrics
        """
        from ..models import ModelUpdateLog, Rating
        import time
        
        result = {
            'updated': False,
            'update_type': update_type,
            'metrics': {}
        }
        
        try:
            start_time = time.time()
            
            # Invalidate cache
            self.invalidate_svd_cache()
            
            # Rebuild model
            success = self._build_svd_model()
            
            duration = time.time() - start_time
            
            # Calculate metrics
            metrics = {}
            if success and self._svd_model:
                metrics = {
                    'explained_variance_ratio': float(self._svd_model.explained_variance_ratio_.sum()),
                    'n_components': self._svd_model.n_components,
                    'n_users': len(self._svd_user_ids) if self._svd_user_ids else 0,
                    'n_movies': len(self._svd_movie_ids) if self._svd_movie_ids else 0
                }
            
            # Count total ratings
            total_ratings = self.db.query(Rating).count()
            
            # Log the update
            log_entry = ModelUpdateLog(
                model_type='svd',
                update_type=update_type,
                ratings_processed=total_ratings,
                update_trigger='manual_force_update',
                metrics=metrics,
                duration_seconds=duration,
                success=success
            )
            self.db.add(log_entry)
            self.db.commit()
            
            result.update({
                'updated': True,
                'metrics': metrics,
                'duration_seconds': duration,
                'ratings_processed': total_ratings
            })
            
            logging.info(f"Force model update completed: {update_type}")
        
        except Exception as e:
            logging.error(f"Error in force_model_update: {e}")
            result['error'] = str(e)
        
        return result
    
    def track_recommendation(
        self, 
        user_id: int, 
        movie_id: int, 
        algorithm: str,
        position: int,
        score: float = None,
        context: dict = None
    ) -> int:
        """
        Track a recommendation shown to user for A/B testing
        
        Args:
            user_id: User who received recommendation
            movie_id: Movie recommended
            algorithm: Algorithm that generated recommendation (svd, item_cf, content, hybrid)
            position: Position in recommendation list (1-based)
            score: Recommendation score/confidence
            context: Additional context (time_period, is_weekend, etc.)
            
        Returns:
            Recommendation event ID
        """
        from ..models import RecommendationEvent
        
        try:
            event = RecommendationEvent(
                user_id=user_id,
                movie_id=movie_id,
                algorithm=algorithm,
                recommendation_score=score,
                position=position,
                context=context
            )
            self.db.add(event)
            self.db.commit()
            
            return event.id
        
        except Exception as e:
            logging.error(f"Error tracking recommendation: {e}")
            self.db.rollback()
            return None
    
    def track_recommendation_click(self, user_id: int, movie_id: int):
        """
        Track when user clicks on a recommended movie
        
        Args:
            user_id: User who clicked
            movie_id: Movie that was clicked
        """
        from ..models import RecommendationEvent
        from datetime import datetime
        
        try:
            # Find the most recent recommendation event for this user-movie pair
            event = self.db.query(RecommendationEvent)\
                .filter(RecommendationEvent.user_id == user_id)\
                .filter(RecommendationEvent.movie_id == movie_id)\
                .filter(RecommendationEvent.clicked == False)\
                .order_by(RecommendationEvent.created_at.desc())\
                .first()
            
            if event:
                event.clicked = True
                event.clicked_at = datetime.utcnow()
                self.db.commit()
                
                logging.info(f"Tracked click: user={user_id}, movie={movie_id}, algo={event.algorithm}")
        
        except Exception as e:
            logging.error(f"Error tracking click: {e}")
            self.db.rollback()
    
    def track_recommendation_rating(self, user_id: int, movie_id: int, rating: float):
        """
        Track when user rates a recommended movie
        
        Args:
            user_id: User who rated
            movie_id: Movie that was rated
            rating: Rating value
        """
        from ..models import RecommendationEvent
        from datetime import datetime
        
        try:
            # Find recommendation event for this user-movie pair
            event = self.db.query(RecommendationEvent)\
                .filter(RecommendationEvent.user_id == user_id)\
                .filter(RecommendationEvent.movie_id == movie_id)\
                .filter(RecommendationEvent.rated == False)\
                .order_by(RecommendationEvent.created_at.desc())\
                .first()
            
            if event:
                event.rated = True
                event.rated_at = datetime.utcnow()
                event.rating_value = rating
                self.db.commit()
                
                logging.info(f"Tracked rating: user={user_id}, movie={movie_id}, rating={rating}, algo={event.algorithm}")
        
        except Exception as e:
            logging.error(f"Error tracking rating: {e}")
            self.db.rollback()
    
    def track_recommendation_performance(
        self, 
        user_id: int, 
        movie_id: int, 
        action: str,
        value: any = None
    ):
        """
        Generic method to track recommendation interactions
        
        Args:
            user_id: User performing action
            movie_id: Movie being interacted with
            action: Type of action (click, rate, favorite, watchlist)
            value: Optional value (e.g., rating value)
        """
        from ..models import RecommendationEvent
        from datetime import datetime
        
        try:
            # Find most recent recommendation event
            event = self.db.query(RecommendationEvent)\
                .filter(RecommendationEvent.user_id == user_id)\
                .filter(RecommendationEvent.movie_id == movie_id)\
                .order_by(RecommendationEvent.created_at.desc())\
                .first()
            
            if event:
                if action == 'click':
                    event.clicked = True
                    event.clicked_at = datetime.utcnow()
                elif action == 'rate':
                    event.rated = True
                    event.rated_at = datetime.utcnow()
                    event.rating_value = value
                elif action == 'favorite':
                    event.added_to_favorites = True
                elif action == 'watchlist':
                    event.added_to_watchlist = True
                elif action == 'thumbs_up':
                    event.thumbs_up = True
                    event.thumbs_up_at = datetime.utcnow()
                elif action == 'thumbs_down':
                    event.thumbs_down = True
                    event.thumbs_down_at = datetime.utcnow()
                
                self.db.commit()
                
                logging.info(f"Tracked {action}: user={user_id}, movie={movie_id}, algo={event.algorithm}")
        
        except Exception as e:
            logging.error(f"Error tracking performance: {e}")
            self.db.rollback()
    
    def track_recommendation_thumbs_up(self, user_id: int, movie_id: int):
        """
        Track when user gives thumbs up to a recommended movie
        
        Args:
            user_id: User who gave thumbs up
            movie_id: Movie that received thumbs up
        """
        from ..models import RecommendationEvent
        from datetime import datetime
        
        try:
            # Find the most recent recommendation event for this user-movie pair
            event = self.db.query(RecommendationEvent)\
                .filter(RecommendationEvent.user_id == user_id)\
                .filter(RecommendationEvent.movie_id == movie_id)\
                .filter(RecommendationEvent.thumbs_up == False)\
                .order_by(RecommendationEvent.created_at.desc())\
                .first()
            
            if event:
                event.thumbs_up = True
                event.thumbs_up_at = datetime.utcnow()
                self.db.commit()
                
                logging.info(f"Tracked thumbs up: user={user_id}, movie={movie_id}, algo={event.algorithm}")
        
        except Exception as e:
            logging.error(f"Error tracking thumbs up: {e}")
            self.db.rollback()
    
    def track_recommendation_thumbs_down(self, user_id: int, movie_id: int):
        """
        Track when user gives thumbs down to a recommended movie
        
        Args:
            user_id: User who gave thumbs down
            movie_id: Movie that received thumbs down
        """
        from ..models import RecommendationEvent
        from datetime import datetime
        
        try:
            # Find the most recent recommendation event for this user-movie pair
            event = self.db.query(RecommendationEvent)\
                .filter(RecommendationEvent.user_id == user_id)\
                .filter(RecommendationEvent.movie_id == movie_id)\
                .filter(RecommendationEvent.thumbs_down == False)\
                .order_by(RecommendationEvent.created_at.desc())\
                .first()
            
            if event:
                event.thumbs_down = True
                event.thumbs_down_at = datetime.utcnow()
                self.db.commit()
                
                logging.info(f"Tracked thumbs down: user={user_id}, movie={movie_id}, algo={event.algorithm}")
        
        except Exception as e:
            logging.error(f"Error tracking thumbs down: {e}")
            self.db.rollback()
    
    def get_algorithm_performance(self, days: int = 30) -> dict:
        """
        Get performance metrics for each recommendation algorithm
        
        Args:
            days: Number of days to analyze
            
        Returns:
            dict with metrics per algorithm
        """
        from ..models import RecommendationEvent
        from datetime import datetime, timedelta
        from sqlalchemy import func
        
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # Query performance by algorithm
            results = self.db.query(
                RecommendationEvent.algorithm,
                func.count(RecommendationEvent.id).label('total_recommendations'),
                func.sum(func.cast(RecommendationEvent.clicked, Integer)).label('total_clicks'),
                func.sum(func.cast(RecommendationEvent.rated, Integer)).label('total_ratings'),
                func.avg(RecommendationEvent.rating_value).label('avg_rating_value'),
                func.sum(func.cast(RecommendationEvent.added_to_favorites, Integer)).label('total_favorites'),
                func.sum(func.cast(RecommendationEvent.added_to_watchlist, Integer)).label('total_watchlist'),
                func.sum(func.cast(RecommendationEvent.thumbs_up, Integer)).label('total_thumbs_up'),
                func.sum(func.cast(RecommendationEvent.thumbs_down, Integer)).label('total_thumbs_down')
            ).filter(
                RecommendationEvent.created_at >= cutoff_date
            ).group_by(
                RecommendationEvent.algorithm
            ).all()
            
            # Format results
            performance = {}
            for row in results:
                algo = row.algorithm
                total = row.total_recommendations or 0
                clicks = row.total_clicks or 0
                ratings = row.total_ratings or 0
                
                performance[algo] = {
                    'total_recommendations': total,
                    'total_clicks': clicks,
                    'total_ratings': ratings,
                    'avg_rating': float(row.avg_rating_value) if row.avg_rating_value else None,
                    'total_favorites': row.total_favorites or 0,
                    'total_watchlist': row.total_watchlist or 0,
                    'total_thumbs_up': row.total_thumbs_up or 0,
                    'total_thumbs_down': row.total_thumbs_down or 0,
                    'ctr': (clicks / total * 100) if total > 0 else 0,  # Click-through rate
                    'rating_rate': (ratings / total * 100) if total > 0 else 0,  # Rating conversion rate
                    'thumbs_up_rate': (row.total_thumbs_up / total * 100) if total > 0 else 0,  # Thumbs up rate
                    'thumbs_down_rate': (row.total_thumbs_down / total * 100) if total > 0 else 0  # Thumbs down rate
                }
            
            return performance
        
        except Exception as e:
            logging.error(f"Error getting algorithm performance: {e}")
            return {}
    
    def get_model_update_history(self, limit: int = 10) -> list:
        """
        Get recent model update history
        
        Args:
            limit: Number of recent updates to retrieve
            
        Returns:
            list of update log dictionaries
        """
        from ..models import ModelUpdateLog
        
        try:
            logs = self.db.query(ModelUpdateLog)\
                .order_by(ModelUpdateLog.created_at.desc())\
                .limit(limit)\
                .all()
            
            return [{
                'id': log.id,
                'model_type': log.model_type,
                'update_type': log.update_type,
                'ratings_processed': log.ratings_processed,
                'update_trigger': log.update_trigger,
                'metrics': log.metrics,
                'duration_seconds': log.duration_seconds,
                'success': log.success,
                'created_at': log.created_at.isoformat() if log.created_at else None
            } for log in logs]
        
        except Exception as e:
            logging.error(f"Error getting model update history: {e}")
            return []

    # =============================================================================
    # ENHANCED DIVERSIFICATION METHODS
    # =============================================================================
    
    def _get_age_based_genre_preferences(self, age: int) -> dict:
        """
        Get genre preferences based on user age
        Returns dict with genre weights for different age groups
        """
        age_genre_map = {
            # Children (13-17)
            'teen': {
                'preferred': ['Animation', 'Adventure', 'Fantasy', 'Comedy', 'Family', 'Science Fiction'],
                'moderate': ['Action', 'Mystery', 'Romance'],
                'avoid': ['Horror', 'Thriller', 'War', 'Crime']
            },
            # Young Adults (18-29)
            'young_adult': {
                'preferred': ['Action', 'Comedy', 'Science Fiction', 'Romance', 'Adventure', 'Thriller'],
                'moderate': ['Drama', 'Fantasy', 'Horror', 'Mystery'],
                'avoid': ['Documentary', 'War']
            },
            # Adults (30-49)
            'adult': {
                'preferred': ['Drama', 'Thriller', 'Crime', 'Mystery', 'Comedy', 'Action'],
                'moderate': ['Science Fiction', 'Romance', 'Adventure', 'Documentary'],
                'avoid': ['Animation', 'Family']
            },
            # Mature Adults (50+)
            'mature': {
                'preferred': ['Drama', 'Documentary', 'History', 'Biography', 'Mystery', 'Crime'],
                'moderate': ['Comedy', 'Romance', 'Thriller', 'War'],
                'avoid': ['Horror', 'Animation', 'Fantasy']
            }
        }
        
        # Determine age group
        if age < 18:
            return age_genre_map['teen']
        elif age < 30:
            return age_genre_map['young_adult']
        elif age < 50:
            return age_genre_map['adult']
        else:
            return age_genre_map['mature']
    
    def _get_enhanced_temporal_preferences(self, hour: int, day_of_week: int, age: int = None) -> dict:
        """
        Enhanced temporal filtering that considers time, day, and optionally age
        
        Returns:
            dict with genre preferences and runtime preferences
        """
        time_period = self._get_time_period(hour)
        is_weekend = day_of_week >= 5
        
        # Base temporal preferences
        temporal_prefs = {
            'morning': {
                'genres': ['Animation', 'Family', 'Comedy', 'Adventure', 'Documentary'],
                'mood': 'light',
                'runtime_pref': 'short',  # < 100 min
                'intensity': 'low'
            },
            'afternoon': {
                'genres': ['Action', 'Adventure', 'Comedy', 'Science Fiction', 'Fantasy'],
                'mood': 'energetic',
                'runtime_pref': 'medium',  # 90-120 min
                'intensity': 'medium'
            },
            'evening': {
                'genres': ['Drama', 'Thriller', 'Mystery', 'Crime', 'Romance'],
                'mood': 'engaging',
                'runtime_pref': 'medium',  # 100-130 min
                'intensity': 'medium-high'
            },
            'night': {
                'genres': ['Horror', 'Thriller', 'Mystery', 'Science Fiction', 'Drama'],
                'mood': 'intense',
                'runtime_pref': 'long',  # > 110 min
                'intensity': 'high'
            }
        }
        
        prefs = temporal_prefs[time_period].copy()
        
        # Adjust for weekend vs weekday
        if is_weekend:
            prefs['runtime_pref'] = 'long'  # People have more time
            prefs['genres'].extend(['Epic', 'Adventure', 'Fantasy'])
        else:
            # Weekday - prefer shorter, lighter content
            if time_period in ['evening', 'night']:
                prefs['genres'] = [g for g in prefs['genres'] if g not in ['Horror']]
                prefs['genres'].extend(['Comedy', 'Documentary'])
        
        # Adjust for age if provided
        if age:
            age_prefs = self._get_age_based_genre_preferences(age)
            # Boost preferred genres for age group
            prefs['age_preferred'] = age_prefs['preferred']
            prefs['age_avoid'] = age_prefs['avoid']
        
        return prefs
    
    def _get_thumbs_based_genre_preferences(self, user_id: int) -> dict:
        """
        Extract genre preferences from thumbs up/down interactions
        
        Returns:
            dict: {
                'liked_genres': set of genres from thumbs up movies,
                'disliked_genres': set of genres from thumbs down movies,
                'genre_scores': dict mapping genres to preference scores
            }
        """
        from ..models import RecommendationEvent
        
        # Get thumbs up movies
        thumbs_up_ids = self._get_thumbs_up_movie_ids(user_id)
        thumbs_down_ids = self._get_thumbs_down_movie_ids(user_id)
        
        liked_genres = defaultdict(int)
        disliked_genres = defaultdict(int)
        
        # Analyze thumbs up movies
        if thumbs_up_ids:
            thumbs_up_movies = self.db.query(Movie).filter(Movie.id.in_(thumbs_up_ids)).all()
            for movie in thumbs_up_movies:
                if movie.genres:
                    try:
                        genres = movie.genres if isinstance(movie.genres, list) else json.loads(movie.genres)
                        for genre in genres:
                            liked_genres[genre] += 1
                    except:
                        pass
        
        # Analyze thumbs down movies
        if thumbs_down_ids:
            thumbs_down_movies = self.db.query(Movie).filter(Movie.id.in_(thumbs_down_ids)).all()
            for movie in thumbs_down_movies:
                if movie.genres:
                    try:
                        genres = movie.genres if isinstance(movie.genres, list) else json.loads(movie.genres)
                        for genre in genres:
                            disliked_genres[genre] += 1
                    except:
                        pass
        
        # Calculate genre scores (liked - disliked)
        all_genres = set(liked_genres.keys()) | set(disliked_genres.keys())
        genre_scores = {}
        for genre in all_genres:
            score = liked_genres[genre] - disliked_genres[genre]
            genre_scores[genre] = score
        
        return {
            'liked_genres': set(g for g, count in liked_genres.items() if count > 0),
            'disliked_genres': set(g for g, count in disliked_genres.items() if count > 0),
            'genre_scores': genre_scores
        }
    
    def _get_user_genre_preferences_combined(self, user_id: int) -> dict:
        """
        Combine genre preferences from multiple sources:
        1. User's explicit genre_preferences (onboarding)
        2. Thumbs up/down interactions
        3. High-rated movies (4+ stars)
        
        Returns:
            dict with comprehensive genre preferences
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        
        combined_scores = defaultdict(float)
        
        # 1. Explicit preferences from onboarding (weight: 5.0 - INCREASED)
        # These are user's stated preferences and should have strong influence
        if user and user.genre_preferences:
            for genre, score in user.genre_preferences.items():
                combined_scores[genre] += score * 5.0
        
        # 2. Thumbs up/down preferences (weight: 3.0 - INCREASED)
        thumbs_prefs = self._get_thumbs_based_genre_preferences(user_id)
        for genre, score in thumbs_prefs['genre_scores'].items():
            combined_scores[genre] += score * 3.0
        
        # 3. High-rated movies (weight: 0.5 - DECREASED and CAPPED)
        # Use square root to reduce over-representation of dominant genres
        high_ratings = self.db.query(Rating).filter(
            Rating.user_id == user_id,
            Rating.rating >= 4.0
        ).all()
        
        if high_ratings:
            movie_ids = [r.movie_id for r in high_ratings]
            movies = self.db.query(Movie).filter(Movie.id.in_(movie_ids)).all()
            
            # Count genres first
            genre_counts = defaultdict(int)
            for movie in movies:
                if movie.genres:
                    try:
                        genres = movie.genres if isinstance(movie.genres, list) else json.loads(movie.genres)
                        for genre in genres:
                            genre_counts[genre] += 1
                    except:
                        pass
            
            # Apply square root dampening to prevent over-representation
            import math
            for genre, count in genre_counts.items():
                # Square root dampening: 26 movies → sqrt(26) ≈ 5.1
                dampened_score = math.sqrt(count) * 0.5
                combined_scores[genre] += dampened_score
        
        # Normalize scores
        if combined_scores:
            max_score = max(abs(s) for s in combined_scores.values())
            if max_score > 0:
                combined_scores = {g: s / max_score for g, s in combined_scores.items()}
        
        return {
            'genre_scores': dict(combined_scores),
            'preferred_genres': set(g for g, s in combined_scores.items() if s > 0.2),  # Lowered threshold
            'disliked_genres': set(g for g, s in combined_scores.items() if s < -0.2)  # Lowered threshold
        }
    
    def _apply_enhanced_diversification(self, movies: list, user_id: int, context: dict = None) -> list:
        """
        Enhanced diversification that combines:
        1. Age-based preferences
        2. Temporal preferences (time of day, weekend)
        3. User genre preferences (onboarding + thumbs + ratings)
        4. Genre diversity (prevent fatigue)
        
        Args:
            movies: List of movie objects
            user_id: User ID
            context: Optional context dict from _get_contextual_features
        
        Returns:
            Reordered list of movies with enhanced diversification
        """
        if not movies:
            return movies
        
        user = self.db.query(User).filter(User.id == user_id).first()
        
        # Get context if not provided
        if context is None:
            context = self._get_contextual_features(user_id)
        
        # Get user's comprehensive genre preferences
        user_genre_prefs = self._get_user_genre_preferences_combined(user_id)
        
        # Get temporal preferences
        temporal_prefs = self._get_enhanced_temporal_preferences(
            hour=context['temporal']['hour'],
            day_of_week=context['temporal']['day_of_week'],
            age=user.age if user else None
        )
        
        # Get age-based preferences
        age_prefs = None
        if user and user.age:
            age_prefs = self._get_age_based_genre_preferences(user.age)
        
        # Score each movie
        movie_scores = []
        for movie in movies:
            score = 0.0
            
            if movie.genres:
                try:
                    genres = movie.genres if isinstance(movie.genres, list) else json.loads(movie.genres)
                    movie_genre_set = set(genres)
                    
                    # 1. User genre preference score (weight: 4.0)
                    for genre in movie_genre_set:
                        if genre in user_genre_prefs['genre_scores']:
                            score += user_genre_prefs['genre_scores'][genre] * 4.0
                    
                    # 2. Temporal relevance score (weight: 2.0)
                    temporal_match = len(movie_genre_set & set(temporal_prefs['genres']))
                    score += temporal_match * 2.0
                    
                    # 3. Age appropriateness score (weight: 1.5)
                    if age_prefs:
                        age_preferred_match = len(movie_genre_set & set(age_prefs['preferred']))
                        age_avoid_match = len(movie_genre_set & set(age_prefs['avoid']))
                        score += age_preferred_match * 1.5
                        score -= age_avoid_match * 2.0  # Penalty for age-inappropriate
                    
                    # 4. Diversity bonus (weight: 1.5)
                    if context['recent_genres']:
                        new_genres = movie_genre_set - context['recent_genres']
                        score += len(new_genres) * 1.5
                        
                        # Penalty for oversaturated genres
                        for genre in movie_genre_set:
                            if genre in context['genre_saturation']:
                                saturation = context['genre_saturation'][genre]
                                score -= saturation * 1.0
                    
                    # 5. Runtime appropriateness (weight: 0.5)
                    if hasattr(movie, 'runtime') and movie.runtime:
                        runtime_pref = temporal_prefs.get('runtime_pref', 'medium')
                        if runtime_pref == 'short' and movie.runtime < 100:
                            score += 0.5
                        elif runtime_pref == 'medium' and 90 <= movie.runtime <= 130:
                            score += 0.5
                        elif runtime_pref == 'long' and movie.runtime > 110:
                            score += 0.5
                    
                except Exception as e:
                    logger.warning(f"Error scoring movie {movie.id}: {e}")
            
            movie_scores.append((movie, score))
        
        # Sort by score (descending)
        movie_scores.sort(key=lambda x: x[1], reverse=True)
        
        logger.info(f"Enhanced diversification applied: "
                   f"age={user.age if user else 'N/A'}, "
                   f"time={temporal_prefs.get('mood', 'N/A')}, "
                   f"user_prefs={len(user_genre_prefs['preferred_genres'])} genres")
        
        return [movie for movie, _ in movie_scores]

    # =============================================================================
    # FEEDBACK-DRIVEN ALGORITHM ADJUSTMENT
    # =============================================================================
    
    def _get_user_feedback_profile(self, user_id: int) -> dict:
        """
        Create comprehensive user feedback profile from all interactions
        
        Returns:
            dict: {
                'strong_likes': set of movie IDs with 4.5+ ratings or thumbs up,
                'likes': set of movie IDs with 3.5-4.4 ratings,
                'neutral': set of movie IDs with 2.5-3.4 ratings,
                'dislikes': set of movie IDs with 1.5-2.4 ratings,
                'strong_dislikes': set of movie IDs with <1.5 ratings or thumbs down,
                'genre_preferences': dict with genre scores from all feedback,
                'director_preferences': dict with director scores,
                'actor_preferences': dict with actor scores,
                'feedback_strength': float indicating how much feedback user has given
            }
        """
        # Get all user interactions
        ratings = self.db.query(Rating).filter(Rating.user_id == user_id).all()
        thumbs_up_ids = set(self._get_thumbs_up_movie_ids(user_id))
        thumbs_down_ids = set(self._get_thumbs_down_movie_ids(user_id))
        
        # Categorize by rating strength
        strong_likes = set()
        likes = set()
        neutral = set()
        dislikes = set()
        strong_dislikes = set()
        
        for rating in ratings:
            movie_id = rating.movie_id
            rating_value = rating.rating
            
            if movie_id in thumbs_up_ids:
                strong_likes.add(movie_id)
            elif movie_id in thumbs_down_ids:
                strong_dislikes.add(movie_id)
            elif rating_value >= 4.5:
                strong_likes.add(movie_id)
            elif rating_value >= 3.5:
                likes.add(movie_id)
            elif rating_value >= 2.5:
                neutral.add(movie_id)
            elif rating_value >= 1.5:
                dislikes.add(movie_id)
            else:
                strong_dislikes.add(movie_id)
        
        # Analyze preferences from feedback
        genre_preferences = defaultdict(float)
        director_preferences = defaultdict(float)
        actor_preferences = defaultdict(float)
        
        # Get movie details for analysis
        all_movie_ids = strong_likes | likes | neutral | dislikes | strong_dislikes
        movies = self.db.query(Movie).filter(Movie.id.in_(all_movie_ids)).all()
        
        for movie in movies:
            movie_id = movie.id
            
            # Determine preference weight
            if movie_id in strong_likes:
                weight = 3.0
            elif movie_id in likes:
                weight = 2.0
            elif movie_id in neutral:
                weight = 0.5
            elif movie_id in dislikes:
                weight = -1.5
            elif movie_id in strong_dislikes:
                weight = -3.0
            else:
                continue
            
            # Analyze genres
            if movie.genres:
                try:
                    genres = movie.genres if isinstance(movie.genres, list) else json.loads(movie.genres)
                    for genre in genres:
                        genre_preferences[genre] += weight
                except:
                    pass
            
            # Analyze directors
            if movie.crew:
                try:
                    crew = movie.crew if isinstance(movie.crew, list) else json.loads(movie.crew)
                    for person in crew:
                        if person.get('job') == 'Director':
                            director_preferences[person.get('name')] += weight
                except:
                    pass
            
            # Analyze top actors
            if movie.cast:
                try:
                    cast = movie.cast if isinstance(movie.cast, list) else json.loads(movie.cast)
                    for actor in cast[:3]:  # Top 3 actors
                        actor_preferences[actor.get('name')] += weight
                except:
                    pass
        
        # Calculate feedback strength (0-1, where 1 = lots of feedback)
        total_interactions = len(ratings) + len(thumbs_up_ids) + len(thumbs_down_ids)
        feedback_strength = min(total_interactions / 20.0, 1.0)  # Max at 20 interactions
        
        return {
            'strong_likes': strong_likes,
            'likes': likes,
            'neutral': neutral,
            'dislikes': dislikes,
            'strong_dislikes': strong_dislikes,
            'genre_preferences': dict(genre_preferences),
            'director_preferences': dict(director_preferences),
            'actor_preferences': dict(actor_preferences),
            'feedback_strength': feedback_strength
        }
    
    def _get_dynamic_algorithm_weights(self, user_id: int) -> dict:
        """
        Dynamically adjust algorithm weights based on user feedback patterns
        
        Returns:
            dict: Algorithm weights that adapt to user preferences
        """
        feedback_profile = self._get_user_feedback_profile(user_id)
        feedback_strength = feedback_profile['feedback_strength']
        
        # Base weights
        base_weights = {
            'svd': 0.4,
            'item_cf': 0.3,
            'content': 0.2,
            'embedding': 0.1
        }
        
        # Adjust based on feedback patterns
        if feedback_strength < 0.3:
            # Low feedback - rely more on content and demographics
            base_weights['content'] += 0.2
            base_weights['svd'] -= 0.1
            base_weights['item_cf'] -= 0.1
        elif feedback_strength > 0.7:
            # High feedback - rely more on collaborative filtering
            base_weights['svd'] += 0.15
            base_weights['item_cf'] += 0.1
            base_weights['content'] -= 0.15
            base_weights['embedding'] -= 0.1
        
        # Adjust based on rating patterns
        strong_likes_count = len(feedback_profile['strong_likes'])
        strong_dislikes_count = len(feedback_profile['strong_dislikes'])
        
        if strong_dislikes_count > strong_likes_count:
            # User has strong dislikes - increase content filtering
            base_weights['content'] += 0.1
            base_weights['svd'] -= 0.05
            base_weights['item_cf'] -= 0.05
        
        # Normalize weights
        total_weight = sum(base_weights.values())
        normalized_weights = {k: v / total_weight for k, v in base_weights.items()}
        
        logger.info(f"Dynamic algorithm weights for user {user_id}: {normalized_weights}")
        
        return normalized_weights
    
    def _apply_feedback_driven_scoring(self, movies: list, user_id: int) -> list:
        """
        Apply sophisticated feedback-driven scoring that heavily weights dislikes
        
        Args:
            movies: List of Movie objects
            user_id: User ID
            
        Returns:
            Reordered list with feedback-driven scoring
        """
        if not movies:
            return movies
        
        feedback_profile = self._get_user_feedback_profile(user_id)
        
        # Pre-calculate similarity sets to avoid repeated expensive calculations
        thumbs_down_ids = self._get_thumbs_down_movie_ids(user_id)
        thumbs_up_ids = self._get_thumbs_up_movie_ids(user_id)
        high_rated_movies = feedback_profile['strong_likes'] | feedback_profile['likes']
        
        # Cache similarity results
        similar_to_disliked = set()
        similar_to_liked = set()
        similar_to_high_rated = set()
        
        if thumbs_down_ids:
            similar_to_disliked = self._get_similar_movie_ids(thumbs_down_ids, similarity_threshold=0.4)
        if thumbs_up_ids:
            similar_to_liked = self._get_similar_movie_ids(thumbs_up_ids, similarity_threshold=0.3)
        if high_rated_movies:
            similar_to_high_rated = self._get_similar_movie_ids(list(high_rated_movies), similarity_threshold=0.3)
        
        movie_scores = []
        for movie in movies:
            score = 0.0
            
            # 1. Genre preferences (weight: 5.0 - highest priority)
            if movie.genres:
                try:
                    genres = movie.genres if isinstance(movie.genres, list) else json.loads(movie.genres)
                    genre_score = 0.0
                    for genre in genres:
                        if genre in feedback_profile['genre_preferences']:
                            genre_score += feedback_profile['genre_preferences'][genre]
                    score += genre_score * 5.0
                except:
                    pass
            
            # 2. Director preferences (weight: 3.0)
            if movie.crew:
                try:
                    crew = movie.crew if isinstance(movie.crew, list) else json.loads(movie.crew)
                    for person in crew:
                        if person.get('job') == 'Director' and person.get('name') in feedback_profile['director_preferences']:
                            score += feedback_profile['director_preferences'][person.get('name')] * 3.0
                except:
                    pass
            
            # 3. Actor preferences (weight: 2.0)
            if movie.cast:
                try:
                    cast = movie.cast if isinstance(movie.cast, list) else json.loads(movie.cast)
                    actor_score = 0.0
                    for actor in cast[:3]:  # Top 3 actors
                        if actor.get('name') in feedback_profile['actor_preferences']:
                            actor_score += feedback_profile['actor_preferences'][actor.get('name')]
                    score += actor_score * 2.0
                except:
                    pass
            
            # 4. Similarity to strongly disliked movies (heavy penalty) - use cached result
            if movie.id in similar_to_disliked:
                score -= 10.0  # Heavy penalty for similarity to disliked movies
            
            # 5. Similarity to strongly liked movies (boost) - use cached result
            if movie.id in similar_to_liked:
                score += 8.0  # Strong boost for similarity to liked movies
            
            # 6. Rating-based similarity - use cached result
            if movie.id in similar_to_high_rated:
                score += 6.0
            
            movie_scores.append((movie, score))
        
        # Sort by score (descending)
        movie_scores.sort(key=lambda x: x[1], reverse=True)
        
        logger.info(f"Applied feedback-driven scoring: "
                   f"strong_likes={len(feedback_profile['strong_likes'])}, "
                   f"strong_dislikes={len(feedback_profile['strong_dislikes'])}, "
                   f"feedback_strength={feedback_profile['feedback_strength']:.2f}")
        
        return [movie for movie, _ in movie_scores]
    
    def _get_adaptive_recommendation_strategy(self, user_id: int) -> str:
        """
        Determine the best recommendation strategy based on user feedback patterns
        
        Returns:
            str: Strategy name ('conservative', 'balanced', 'exploratory', 'preference_focused')
        """
        feedback_profile = self._get_user_feedback_profile(user_id)
        
        strong_likes_count = len(feedback_profile['strong_likes'])
        strong_dislikes_count = len(feedback_profile['strong_dislikes'])
        feedback_strength = feedback_profile['feedback_strength']
        
        # Determine strategy based on patterns
        if feedback_strength < 0.2:
            return 'exploratory'  # Not enough feedback, explore broadly
        elif strong_dislikes_count > strong_likes_count * 1.5:
            return 'conservative'  # User has strong dislikes, be conservative
        elif strong_likes_count > strong_dislikes_count * 2:
            return 'preference_focused'  # User has clear preferences, focus on them
        else:
            return 'balanced'  # Balanced approach
    
    def get_feedback_driven_recommendations(self, user_id: int, n_recommendations: int = 10) -> list:
        """
        Get recommendations using feedback-driven approach that heavily weights dislikes
        
        Args:
            user_id: User ID
            n_recommendations: Number of recommendations
            
        Returns:
            List of recommended movies
        """
        # Get adaptive strategy
        strategy = self._get_adaptive_recommendation_strategy(user_id)
        
        # Get dynamic algorithm weights
        algorithm_weights = self._get_dynamic_algorithm_weights(user_id)
        
        # Generate recommendations using weighted algorithms
        all_recommendations = []
        seen_ids = set()
        
        # SVD recommendations
        if algorithm_weights['svd'] > 0:
            svd_count = int(n_recommendations * algorithm_weights['svd'])
            svd_recs = self.get_svd_recommendations(user_id, svd_count)
            for movie in svd_recs:
                if movie.id not in seen_ids:
                    all_recommendations.append(movie)
                    seen_ids.add(movie.id)
        
        # Item-based CF recommendations
        if algorithm_weights['item_cf'] > 0:
            item_count = int(n_recommendations * algorithm_weights['item_cf'])
            item_recs = self.get_item_based_recommendations(user_id, item_count)
            for movie in item_recs:
                if movie.id not in seen_ids:
                    all_recommendations.append(movie)
                    seen_ids.add(movie.id)
        
        # Content-based recommendations
        if algorithm_weights['content'] > 0:
            content_count = int(n_recommendations * algorithm_weights['content'])
            content_recs = self.get_content_based_recommendations(user_id, content_count)
            for movie in content_recs:
                if movie.id not in seen_ids:
                    all_recommendations.append(movie)
                    seen_ids.add(movie.id)
        
        # If we don't have enough recommendations, get more from popular movies
        if len(all_recommendations) < n_recommendations:
            logger.info(f"Only got {len(all_recommendations)} recommendations, fetching popular movies to reach {n_recommendations}")
            # Fetch even fewer popular movies for better performance
            popular_count = min(n_recommendations - len(all_recommendations) + 5, 20)
            popular_movies = self._get_popular_movies(popular_count, user_id)
            for movie in popular_movies:
                if movie.id not in seen_ids and len(all_recommendations) < n_recommendations + 10:
                    all_recommendations.append(movie)
                    seen_ids.add(movie.id)
        
        # Apply feedback-driven scoring
        scored_recommendations = self._apply_feedback_driven_scoring(all_recommendations, user_id)
        
        # Filter out disliked genres (CRITICAL: was missing!)
        scored_recommendations = self._filter_disliked_genres(scored_recommendations, user_id)
        
        # Apply thumbs up/down filtering
        scored_recommendations = self._filter_similar_to_thumbs_down(scored_recommendations, user_id)
        scored_recommendations = self._boost_similar_to_thumbs_up(scored_recommendations, user_id)
        
        logger.info(f"Feedback-driven recommendations: strategy={strategy}, "
                   f"weights={algorithm_weights}, count={len(scored_recommendations)}")
        
        return scored_recommendations[:n_recommendations]