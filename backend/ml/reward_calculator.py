"""
Reward Calculator for Multi-Armed Bandit Experiments

Computes rewards from user interactions with configurable definitions:
- Binary rewards: clicked OR watched ≥ 50% within 24h = 1.0, else 0.0
- Scaled rewards: watch_time / duration or rating / 5.0
- Time window logic for delayed rewards
- Idempotent updates
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from ..models import RecommendationEvent, Rating, Favorite, WatchlistItem

logger = logging.getLogger(__name__)

class RewardCalculator:
    """Calculates rewards from user interactions"""
    
    def __init__(self, db: Session):
        self.db = db
        self.default_window_hours = 24
        self.binary_threshold = 0.5  # 50% watch time for binary reward
        self.rating_threshold = 4.0  # Rating ≥ 4.0 is positive
    
    def compute_reward(self, event: RecommendationEvent, 
                      interactions: Optional[List[Dict[str, Any]]] = None,
                      reward_type: str = "binary") -> float:
        """
        Compute reward for a recommendation event
        
        Args:
            event: RecommendationEvent to compute reward for
            interactions: Optional pre-fetched interactions
            reward_type: "binary" or "scaled"
            
        Returns:
            Reward value (0.0 to 1.0)
        """
        if event.reward is not None:
            # Already computed
            return event.reward
        
        # Get interactions if not provided
        if interactions is None:
            interactions = self._get_user_interactions(
                event.user_id, 
                event.movie_id, 
                event.served_at or event.created_at
            )
        
        # Compute reward based on type
        if reward_type == "binary":
            reward = self._compute_binary_reward(event, interactions)
        elif reward_type == "scaled":
            reward = self._compute_scaled_reward(event, interactions)
        else:
            raise ValueError(f"Unknown reward type: {reward_type}")
        
        # Update event with computed reward
        event.reward = reward
        self.db.commit()
        
        logger.debug(f"Computed {reward_type} reward {reward:.3f} for event {event.id}")
        return reward
    
    def _compute_binary_reward(self, event: RecommendationEvent, 
                              interactions: List[Dict[str, Any]]) -> float:
        """Compute binary reward (0.0 or 1.0)"""
        
        # Check for immediate positive signals
        if event.clicked:
            return 1.0
        
        if event.thumbs_up:
            return 1.0
        
        if event.added_to_favorites:
            return 1.0
        
        # Check for negative signals
        if event.thumbs_down:
            return 0.0
        
        # Check rating
        if event.rated and event.rating_value is not None:
            if event.rating_value >= self.rating_threshold:
                return 1.0
            elif event.rating_value <= 2.0:  # Strong negative
                return 0.0
            # Neutral ratings (2.5-3.5) don't contribute to binary reward
        
        # Check for watchlist addition (weak positive signal)
        if event.added_to_watchlist:
            return 0.7  # Partial reward
        
        # Check interactions within time window
        window_start = event.served_at or event.created_at
        window_end = window_start + timedelta(hours=self.default_window_hours)
        
        for interaction in interactions:
            if not (window_start <= interaction['timestamp'] <= window_end):
                continue
            
            # Rating interaction
            if interaction['type'] == 'rating':
                if interaction['value'] >= self.rating_threshold:
                    return 1.0
                elif interaction['value'] <= 2.0:
                    return 0.0
            
            # Watch interaction (if we had watch time data)
            elif interaction['type'] == 'watch':
                watch_ratio = interaction.get('watch_ratio', 0.0)
                if watch_ratio >= self.binary_threshold:
                    return 1.0
            
            # Favorite interaction
            elif interaction['type'] == 'favorite':
                return 1.0
            
            # Watchlist interaction
            elif interaction['type'] == 'watchlist':
                return 0.7
        
        # No positive interactions found
        return 0.0
    
    def _compute_scaled_reward(self, event: RecommendationEvent, 
                              interactions: List[Dict[str, Any]]) -> float:
        """Compute scaled reward (0.0 to 1.0) based on interaction strength"""
        
        # Start with base reward from immediate signals
        base_reward = 0.0
        
        if event.clicked:
            base_reward += 0.3
        
        if event.thumbs_up:
            base_reward += 0.4
        
        if event.thumbs_down:
            base_reward -= 0.3
        
        if event.added_to_favorites:
            base_reward += 0.5
        
        if event.added_to_watchlist:
            base_reward += 0.2
        
        # Rating contribution
        if event.rated and event.rating_value is not None:
            # Scale rating to 0-1 range
            rating_reward = (event.rating_value - 1.0) / 4.0  # (rating - 1) / 4
            base_reward += rating_reward * 0.6  # Weight rating contribution
        
        # Check interactions within time window
        window_start = event.served_at or event.created_at
        window_end = window_start + timedelta(hours=self.default_window_hours)
        
        for interaction in interactions:
            if not (window_start <= interaction['timestamp'] <= window_end):
                continue
            
            if interaction['type'] == 'rating':
                rating_reward = (interaction['value'] - 1.0) / 4.0
                base_reward += rating_reward * 0.4
            
            elif interaction['type'] == 'watch':
                watch_ratio = interaction.get('watch_ratio', 0.0)
                base_reward += watch_ratio * 0.3
            
            elif interaction['type'] == 'favorite':
                base_reward += 0.3
            
            elif interaction['type'] == 'watchlist':
                base_reward += 0.1
        
        # Clamp to [0, 1] range
        return max(0.0, min(1.0, base_reward))
    
    def _get_user_interactions(self, user_id: int, movie_id: int, 
                              since: datetime) -> List[Dict[str, Any]]:
        """Get user interactions with movie since given timestamp"""
        interactions = []
        
        # Get ratings
        ratings = self.db.query(Rating).filter(
            and_(
                Rating.user_id == user_id,
                Rating.movie_id == movie_id,
                Rating.timestamp >= since
            )
        ).all()
        
        for rating in ratings:
            interactions.append({
                'type': 'rating',
                'value': rating.rating,
                'timestamp': rating.timestamp
            })
        
        # Get favorites
        favorites = self.db.query(Favorite).filter(
            and_(
                Favorite.user_id == user_id,
                Favorite.movie_id == movie_id,
                Favorite.created_at >= since
            )
        ).all()
        
        for favorite in favorites:
            interactions.append({
                'type': 'favorite',
                'timestamp': favorite.created_at
            })
        
        # Get watchlist additions
        watchlist_items = self.db.query(WatchlistItem).filter(
            and_(
                WatchlistItem.user_id == user_id,
                WatchlistItem.movie_id == movie_id,
                WatchlistItem.created_at >= since
            )
        ).all()
        
        for item in watchlist_items:
            interactions.append({
                'type': 'watchlist',
                'timestamp': item.created_at
            })
        
        # Sort by timestamp
        interactions.sort(key=lambda x: x['timestamp'])
        
        return interactions
    
    def batch_compute_rewards(self, events: List[RecommendationEvent], 
                             reward_type: str = "binary") -> Dict[int, float]:
        """
        Compute rewards for multiple events efficiently
        
        Args:
            events: List of RecommendationEvent objects
            reward_type: "binary" or "scaled"
            
        Returns:
            Dictionary mapping event_id to reward value
        """
        rewards = {}
        
        # Group events by user_id for efficient interaction fetching
        user_events = {}
        for event in events:
            if event.user_id not in user_events:
                user_events[event.user_id] = []
            user_events[event.user_id].append(event)
        
        # Process each user's events
        for user_id, user_event_list in user_events.items():
            # Get all interactions for this user since earliest event
            earliest_time = min(
                (event.served_at or event.created_at) 
                for event in user_event_list
            )
            
            # Get all movies involved
            movie_ids = [event.movie_id for event in user_event_list]
            
            # Fetch interactions for all movies
            interactions_by_movie = {}
            for movie_id in movie_ids:
                interactions_by_movie[movie_id] = self._get_user_interactions(
                    user_id, movie_id, earliest_time
                )
            
            # Compute rewards for each event
            for event in user_event_list:
                movie_interactions = interactions_by_movie.get(event.movie_id, [])
                reward = self.compute_reward(event, movie_interactions, reward_type)
                rewards[event.id] = reward
        
        return rewards
    
    def get_pending_events(self, hours_back: int = 24) -> List[RecommendationEvent]:
        """Get events that need reward computation"""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
        
        return self.db.query(RecommendationEvent).filter(
            and_(
                RecommendationEvent.reward.is_(None),
                RecommendationEvent.served_at >= cutoff_time
            )
        ).all()
    
    def update_event_reward(self, event_id: int, reward: float) -> bool:
        """Update reward for a specific event"""
        try:
            event = self.db.query(RecommendationEvent).filter(
                RecommendationEvent.id == event_id
            ).first()
            
            if event:
                event.reward = reward
                self.db.commit()
                return True
            return False
            
        except Exception as e:
            logger.error(f"Failed to update reward for event {event_id}: {e}")
            self.db.rollback()
            return False
    
    def get_reward_statistics(self, experiment_id: Optional[str] = None,
                            policy: Optional[str] = None,
                            arm_id: Optional[str] = None) -> Dict[str, Any]:
        """Get reward statistics for analysis"""
        query = self.db.query(RecommendationEvent).filter(
            RecommendationEvent.reward.isnot(None)
        )
        
        if experiment_id:
            query = query.filter(RecommendationEvent.experiment_id == experiment_id)
        
        if policy:
            query = query.filter(RecommendationEvent.policy == policy)
        
        if arm_id:
            query = query.filter(RecommendationEvent.arm_id == arm_id)
        
        events = query.all()
        
        if not events:
            return {
                'count': 0,
                'mean_reward': 0.0,
                'std_reward': 0.0,
                'min_reward': 0.0,
                'max_reward': 0.0,
                'positive_rate': 0.0
            }
        
        rewards = [event.reward for event in events]
        
        import statistics
        mean_reward = statistics.mean(rewards)
        std_reward = statistics.stdev(rewards) if len(rewards) > 1 else 0.0
        positive_rate = sum(1 for r in rewards if r > 0.5) / len(rewards)
        
        return {
            'count': len(events),
            'mean_reward': mean_reward,
            'std_reward': std_reward,
            'min_reward': min(rewards),
            'max_reward': max(rewards),
            'positive_rate': positive_rate
        }
