from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_, String
from typing import Optional, List
from ..database import get_db
from ..models import Movie as MovieModel, Genre as GenreModel, User
from ..schemas import Movie, MovieList, Genre
from ..ml.recommender import MovieRecommender
from ..auth import get_current_user

router = APIRouter(prefix="/movies", tags=["movies"])

@router.get("/", response_model=MovieList)
def get_movies(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    genre: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = Query("popularity", regex="^(popularity|vote_average|release_date|title)$"),
    db: Session = Depends(get_db)
):
    """Get paginated list of movies with optional filters"""
    
    query = db.query(MovieModel)
    
    # Filter by genre
    if genre:
        query = query.filter(MovieModel.genres.cast(String).contains(genre))
    
    # Search by title or overview
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                MovieModel.title.ilike(search_term),
                MovieModel.overview.ilike(search_term)
            )
        )
    
    # Sorting
    if sort_by == "popularity":
        query = query.order_by(desc(MovieModel.popularity))
    elif sort_by == "vote_average":
        query = query.order_by(desc(MovieModel.vote_average))
    elif sort_by == "release_date":
        query = query.order_by(desc(MovieModel.release_date))
    elif sort_by == "title":
        query = query.order_by(MovieModel.title)
    
    # Get total count
    total = query.count()
    
    # Pagination
    offset = (page - 1) * page_size
    movies = query.offset(offset).limit(page_size).all()
    
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "movies": movies
    }

@router.get("/recommendations", response_model=List[Movie])
def get_recommendations(
    user_id: int = Query(...),
    limit: int = Query(30, ge=1, le=50),
    offset: int = Query(0, ge=0),
    seed: Optional[int] = Query(None, description="Optional seed to shuffle results deterministically"),
    use_bandit: bool = Query(True, description="Use bandit algorithm selection (A/B testing)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get personalized movie recommendations for a user
    
    Now with intelligent algorithm selection using Thompson Sampling!
    
    Features:
    - Automatically selects best algorithms based on context (time, user type, etc.)
    - Learns from user feedback (clicks, ratings, thumbs)
    - Balances exploration (trying new algorithms) vs exploitation (using known good ones)
    - Filters out disliked genres and low-rated movies
    - Provides diverse recommendations across genres
    
    Query Parameters:
    - use_bandit=true: Use Thompson Sampling bandit (default, A/B test)
    - use_bandit=false: Use classic hybrid approach (control group)
    """
    
    # Verify the user is requesting their own recommendations
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to view these recommendations")
    
    recommender = MovieRecommender(db)
    
    # A/B TEST: Bandit vs Hybrid
    if use_bandit:
        # NEW: Thompson Sampling Bandit approach
        pool_size = max(limit + offset + 50, 50)
        pool_size = min(pool_size, 500)
        
        try:
            result = recommender.get_bandit_recommendations(
                user_id=user_id,
                n_recommendations=pool_size
            )
            
            # Extract movies and algorithm info
            recommendations_with_algo = result['recommendations']
            context = result['context']
            
            # Apply offset/limit window
            recommendations_with_algo = recommendations_with_algo[offset:offset + limit]
            
            # Track recommendations with proper algorithm attribution
            for position, rec_data in enumerate(recommendations_with_algo, start=1):
                try:
                    recommender.track_recommendation(
                        user_id=user_id,
                        movie_id=rec_data['movie'].id,
                        algorithm=f"bandit_{rec_data['algorithm']}",  # e.g., "bandit_svd"
                        position=position,
                        score=rec_data['confidence'],
                        context=context
                    )
                except Exception as e:
                    import logging
                    logging.warning(f"Failed to track bandit recommendation: {e}")
            
            # Return just the movies (strip algorithm metadata for API response)
            return [rec['movie'] for rec in recommendations_with_algo]
            
        except Exception as e:
            # Fallback to hybrid if bandit fails
            import logging
            logging.error(f"Bandit recommendation failed, falling back to hybrid: {e}")
            use_bandit = False
    
    if not use_bandit:
        # CONTROL: Classic hybrid approach
        pool_size = max(limit + offset + 50, 50)
        pool_size = min(pool_size, 500)
        recommendations = recommender.get_hybrid_recommendations(
            user_id, 
            pool_size, 
            use_context=False,
            use_embeddings=False,
            use_graph=False
        )

        # Optionally shuffle using seed for deterministic reshuffling
        if seed is not None and len(recommendations) > 1:
            import random
            rng = random.Random(int(seed))
            rng.shuffle(recommendations)

        # Apply offset/limit window
        recommendations = recommendations[offset:offset + limit]
        
        # Track recommendations for analytics
        try:
            for position, movie in enumerate(recommendations, start=1):
                recommender.track_recommendation(
                    user_id=user_id,
                    movie_id=movie.id,
                    algorithm='hybrid_control',
                    position=position
                )
        except Exception as e:
            # Don't fail the request if tracking fails
            import logging
            logging.warning(f"Failed to track recommendations: {e}")
        
        return recommendations

# REMOVED: Old context-aware and feedback-driven endpoints
# Everything is now unified in the main /recommendations endpoint

@router.get("/top-rated", response_model=List[Movie])
def get_top_rated(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """Get top rated movies"""
    
    movies = db.query(MovieModel)\
        .filter(MovieModel.vote_count >= 100)\
        .order_by(desc(MovieModel.vote_average))\
        .limit(limit)\
        .all()
    
    return movies

@router.get("/genres/list", response_model=List[Genre])
def get_genres(db: Session = Depends(get_db)):
    """Get all available genres"""
    
    genres = db.query(GenreModel).all()
    return genres

@router.get("/{movie_id}", response_model=Movie)
def get_movie(movie_id: int, db: Session = Depends(get_db)):
    """Get a specific movie by ID"""
    
    movie = db.query(MovieModel).filter(MovieModel.id == movie_id).first()
    
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    
    return movie