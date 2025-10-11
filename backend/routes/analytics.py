"""
Analytics and A/B Testing Endpoints
"""
from fastapi import APIRouter, Depends, Query, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

from ..database import get_db
from ..auth import get_current_user
from ..models import User
from ..ml.recommender import MovieRecommender

router = APIRouter(prefix="/analytics", tags=["analytics"])


# Schemas
class RecommendationClickSchema(BaseModel):
    user_id: int
    movie_id: int


class RecommendationRatingSchema(BaseModel):
    user_id: int
    movie_id: int
    rating: float


class RecommendationThumbsUpSchema(BaseModel):
    user_id: int
    movie_id: int


class RecommendationThumbsDownSchema(BaseModel):
    user_id: int
    movie_id: int


class PerformanceMetrics(BaseModel):
    algorithm: str
    total_recommendations: int
    total_clicks: int
    total_ratings: int
    avg_rating: Optional[float]
    total_favorites: int
    total_watchlist: int
    total_thumbs_up: int
    total_thumbs_down: int
    ctr: float
    rating_rate: float
    thumbs_up_rate: float
    thumbs_down_rate: float


class AlgorithmPerformanceResponse(BaseModel):
    period_days: int
    algorithms: dict


class ModelUpdateResponse(BaseModel):
    id: int
    model_type: str
    update_type: str
    ratings_processed: Optional[int]
    update_trigger: Optional[str]
    metrics: Optional[dict]
    duration_seconds: Optional[float]
    success: bool
    created_at: Optional[str]


class ForceUpdateRequest(BaseModel):
    update_type: str = "full_retrain"  # full_retrain, warm_start


# Endpoints
@router.post("/track/click")
async def track_recommendation_click(
    data: RecommendationClickSchema,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Track when a user clicks on a recommended movie
    Also updates bandit with success signal
    """
    def track_click():
        from ..models import RecommendationEvent
        from ..ml.bandit_selector import BanditSelector
        
        recommender = MovieRecommender(db)
        recommender.track_recommendation_click(data.user_id, data.movie_id)
        
        # Update bandit - clicks are successes
        try:
            # Get the recommendation event to find algorithm and context
            event = db.query(RecommendationEvent).filter(
                RecommendationEvent.user_id == data.user_id,
                RecommendationEvent.movie_id == data.movie_id
            ).order_by(RecommendationEvent.created_at.desc()).first()
            
            if event and event.algorithm and event.context:
                # Extract the base algorithm name (remove "bandit_" prefix if present)
                algorithm = event.algorithm.replace('bandit_', '') if event.algorithm.startswith('bandit_') else event.algorithm
                
                # Update bandit state
                bandit = BanditSelector(db)
                bandit.update_bandit(event.context, algorithm, 'success')
        except Exception as e:
            import logging
            logging.warning(f"Failed to update bandit for click: {e}")
    
    # Run in background to not slow down response
    background_tasks.add_task(track_click)
    
    return {"status": "tracked", "action": "click"}


@router.post("/track/rating")
async def track_recommendation_rating(
    data: RecommendationRatingSchema,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Track when a user rates a recommended movie
    Also updates bandit based on rating value
    """
    def track_rating():
        from ..models import RecommendationEvent
        from ..ml.bandit_selector import BanditSelector
        
        recommender = MovieRecommender(db)
        recommender.track_recommendation_rating(data.user_id, data.movie_id, data.rating)
        
        # Update bandit based on rating
        try:
            # Get the recommendation event
            event = db.query(RecommendationEvent).filter(
                RecommendationEvent.user_id == data.user_id,
                RecommendationEvent.movie_id == data.movie_id
            ).order_by(RecommendationEvent.created_at.desc()).first()
            
            if event and event.algorithm and event.context:
                # Extract base algorithm name
                algorithm = event.algorithm.replace('bandit_', '') if event.algorithm.startswith('bandit_') else event.algorithm
                
                # Determine outcome based on rating
                if data.rating >= 4.0:
                    outcome = 'success'
                elif data.rating <= 2.0:
                    outcome = 'failure'
                else:
                    outcome = 'neutral'
                
                # Update bandit state
                bandit = BanditSelector(db)
                bandit.update_bandit(event.context, algorithm, outcome)
        except Exception as e:
            import logging
            logging.warning(f"Failed to update bandit for rating: {e}")
    
    # Run in background
    background_tasks.add_task(track_rating)
    
    return {"status": "tracked", "action": "rating"}


@router.post("/track/favorite/{user_id}/{movie_id}")
async def track_favorite(
    user_id: int,
    movie_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Track when a user favorites a recommended movie
    """
    def track():
        recommender = MovieRecommender(db)
        recommender.track_recommendation_performance(user_id, movie_id, 'favorite')
    
    background_tasks.add_task(track)
    return {"status": "tracked", "action": "favorite"}


@router.post("/track/watchlist/{user_id}/{movie_id}")
async def track_watchlist(
    user_id: int,
    movie_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Track when a user adds a recommended movie to watchlist
    """
    def track():
        recommender = MovieRecommender(db)
        recommender.track_recommendation_performance(user_id, movie_id, 'watchlist')
    
    background_tasks.add_task(track)
    return {"status": "tracked", "action": "watchlist"}


@router.post("/track/thumbs-up")
async def track_thumbs_up(
    data: RecommendationThumbsUpSchema,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Track when a user gives thumbs up to a recommended movie
    Also updates bandit with success signal
    """
    def track():
        from ..models import RecommendationEvent
        from ..ml.bandit_selector import BanditSelector
        
        recommender = MovieRecommender(db)
        recommender.track_recommendation_thumbs_up(data.user_id, data.movie_id)
        
        # Update bandit - thumbs up is success
        try:
            event = db.query(RecommendationEvent).filter(
                RecommendationEvent.user_id == data.user_id,
                RecommendationEvent.movie_id == data.movie_id
            ).order_by(RecommendationEvent.created_at.desc()).first()
            
            if event and event.algorithm and event.context:
                algorithm = event.algorithm.replace('bandit_', '') if event.algorithm.startswith('bandit_') else event.algorithm
                bandit = BanditSelector(db)
                bandit.update_bandit(event.context, algorithm, 'success')
        except Exception as e:
            import logging
            logging.warning(f"Failed to update bandit for thumbs up: {e}")
    
    background_tasks.add_task(track)
    return {"status": "tracked", "action": "thumbs_up"}


@router.post("/track/thumbs-down")
async def track_thumbs_down(
    data: RecommendationThumbsDownSchema,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Track when a user gives thumbs down to a recommended movie
    Also updates bandit with failure signal
    """
    def track():
        from ..models import RecommendationEvent
        from ..ml.bandit_selector import BanditSelector
        
        recommender = MovieRecommender(db)
        recommender.track_recommendation_thumbs_down(data.user_id, data.movie_id)
        
        # Update bandit - thumbs down is failure
        try:
            event = db.query(RecommendationEvent).filter(
                RecommendationEvent.user_id == data.user_id,
                RecommendationEvent.movie_id == data.movie_id
            ).order_by(RecommendationEvent.created_at.desc()).first()
            
            if event and event.algorithm and event.context:
                algorithm = event.algorithm.replace('bandit_', '') if event.algorithm.startswith('bandit_') else event.algorithm
                bandit = BanditSelector(db)
                bandit.update_bandit(event.context, algorithm, 'failure')
        except Exception as e:
            import logging
            logging.warning(f"Failed to update bandit for thumbs down: {e}")
    
    background_tasks.add_task(track)
    return {"status": "tracked", "action": "thumbs_down"}


@router.get("/performance", response_model=AlgorithmPerformanceResponse)
async def get_algorithm_performance(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get performance metrics for each recommendation algorithm
    
    Requires authentication (admin/analyst only)
    """
    recommender = MovieRecommender(db)
    performance = recommender.get_algorithm_performance(days=days)
    
    return {
        "period_days": days,
        "algorithms": performance
    }


@router.get("/model/updates", response_model=List[ModelUpdateResponse])
async def get_model_updates(
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get recent model update history
    
    Requires authentication
    """
    recommender = MovieRecommender(db)
    history = recommender.get_model_update_history(limit=limit)
    
    return history


@router.post("/model/force-update")
async def force_model_update(
    request: ForceUpdateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Force a model update regardless of threshold
    
    Requires authentication (admin only)
    """
    def update_model():
        recommender = MovieRecommender(db)
        return recommender.force_model_update(update_type=request.update_type)
    
    # Run in background
    background_tasks.add_task(update_model)
    
    return {
        "status": "triggered",
        "update_type": request.update_type,
        "message": "Model update started in background"
    }


@router.get("/recommendations/stats")
async def get_recommendation_stats(
    days: int = Query(7, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get overall recommendation statistics
    """
    from ..models import RecommendationEvent
    from sqlalchemy import func
    from datetime import timedelta
    
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    # Overall stats
    stats = db.query(
        func.count(RecommendationEvent.id).label('total'),
        func.sum(func.cast(RecommendationEvent.clicked, int)).label('clicks'),
        func.sum(func.cast(RecommendationEvent.rated, int)).label('ratings'),
        func.avg(RecommendationEvent.rating_value).label('avg_rating')
    ).filter(
        RecommendationEvent.created_at >= cutoff_date
    ).first()
    
    total = stats.total or 0
    clicks = stats.clicks or 0
    ratings = stats.ratings or 0
    
    return {
        "period_days": days,
        "total_recommendations": total,
        "total_clicks": clicks,
        "total_ratings": ratings,
        "avg_rating": float(stats.avg_rating) if stats.avg_rating else None,
        "overall_ctr": (clicks / total * 100) if total > 0 else 0,
        "overall_rating_rate": (ratings / total * 100) if total > 0 else 0
    }


@router.get("/recommendations/top-performing")
async def get_top_performing_recommendations(
    limit: int = Query(10, ge=1, le=50),
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get top performing movie recommendations (by click rate)
    """
    from ..models import RecommendationEvent, Movie
    from sqlalchemy import func
    from datetime import timedelta
    
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    # Query top movies by click rate
    results = db.query(
        RecommendationEvent.movie_id,
        Movie.title,
        func.count(RecommendationEvent.id).label('times_recommended'),
        func.sum(func.cast(RecommendationEvent.clicked, int)).label('clicks'),
        func.avg(RecommendationEvent.rating_value).label('avg_rating')
    ).join(
        Movie, Movie.id == RecommendationEvent.movie_id
    ).filter(
        RecommendationEvent.created_at >= cutoff_date
    ).group_by(
        RecommendationEvent.movie_id, Movie.title
    ).order_by(
        func.sum(func.cast(RecommendationEvent.clicked, int)).desc()
    ).limit(limit).all()
    
    return [{
        'movie_id': row.movie_id,
        'title': row.title,
        'times_recommended': row.times_recommended,
        'clicks': row.clicks or 0,
        'avg_rating': float(row.avg_rating) if row.avg_rating else None,
        'ctr': ((row.clicks or 0) / row.times_recommended * 100) if row.times_recommended > 0 else 0
    } for row in results]


@router.get("/users/most-active")
async def get_most_active_users(
    limit: int = Query(10, ge=1, le=50),
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get most active users (by recommendation interactions)
    """
    from ..models import RecommendationEvent, User as UserModel
    from sqlalchemy import func, or_
    from datetime import timedelta
    
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    # Query most active users
    results = db.query(
        RecommendationEvent.user_id,
        UserModel.username,
        func.count(RecommendationEvent.id).label('recommendations_received'),
        func.sum(func.cast(RecommendationEvent.clicked, int)).label('clicks'),
        func.sum(func.cast(RecommendationEvent.rated, int)).label('ratings')
    ).join(
        UserModel, UserModel.id == RecommendationEvent.user_id
    ).filter(
        RecommendationEvent.created_at >= cutoff_date
    ).group_by(
        RecommendationEvent.user_id, UserModel.username
    ).order_by(
        func.count(RecommendationEvent.id).desc()
    ).limit(limit).all()
    
    return [{
        'user_id': row.user_id,
        'username': row.username,
        'recommendations_received': row.recommendations_received,
        'clicks': row.clicks or 0,
        'ratings': row.ratings or 0,
        'engagement_rate': ((row.clicks or 0) / row.recommendations_received * 100) if row.recommendations_received > 0 else 0
    } for row in results]


@router.get("/thumbs-status/{movie_id}")
def get_thumbs_status(
    movie_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get thumbs up/down status for a specific movie for the current user
    """
    from ..models import RecommendationEvent
    
    # Find the most recent thumbs up/down event for this user and movie
    event = db.query(RecommendationEvent).filter(
        RecommendationEvent.user_id == current_user.id,
        RecommendationEvent.movie_id == movie_id,
        (RecommendationEvent.thumbs_up == True) | (RecommendationEvent.thumbs_down == True)
    ).order_by(RecommendationEvent.created_at.desc()).first()
    
    if event:
        return {
            "thumbs_up": event.thumbs_up,
            "thumbs_down": event.thumbs_down,
            "last_updated": event.thumbs_up_at if event.thumbs_up else event.thumbs_down_at
        }
    else:
        return {
            "thumbs_up": False,
            "thumbs_down": False,
            "last_updated": None
        }


@router.post("/toggle-thumbs-up/{movie_id}")
def toggle_thumbs_up(
    movie_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Toggle thumbs up for a specific movie for the current user
    """
    from ..models import RecommendationEvent
    from datetime import datetime
    
    try:
        # Find the most recent recommendation event for this user and movie
        event = db.query(RecommendationEvent).filter(
            RecommendationEvent.user_id == current_user.id,
            RecommendationEvent.movie_id == movie_id
        ).order_by(RecommendationEvent.created_at.desc()).first()
        
        if event:
            if event.thumbs_up:
                # Currently thumbs up, remove it
                event.thumbs_up = False
                event.thumbs_up_at = None
                action = "removed"
            else:
                # Not thumbs up, add it and remove thumbs down if present
                event.thumbs_up = True
                event.thumbs_up_at = datetime.utcnow()
                event.thumbs_down = False
                event.thumbs_down_at = None
                action = "added"
            
            db.commit()
            
            return {
                "thumbs_up": event.thumbs_up,
                "thumbs_down": event.thumbs_down,
                "action": action
            }
        else:
            # No recommendation event found, create a new one
            new_event = RecommendationEvent(
                user_id=current_user.id,
                movie_id=movie_id,
                algorithm="manual",
                thumbs_up=True,
                thumbs_up_at=datetime.utcnow()
            )
            db.add(new_event)
            db.commit()
            
            return {
                "thumbs_up": True,
                "thumbs_down": False,
                "action": "added"
            }
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error toggling thumbs up: {str(e)}")


@router.post("/toggle-thumbs-down/{movie_id}")
def toggle_thumbs_down(
    movie_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Toggle thumbs down for a specific movie for the current user
    """
    from ..models import RecommendationEvent
    from datetime import datetime
    
    try:
        # Find the most recent recommendation event for this user and movie
        event = db.query(RecommendationEvent).filter(
            RecommendationEvent.user_id == current_user.id,
            RecommendationEvent.movie_id == movie_id
        ).order_by(RecommendationEvent.created_at.desc()).first()
        
        if event:
            if event.thumbs_down:
                # Currently thumbs down, remove it
                event.thumbs_down = False
                event.thumbs_down_at = None
                action = "removed"
            else:
                # Not thumbs down, add it and remove thumbs up if present
                event.thumbs_down = True
                event.thumbs_down_at = datetime.utcnow()
                event.thumbs_up = False
                event.thumbs_up_at = None
                action = "added"
            
            db.commit()
            
            return {
                "thumbs_up": event.thumbs_up,
                "thumbs_down": event.thumbs_down,
                "action": action
            }
        else:
            # No recommendation event found, create a new one
            new_event = RecommendationEvent(
                user_id=current_user.id,
                movie_id=movie_id,
                algorithm="manual",
                thumbs_down=True,
                thumbs_down_at=datetime.utcnow()
            )
            db.add(new_event)
            db.commit()
            
            return {
                "thumbs_up": False,
                "thumbs_down": True,
                "action": "added"
            }
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error toggling thumbs down: {str(e)}")


@router.get("/thumbs-movies")
def get_thumbs_movies(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all movie IDs that the current user has given thumbs up or down to
    """
    from ..models import RecommendationEvent
    
    try:
        # Get all movies with thumbs up or down
        events = db.query(RecommendationEvent.movie_id).filter(
            RecommendationEvent.user_id == current_user.id,
            (RecommendationEvent.thumbs_up == True) | (RecommendationEvent.thumbs_down == True)
        ).all()
        
        thumbs_movie_ids = [event[0] for event in events]
        
        return {
            "thumbs_movie_ids": thumbs_movie_ids,
            "count": len(thumbs_movie_ids)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching thumbs movies: {str(e)}")


@router.get("/bandit/stats")
def get_bandit_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get Thompson Sampling bandit statistics
    
    Shows performance of each algorithm in different contexts
    """
    from ..ml.bandit_selector import BanditSelector
    from ..models import BanditState
    
    try:
        bandit = BanditSelector(db)
        
        # Get all bandit states
        all_stats = bandit.get_bandit_stats()
        
        # Get summary statistics
        states = db.query(BanditState).all()
        
        total_pulls = sum(s.total_pulls for s in states)
        total_successes = sum(s.total_successes for s in states)
        total_failures = sum(s.total_failures for s in states)
        
        # Calculate per-algorithm stats
        algorithm_summary = {}
        for algo in bandit.algorithms:
            algo_states = [s for s in states if s.algorithm == algo]
            if algo_states:
                algo_pulls = sum(s.total_pulls for s in algo_states)
                algo_successes = sum(s.total_successes for s in algo_states)
                algo_failures = sum(s.total_failures for s in algo_states)
                
                algorithm_summary[algo] = {
                    'total_pulls': algo_pulls,
                    'total_successes': algo_successes,
                    'total_failures': algo_failures,
                    'success_rate': (algo_successes / (algo_successes + algo_failures)) if (algo_successes + algo_failures) > 0 else 0,
                    'selection_rate': (algo_pulls / total_pulls) if total_pulls > 0 else 0
                }
        
        return {
            'summary': {
                'total_contexts': len(set(s.context_key for s in states)),
                'total_pulls': total_pulls,
                'total_successes': total_successes,
                'total_failures': total_failures,
                'overall_success_rate': (total_successes / (total_successes + total_failures)) if (total_successes + total_failures) > 0 else 0
            },
            'algorithm_summary': algorithm_summary,
            'detailed_stats': all_stats
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching bandit stats: {str(e)}")

