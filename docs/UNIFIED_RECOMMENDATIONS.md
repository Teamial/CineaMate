# Unified Recommendation System

## 🎯 Overview

**Simplified from 3 modes to 1 unified algorithm** - Just works, no configuration needed!

## What Changed

### Before ❌
- **3 separate endpoints**: `/recommendations`, `/recommendations/context`, `/recommendations/feedback-driven`
- Different modes with different behavior
- Context-aware: Too aggressive filtering, returned no movies
- Feedback-driven: Overly complex, poor results
- Standard: Worked but required manual mode selection

### After ✅
- **1 unified endpoint**: `/recommendations`
- No modes, no configuration
- Automatically combines best features from all approaches
- Returns plenty of movies (30 by default)
- Just works!

## API Usage

### Frontend Integration

**OLD (Remove this)**:
```javascript
// ❌ Don't use these anymore
GET /recommendations/context?user_id=1
GET /recommendations/feedback-driven?user_id=1
GET /recommendations?user_id=1&use_context=true  // Complex params
```

**NEW (Use this)**:
```javascript
// ✅ Just one simple endpoint
GET /recommendations?user_id=1&limit=30

// That's it! No modes, no params needed.
```

### Full Example

```javascript
// Get recommendations
const recommendations = await fetch(
  `/movies/recommendations?user_id=${userId}&limit=30`,
  {
    headers: { 'Authorization': `Bearer ${token}` }
  }
).then(r => r.json());

// Returns: Array of Movie objects (30 by default)
```

## What the Unified Algorithm Does

The new unified recommendation system automatically:

1. ✅ **Filters horror movies** (or any disliked genres from onboarding)
2. ✅ **Balances preferences** - Your stated preferences (Mystery, Drama, Romance) get strong weight, but doesn't ignore your ratings
3. ✅ **Provides diversity** - Multiple genres, not just Animation/Family
4. ✅ **Smart mixing** - Combines SVD, item-based CF, and content-based recommendations
5. ✅ **Returns plenty of movies** - Typically 25-30 results
6. ✅ **No over-filtering** - Removed aggressive temporal/context filtering that was removing everything

## Under the Hood

The unified algorithm uses:

```python
# Hybrid approach with smart weights
60% SVD (matrix factorization) - Best for accuracy
25% Item-based CF - Good for similar movies  
15% Content-based - Good for diversity

Then applies:
- Horror/disliked genre filtering
- Thumbs up/down filtering
- Genre preference boosting (from onboarding)
- Removes already-seen movies
```

## Frontend Changes Needed

### Remove Mode Selection UI

If you have UI for selecting recommendation modes/types, remove it:

```jsx
// ❌ Remove this kind of code
<Select value={recType}>
  <option value="standard">Standard</option>
  <option value="context-aware">Context-Aware</option>
  <option value="feedback-driven">Feedback-Driven</option>
</Select>
```

### Simplified Recommendations Component

```jsx
// ✅ Just fetch and display
const Recommendations = ({ userId }) => {
  const [movies, setMovies] = useState([]);
  
  useEffect(() => {
    fetch(`/movies/recommendations?user_id=${userId}&limit=30`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(r => r.json())
      .then(setMovies);
  }, [userId]);
  
  return (
    <div>
      {movies.map(movie => <MovieCard key={movie.id} movie={movie} />)}
    </div>
  );
};
```

## Testing

Test the unified endpoint:

```bash
# 1. Start backend
uvicorn backend.main:app --reload

# 2. Test API
curl "http://localhost:8000/movies/recommendations?user_id=1&limit=30" \
  -H "Authorization: Bearer $TOKEN"

# Should return 25-30 movies with no horror (if user dislikes it)
```

## Migration Checklist

- [ ] Update frontend to use single `/recommendations` endpoint
- [ ] Remove mode selection UI components
- [ ] Remove `use_context`, `use_embeddings`, `use_graph` parameters
- [ ] Remove `/recommendations/context` endpoint calls
- [ ] Remove `/recommendations/feedback-driven` endpoint calls
- [ ] Test that recommendations load properly
- [ ] Verify horror movies are filtered (if disliked)
- [ ] Verify getting 25-30 movies consistently

## Benefits

### For Users
- ✅ No confusing modes to choose from
- ✅ Just get great recommendations automatically
- ✅ More movies shown (25-30 vs 10-15)
- ✅ Better diversity across genres
- ✅ Horror/disliked genres always filtered

### For Developers
- ✅ One endpoint to maintain instead of three
- ✅ Simpler API contract
- ✅ Easier to test and debug
- ✅ No complex parameter combinations
- ✅ Cleaner frontend code

### For the System
- ✅ Less complexity
- ✅ Fewer edge cases
- ✅ Consistent behavior
- ✅ Easier to improve in the future

## Backwards Compatibility

The old endpoints still exist in the code but are commented out. If you need them temporarily:

1. They're in `backend/routes/movies.py` lines 115-179
2. Uncomment if needed for gradual migration
3. Delete entirely once frontend is updated

## Questions?

The unified algorithm lives in:
- **API**: `backend/routes/movies.py` (line 64-113)
- **Logic**: `backend/ml/recommender.py` - `get_hybrid_recommendations()`
- **Filters**: Horror filtering, thumbs up/down, genre preferences

---

**Version**: 3.0.0 - Unified Recommendations  
**Date**: October 5, 2025  
**Breaking Change**: Yes (but improved!)  
**Migration Time**: ~15 minutes to update frontend
