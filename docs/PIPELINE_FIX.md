# Pipeline Fix: PostgreSQL Reserved Keyword Issue

## Problem

The pipeline was failing with this error:

```
psycopg2.errors.SyntaxError: syntax error at or near "cast"
LINE 13:                         cast JSONB,
```

## Root Cause

`cast` is a **reserved keyword in PostgreSQL** used for type casting operations. When used as a column name without quotes, PostgreSQL interprets it as a SQL command rather than a column name.

## Solution Applied

I've updated three files to properly quote the `cast` column name:

### 1. `movie_pipeline.py`

**Fixed CREATE TABLE statement:**
```sql
CREATE TABLE IF NOT EXISTS movies (
    ...
    "cast" JSONB,  -- Now quoted
    crew JSONB,
    ...
)
```

**Fixed UPSERT logic:**
```python
# Quote all column names to handle reserved keywords
quoted_columns = [f'"{col}"' for col in columns]
update_set = ', '.join([f'"{col}" = :{col}' for col in columns if col != 'id'])
```

### 2. `backend/migrate_database.py`

**Fixed column addition:**
```python
new_columns = {
    '"cast"': 'JSONB',  # Quoted because 'cast' is a reserved keyword
    'crew': 'JSONB',
    ...
}
```

### 3. Updated comparison logic to strip quotes when checking existing columns

## How to Run the Pipeline Again

Now you can safely run the pipeline:

```bash
cd /Users/tea/Documents/Passion-Projects/movie_recommender
source .venv/bin/activate
python3 movie_pipeline.py
```

The pipeline should now complete successfully without the syntax error.

## What the Pipeline Does

When you run `python3 movie_pipeline.py`, it will:

1. ✅ Fetch movies from TMDB (popular, top rated, upcoming, now playing, trending)
2. ✅ Enrich 50 movies with detailed data (cast with profile images, crew, keywords, language, etc.)
3. ✅ Transform and clean the data
4. ✅ Create database tables if they don't exist (with properly quoted column names)
5. ✅ Insert/update movies in the database using UPSERT logic
6. ✅ Log the pipeline run to `pipeline_runs` table

## Expected Output

You should see:

```
2025-10-04 11:35:58,075 - __main__ - INFO - 💾 Loading data to database...
2025-10-04 11:35:58,114 - __main__ - INFO - Using incremental update mode...
2025-10-04 11:35:59,XXX - __main__ - INFO - ✅ Loaded 50 movies and 19 genres to database

============================================================
✅ PIPELINE COMPLETED SUCCESSFULLY!
============================================================
```

## What Data Is Now Available

After the pipeline runs, movies will have:

- ✅ **Cast with images**: `[{"name": "Actor", "character": "Role", "profile_path": "/image.jpg"}]`
- ✅ **Language**: `"en"`, `"fr"`, `"ja"`, etc.
- ✅ **Director**: Available in crew array
- ✅ **Runtime, Budget, Revenue**: Full financial data
- ✅ **Keywords, Tagline, Trailer**: Additional metadata

## Next Steps After Pipeline Success

1. **Restart the backend API:**
   ```bash
   uvicorn backend.main:app --reload
   ```

2. **Test the MovieDetailModal:**
   - Open your frontend
   - Click on any movie
   - The modal should now display:
     - Cast members with profile images
     - Director name
     - Language
     - All stats (rating, views, budget, revenue)

## Database Schema

The `movies` table now has this structure:

```sql
CREATE TABLE movies (
    id INTEGER PRIMARY KEY,
    title VARCHAR(500),
    overview TEXT,
    release_date DATE,
    vote_average FLOAT,
    vote_count INTEGER,
    popularity FLOAT,
    poster_url VARCHAR(500),
    backdrop_url VARCHAR(500),
    genres JSONB,
    "cast" JSONB,              -- Quoted for reserved keyword
    crew JSONB,
    keywords JSONB,
    runtime INTEGER,
    budget BIGINT,
    revenue BIGINT,
    tagline TEXT,
    similar_movie_ids JSONB,
    trailer_key VARCHAR(100),
    original_language VARCHAR(10),
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

## Troubleshooting

### If you still get errors:

1. **Drop and recreate the table** (if you have no important data):
   ```sql
   DROP TABLE IF EXISTS movies CASCADE;
   ```
   Then run the pipeline again.

2. **Check PostgreSQL version** (JSONB requires PostgreSQL 9.4+):
   ```bash
   psql $DATABASE_URL -c "SELECT version();"
   ```

3. **Verify environment variables**:
   ```bash
   echo $TMDB_API_KEY
   echo $DATABASE_URL
   ```

## Common PostgreSQL Reserved Keywords

For future reference, these are reserved keywords that need quoting:

- `cast`, `user`, `order`, `group`, `table`, `select`, `where`, `from`, `join`, `grant`, etc.

Always quote column names that might be reserved keywords:
```sql
CREATE TABLE example (
    "user" VARCHAR(100),  -- Quoted
    "order" INTEGER,      -- Quoted
    name VARCHAR(100)     -- Not reserved, no quotes needed
);
```

## Success!

You're now ready to run the pipeline and populate your database with enriched movie data! 🎬✨

