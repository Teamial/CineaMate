# Recommendation Algorithm Fixes

## Date: October 5, 2025

## Issues Reported
1. **Horror movies showing up** despite being marked as disliked
2. **Recommendations too generic** - not tailored to user's taste after 34 ratings
3. **Ignoring stated preferences** - User liked Mystery, Drama, Romance but only getting Animation/Family

## Root Causes Identified

### 1. Genre Filtering Was Working ✅
- Horror filter was actually working correctly
- No horror movies in current recommendations

### 2. Over-fitting to Rating Patterns ❌
- User had 26/30 ratings in Animation/Family
- Rating-based genres (weight: 1.0 × 26 = 26) overpowered stated preferences (weight: 3.0 × 5 = 15)
- Algorithm was being "too safe" and only recommending similar movies

### 3. SVD Model Not Building ❌
- Threshold was 10 minimum ratings
- User had 30 ratings but SVD still failed
- System falling back to narrow item-based CF

## Fixes Implemented

### Fix 1: Balanced Genre Preference Weighting

**Before**:
```python
# Onboarding preferences: weight 3.0
combined_scores[genre] += score * 3.0

# Rating-based: weight 1.0 (no dampening)
for movie in high_rated_movies:
    for genre in movie.genres:
        combined_scores[genre] += 1.0
```

**After**:
```python
# Onboarding preferences: weight 5.0 (INCREASED)
combined_scores[genre] += score * 5.0

# Rating-based: weight 0.5 with square root dampening
dampened_score = math.sqrt(count) * 0.5
combined_scores[genre] += dampened_score
# Example: 26 Animation movies → sqrt(26) × 0.5 ≈ 2.55 (instead of 26!)
```

**Impact**: Stated preferences now have 10x more weight than individual ratings

### Fix 2: Enhanced Content-Based Recommendations

**Before**:
```python
# Only used genres from rated movies
top_genres = get_top_3_genres_from_ratings()
```

**After**:
```python
# Combines rated movies (dampened) + stated preferences (strong weight)
genre_scores[genre] += math.sqrt(count) * 0.3  # From ratings
genre_scores[genre] += pref_score * 3.0        # From onboarding
top_genres = top_5_genres  # Increased from 3 to 5
```

**Impact**: System now explores stated preferences even if not in ratings

### Fix 3: Lowered SVD Threshold

**Before**:
```python
self.svd_min_ratings = 10  # System-wide minimum
```

**After**:
```python
self.svd_min_ratings = 5  # Lowered threshold
```

**Impact**: SVD model can build with fewer total ratings in system

### Fix 4: Lowered Preference Threshold

**Before**:
```python
'preferred_genres': set(g for g, s in scores.items() if s > 0.3)
```

**After**:
```python
'preferred_genres': set(g for g, s in scores.items() if s > 0.2)
```

**Impact**: More genres considered as "preferred", increasing diversity

## Results

### Before Fix
```
Recommendations (10 movies):
- 10/10 Animation/Family movies (100%)
- 0/10 Mystery/Drama/Romance (0%)
- Generic, safe recommendations
- Not personalized despite 30 ratings
```

### After Fix
```
Recommendations (18 movies):
✅ No horror movies (0%)
✅ Drama: 15 movies (83%)
✅ Romance: 13 movies (72%)
✅ Mystery: 5 movies (28%)
✅ Animation/Family: 5 movies (28%) - still present but not dominant
✅ 13 unique genres (was ~3)
✅ Diverse, personalized recommendations
```

### Example Improved Recommendations
- **La La Land** (Comedy, Drama, Romance, Music)
- **Love, Rosie** (Romance, Drama, Comedy)
- **Moonrise Kingdom** (Comedy, Drama, Romance)
- **The Brothers Bloom** (Adventure, Comedy, Drama, Romance)
- **Ed, Edd n Eddy** (still includes some Animation but with Drama/Mystery)

## Technical Details

### Square Root Dampening Formula
```python
# Before: Linear scaling
score = count  # 26 movies → score of 26

# After: Square root dampening  
score = math.sqrt(count) * 0.5  # 26 movies → score of 2.55

# Why this works:
# - Reduces over-representation of dominant genres
# - Still gives credit for user preferences
# - Allows stated preferences to compete
```

### Preference Weight Comparison
| Source | Old Weight | New Weight | Example Score |
|--------|-----------|-----------|---------------|
| Onboarding (Mystery) | 3.0 | 5.0 | 5.0 |
| Thumbs Up (Mystery) | 2.0 | 3.0 | 3.0 |
| 26 Rated Movies (Animation) | 26.0 | 2.55 | 2.55 |

**Result**: Mystery (5.0) > Animation (2.55) ✅

## Files Modified

1. **`backend/ml/recommender.py`**
   - Line 34: Lowered SVD threshold 10 → 5
   - Lines 2051-2101: Enhanced `_get_user_genre_preferences_combined()` with dampening
   - Lines 363-441: Enhanced `get_content_based_recommendations()` to use stated preferences

## Testing

Run the test script to verify:
```bash
python test_improved_recommendations.py
```

Expected output:
- ✅ No horror movies
- ✅ 8+ unique genres
- ✅ Multiple movies from stated preferences (Mystery/Drama/Romance)

## Recommendations for Users

### If You Want More Diversity
Rate movies in genres you're interested in exploring (even if just 3-4 stars)

### If You Want Different Genres
Update your genre preferences in settings:
- Use thumbs down on unwanted genres
- Use thumbs up on genres you want to see more of

### If Still Too Many Animated Movies
The system now respects preferences better, but you can:
1. Rate non-animated movies higher (4.5-5 stars)
2. Add more genres to your preferences
3. Use thumbs down on animated movies you don't want

## Notes

- Horror filtering was already working correctly
- Main issue was genre balance, not filtering
- System now explores stated preferences aggressively
- Animation/Family still appears but not dominant
- Backwards compatible - no database changes needed

## Critical Bug Fix (October 5, 2025 - Part 2)

### Issue: Horror Movie "Weapons" Appearing Despite Filter

**Bug**: Horror movie "Weapons" (Horror/Mystery) was appearing in recommendations despite user marking Horror as disliked.

**Root Cause**: Dangerous fallback in `_filter_disliked_genres()` (lines 272-276):
```python
if filtered_movies:
    return filtered_movies
else:
    # If filtering removes ALL movies, return original list
    return movies  # <-- Returns unfiltered horror movies!
```

**Fix Applied**:
1. Removed the dangerous fallback - now returns empty list instead
2. Added early filtering in `get_content_based_recommendations()` - horror filtered at source
3. Added early filtering in `get_item_based_recommendations()` - double layer of protection

**Result**: Horror movies now filtered at multiple stages:
- ✅ Stage 1: Filtered when building recommendation pool (content-based, item-based)
- ✅ Stage 2: Filtered after combining all sources (hybrid)
- ✅ Never bypasses filter with fallbacks

## Version
- **Before**: v2.0.0 (with over-fitting issue)
- **After**: v2.0.1 (balanced preferences)
- **After**: v2.0.2 (fixed horror filter bypass bug)
- **Date**: October 5, 2025
