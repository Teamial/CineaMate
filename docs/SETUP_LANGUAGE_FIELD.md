# Setup Instructions: Adding Language Field

## What Was Updated

I've updated the backend to support language data and improved cast member information for the MovieDetailModal. Here's what changed:

### Backend Changes

1. **Models (`backend/models.py`)**
   - Added `original_language` field (VARCHAR(10)) to store ISO 639-1 language codes

2. **Schemas (`backend/schemas.py`)**
   - Added `original_language` to Movie schema

3. **Pipeline (`movie_pipeline.py`)**
   - Updated to fetch `original_language` from TMDB API
   - Enhanced cast data to include `profile_path` for actor images
   - Added `original_language` to database CREATE TABLE statement

4. **Migration Script (`backend/migrate_add_language.py`)**
   - Created migration script to add column to existing databases

5. **Documentation (`backend/MOVIE_DATA_FIELDS.md`)**
   - Complete reference for all available movie fields
   - Examples of how to use the data in frontend

## Important Fix Applied

✅ **Fixed PostgreSQL Reserved Keyword Issue**: The column name `cast` is now properly quoted as `"cast"` because it's a reserved keyword in PostgreSQL.

## How to Apply Changes

### Step 1: Activate Virtual Environment

```bash
cd /Users/tea/Documents/Passion-Projects/movie_recommender

# Activate your Python virtual environment
source .venv/bin/activate  # or whatever your venv is named
```

### Step 2: Run Database Migration

```bash
# Add the original_language column
python3 backend/migrate_add_language.py
```

This will:
- ✅ Check if the column exists
- ✅ Add the column if missing
- ✅ Leave existing data intact

### Step 3: Populate Language Data

Run the pipeline to fetch language data for existing movies:

```bash
# Option A: Full enrichment (recommended)
python3 -c "from movie_pipeline import MovieETLPipeline; import os; pipeline = MovieETLPipeline(os.getenv('TMDB_API_KEY'), os.getenv('DATABASE_URL')); pipeline.run_full_enrichment()"

# Option B: Quick update
python3 -c "from movie_pipeline import MovieETLPipeline; import os; pipeline = MovieETLPipeline(os.getenv('TMDB_API_KEY'), os.getenv('DATABASE_URL')); pipeline.run_quick_update()"
```

### Step 4: Restart Backend API

```bash
# Kill any running backend process, then:
uvicorn backend.main:app --reload
```

### Step 5: Test the Frontend

The MovieDetailModal should now display:

1. ✅ **Cast with Images** - Profile photos for actors
2. ✅ **Language** - Full language name (e.g., "English")
3. ✅ **Director** - Extracted from crew data
4. ✅ **Popularity** - Displayed as views
5. ✅ **All Stats** - Rating, votes, budget, revenue

## Data Structure

### Cast Members (with images)

```json
{
  "name": "Leonardo DiCaprio",
  "character": "Dom Cobb",
  "profile_path": "/wo2hJpn04vbtmh0B9utCFdsQhxM.jpg"
}
```

Frontend usage:
```javascript
const imageUrl = actor.profile_path 
  ? `https://image.tmdb.org/t/p/w200${actor.profile_path}`
  : null;
```

### Language Codes

The `original_language` field contains ISO 639-1 codes:
- `"en"` → English
- `"fr"` → French
- `"es"` → Spanish
- `"ja"` → Japanese
- etc.

You can convert to full names using a helper function or library like `iso-639-1`.

### Director

Extract from crew array:
```javascript
const director = movie.crew
  ? (typeof movie.crew === 'string' ? JSON.parse(movie.crew) : movie.crew)
      .find(person => person.job === 'Director')?.name
  : 'Unknown';
```

### Views

Use `vote_count` (actual user ratings) or calculate from `popularity`:
```javascript
const views = movie.vote_count 
  ? movie.vote_count.toLocaleString() 
  : movie.popularity 
    ? `${(movie.popularity * 10).toFixed(1)}K`
    : 'N/A';
```

## Frontend Helper (Optional)

Create `/Users/tea/Documents/Passion-Projects/movie_recommender/frontend/src/utils/movieHelpers.js`:

```javascript
// Language code to name mapping
const LANGUAGE_NAMES = {
  'en': 'English',
  'fr': 'French',
  'es': 'Spanish',
  'de': 'German',
  'ja': 'Japanese',
  'ko': 'Korean',
  'zh': 'Chinese',
  'it': 'Italian',
  'pt': 'Portuguese',
  'ru': 'Russian',
  'hi': 'Hindi',
  'ar': 'Arabic',
  // Add more as needed
};

export const getLanguageName = (code) => {
  if (!code) return 'Not specified';
  return LANGUAGE_NAMES[code] || code.toUpperCase();
};

export const getCastImageUrl = (profilePath) => {
  if (!profilePath) return null;
  return `https://image.tmdb.org/t/p/w200${profilePath}`;
};

export const getDirector = (crew) => {
  if (!crew) return 'Unknown';
  const crewArray = typeof crew === 'string' ? JSON.parse(crew) : crew;
  return crewArray.find(person => person.job === 'Director')?.name || 'Unknown';
};

export const formatViews = (voteCount, popularity) => {
  if (voteCount) return voteCount.toLocaleString();
  if (popularity) return `${(popularity * 10).toFixed(1)}K`;
  return 'N/A';
};
```

Then use in MovieDetailModal:
```javascript
import { getLanguageName, getCastImageUrl, getDirector, formatViews } from '@/utils/movieHelpers';

// In your component
const languageName = getLanguageName(movie.original_language);
const director = getDirector(movie.crew);
const views = formatViews(movie.vote_count, movie.popularity);
```

## Verification

After setup, verify the data is available:

```bash
# Check a movie in database
psql $DATABASE_URL -c "SELECT id, title, original_language, cast IS NOT NULL as has_cast FROM movies LIMIT 5;"
```

Expected output should show language codes and TRUE for has_cast.

## Troubleshooting

### Column Already Exists Error

If you get "column already exists", that's fine - it means the column was already added. You can skip the migration.

### Missing Language Data

If movies don't have language data after migration:
1. The column was added but not populated
2. Run the pipeline to fetch the data
3. Or wait for the next scheduled pipeline run

### Cast Images Not Showing

1. Check that `profile_path` exists in cast data
2. Verify image URL format: `https://image.tmdb.org/t/p/w200{profile_path}`
3. Some actors may not have profile images (will be null)

## Next Steps

1. ✅ Run migration (Step 2 above)
2. ✅ Populate data (Step 3 above)
3. ✅ Restart backend (Step 4 above)
4. ✅ Test frontend display
5. ✅ (Optional) Add language name helper function

## Reference

See `backend/MOVIE_DATA_FIELDS.md` for complete field documentation and usage examples.

