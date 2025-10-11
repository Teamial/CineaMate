# Pgvector Quick Start Guide

## 🚀 Quick Commands

### Check Embedding Coverage
```bash
docker exec movies-postgres psql -U postgres -d movies_db -c "
SELECT 
    COUNT(*) as total_movies,
    COUNT(embedding) as with_embeddings,
    ROUND(100.0 * COUNT(embedding) / COUNT(*), 1) as coverage_percent
FROM movies;"
```

### Generate Embeddings
```bash
# Activate virtual environment
source .venv/bin/activate

# Generate embeddings for all movies without them
python backend/generate_embeddings.py
```

### Test Similarity Search
```bash
python -c "
from backend.ml.pgvector_recommender import PgvectorRecommender
from backend.database import SessionLocal

db = SessionLocal()
rec = PgvectorRecommender(db)

# Get stats
stats = rec.get_stats()
print(f'Coverage: {stats[\"coverage_percentage\"]:.1f}%')

# Find similar movies
similar = rec.get_similar_movies(movie_id=941109, n_similar=5)
for movie, sim in similar:
    print(f'{sim:.3f} - {movie.title}')
db.close()
"
```

## 📝 Workflow

### Initial Setup (One-Time)
```bash
# 1. Start Docker containers
docker-compose up -d

# 2. Run migration
python backend/migrate_add_pgvector.py

# 3. Load movies
python movie_pipeline.py

# 4. Generate embeddings
python backend/generate_embeddings.py
```

### Adding New Movies
```bash
# 1. Run pipeline to fetch new movies
python movie_pipeline.py

# 2. Generate embeddings for new movies
python backend/generate_embeddings.py
```

**Or wait for automatic daily refresh at 4 AM!**

## 🔍 Useful Queries

### Check Index Status
```bash
docker exec movies-postgres psql -U postgres -d movies_db -c "
SELECT schemaname, tablename, indexname 
FROM pg_indexes 
WHERE tablename = 'movies' AND indexname LIKE '%embedding%';"
```

### Sample Movie Embeddings
```bash
docker exec movies-postgres psql -U postgres -d movies_db -c "
SELECT id, title, 
       CASE WHEN embedding IS NOT NULL THEN '✓' ELSE '✗' END as has_embedding
FROM movies 
LIMIT 10;"
```

### Find Movies Without Embeddings
```bash
docker exec movies-postgres psql -U postgres -d movies_db -c "
SELECT COUNT(*), 
       STRING_AGG(title, ', ' LIMIT 5) as sample_titles
FROM movies 
WHERE embedding IS NULL;"
```

## 🔧 Configuration

### Model Settings
- **Model**: `sentence-transformers/all-MiniLM-L6-v2`
- **Dimensions**: 384
- **Device**: CPU (automatically uses GPU if available)
- **Batch Size**: 100 (adjustable in generate_embeddings.py)

### Index Settings
- **Type**: IVFFlat
- **Distance**: Cosine (`vector_cosine_ops`)
- **Lists**: 100 (adjust for dataset size: √n recommended)

### Scheduler
- **Frequency**: Daily at 4:00 AM
- **Job**: Generates embeddings for new movies
- **Config**: `backend/scheduler.py`

## 🎯 Integration Points

### Main Recommender
File: `backend/ml/recommender.py`

```python
def get_embedding_recommendations(self, user_id, n_recommendations=10):
    # Try pgvector first (fastest)
    try:
        from backend.ml.pgvector_recommender import PgvectorRecommender
        recommender = PgvectorRecommender(self.db)
        return recommender.get_recommendations(user_id, n_recommendations)
    except Exception as e:
        # Fallback to file-based embeddings
        pass
```

### API Endpoint
File: `backend/routes/movies.py`

The `/recommendations` endpoint automatically uses pgvector when available.

## 📊 Performance Tips

1. **Batch Generation**: Process embeddings in batches (current: 100)
2. **Index Tuning**: Adjust `lists` parameter as dataset grows
3. **Query Optimization**: Use diversity_boost for better recommendations
4. **Monitoring**: Check coverage regularly with stats query

## 🐛 Troubleshooting

### Embeddings Not Generating
```bash
# Check if model is available
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Check database connection
python -c "from backend.database import engine; engine.connect()"
```

### Slow Queries
```bash
# Check if index exists
docker exec movies-postgres psql -U postgres -d movies_db -c "\d movies"

# Rebuild index
docker exec movies-postgres psql -U postgres -d movies_db -c "
DROP INDEX IF EXISTS movies_embedding_idx;
CREATE INDEX movies_embedding_idx ON movies 
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);"
```

### Port Conflicts
Check `.env` file:
```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/movies_db
```

## 📚 Files Reference

- `docker-compose.yml` - Pgvector Docker image
- `backend/models.py` - Embedding column definition
- `backend/migrate_add_pgvector.py` - Migration script
- `backend/generate_embeddings.py` - Embedding generation
- `backend/ml/pgvector_recommender.py` - Recommender implementation
- `backend/scheduler.py` - Automatic refresh job
- `PGVECTOR_INTEGRATION_COMPLETE.md` - Full documentation

## ✅ Health Check
```bash
# All-in-one health check
python -c "
from backend.ml.pgvector_recommender import PgvectorRecommender
from backend.database import SessionLocal

db = SessionLocal()
rec = PgvectorRecommender(db)
stats = rec.get_stats()

print('Pgvector Health Check:')
print(f'  Database: {'✓' if stats['total_movies'] > 0 else '✗'}')
print(f'  Embeddings: {'✓' if stats['coverage_percentage'] > 0 else '✗'}')
print(f'  Coverage: {stats['coverage_percentage']:.1f}%')
print(f'  Status: {'✓ HEALTHY' if stats['coverage_percentage'] == 100 else '⚠ PARTIAL'}'
)
db.close()
"
```

---

**Quick Access**: All pgvector functionality is encapsulated in `PgvectorRecommender` class and runs automatically via the scheduler.