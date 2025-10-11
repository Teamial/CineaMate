# Diversity Algorithm - Long-Tail Discovery Strategy

## Overview

The Diversity Algorithm addresses the "filter bubble" problem by actively recommending high-quality but underrepresented content - the "absolute bangers" users wouldn't discover on their own.

## Key Strategies

### 1. Long-Tail Discovery

**Goal**: Find hidden gems with low popularity but high quality

**Algorithm**:
```python
# Filter criteria
vote_count < 1000        # Low popularity (long-tail)
vote_average >= 7.5      # High quality
vote_count >= 50         # Minimum reliability

# Score calculation
score = (
    0.5 * quality_score +           # Base quality
    0.3 * coverage_boost +          # Underrecommended bonus
    0.2 * (1 - popularity_dampen)   # Anti-popularity bias
)
```

**Coverage Boost**: Movies rarely recommended get higher scores
**Popularity Dampening**: log(1 + popularity) reduces bias toward blockbusters

### 2. Serendipity Scoring

**Goal**: Recommend movies dissimilar to user's history but high-quality

**User Profile Building**:
1. Extract genres from high-rated movies (rating ≥ 4.0)
2. Calculate genre preferences: `{genre: count}`
3. Normalize to 0-1 scale

**Dissimilarity Calculation**:
```python
def calculate_dissimilarity(movie, user_profile):
    movie_genres = get_genres(movie)
    overlap = sum(user_profile.get(g, 0) for g in movie_genres)
    overlap_normalized = overlap / len(movie_genres)
    dissimilarity = 1.0 - overlap_normalized
    return dissimilarity
```

**Final Score**:
```python
serendipity_score = (
    0.4 * dissimilarity +    # How different from user's taste
    0.6 * quality_score      # Still maintain quality
)
```

### 3. Niche Genre Emphasis

**Target Genres**:
- Anime
- Animation (Japanese style)
- Foreign Language Films
- Documentary
- Art House
- Independent Cinema

**Boosting Strategy**:
- Identify user's openness to niche content
- If user rated any niche genre ≥ 4.0, boost all niche recommendations
- Special handling for anime: check for Animation + Japanese origin

## Implementation

### Core Class

```python
class DiversityRecommender:
    def __init__(self, db: Session):
        self.long_tail_threshold = 1000
        self.high_quality_threshold = 7.5
        self.niche_genres = {'Anime', 'Animation', 'Foreign', 'Documentary'}
    
    def get_long_tail_recommendations(self, user_id: int, n: int = 10):
        """Find hidden gems"""
        # Implementation
    
    def get_serendipity_recommendations(self, user_id: int, n: int = 10):
        """Find quality surprises"""
        # Implementation
```

### Usage Example

```python
from backend.ml.diversity_recommender import DiversityRecommender
from backend.database import SessionLocal

db = SessionLocal()
diversity_rec = DiversityRecommender(db)

# Get 10 hidden gems
hidden_gems = diversity_rec.get_long_tail_recommendations(user_id=1, n=10)

# Get 10 serendipitous picks
surprises = diversity_rec.get_serendipity_recommendations(user_id=1, n=10)
```

## Metrics

### Success Indicators

1. **Long-tail Rate**: % of recommendations with vote_count < 1000
   - Target: 30-40%
   - Baseline: 5-10%

2. **Genre Diversity**: Unique genres per recommendation list
   - Target: 0.6-0.8 (60-80% unique)
   - Baseline: 0.3-0.4

3. **Discovery CTR**: Click rate on niche content
   - Target: 15-20%
   - Monitor anime/foreign film clicks

4. **Quality Maintenance**: Avg rating of long-tail recommendations
   - Target: ≥ 4.0
   - Must not sacrifice quality for diversity

## Configuration

### Tuning Parameters

```python
# Quality vs Discovery Tradeoff
long_tail_threshold = 1000      # Lower = more diverse, higher = safer
high_quality_threshold = 7.5    # Higher = safer, lower = more exploratory

# Serendipity Balance
serendipity_weight = 0.4        # How much to favor dissimilarity
quality_weight = 0.6            # How much to favor quality

# Niche Genre Boost
niche_boost_multiplier = 1.5    # Boost factor for niche genres
```

### Recommendation Mix

Suggested proportions for hybrid system:
- 40% Traditional collaborative filtering
- 30% Long-tail discovery
- 20% Serendipity exploration
- 10% Niche genre emphasis

## Expected Results

### Before Diversity Algorithm:
- Popular movies: 90% of recommendations
- Long-tail movies: 10%
- Anime recommendations: Rare
- Genre diversity: Low (3-4 genres)

### After Diversity Algorithm:
- Popular movies: 60% of recommendations
- Long-tail movies: 35-40%
- Anime recommendations: Regular (if user shows interest)
- Genre diversity: High (6-8 genres)

### User Impact:
- "Wow, I never would have found this movie!"
- Increased exploration behavior
- Higher engagement with niche content
- Maintained satisfaction (quality preserved)

## Troubleshooting

### Issue: Not enough diversity

**Causes**:
- Threshold too high (increase long_tail_threshold)
- Quality bar too high (lower high_quality_threshold)
- User has very narrow taste profile

**Solutions**:
- Lower thresholds gradually
- Increase diversity weight in hybrid mix
- Add random exploration component

### Issue: Quality degradation

**Causes**:
- Recommending too obscure content
- Not enough user history to judge taste

**Solutions**:
- Increase high_quality_threshold
- Require minimum vote_count (e.g., 100)
- Fall back to safer recommendations for new users

### Issue: User doesn't click diverse recommendations

**Causes**:
- Presentation problem (thumbnails, descriptions)
- Timing (user wants familiar content right now)
- Mismatch with user's actual preferences

**Solutions**:
- Improve movie metadata and presentation
- Use context-aware delivery (time of day)
- Monitor and adjust based on feedback

## Future Enhancements

1. **Temporal Diversity**: Vary diversity level by time of day
   - Weekend: More exploration
   - Weeknight: More familiar

2. **Collaborative Diversity**: Learn from similar users who explore

3. **Explanation Generation**: "Because you liked X, try this hidden gem Y"

4. **Diversity Fatigue Detection**: Back off if user rejects too many diverse picks

5. **Regional Diversity**: Prioritize local/regional cinema

---

**Status**: Implemented ✅  
**Last Updated**: October 11, 2025

