# 🚀 Setup Instructions - Embedding-Based Recommendations

## Next Steps Implementation Guide

This document walks through completing the 3 next steps:
1. ✅ Build full index (2000 movies)
2. ✅ Enable in API (`use_embeddings=true`)
3. ✅ Monitor performance

---

## Prerequisites

### Option 1: Virtual Environment (Recommended)

```bash
cd /Users/tea/Documents/Passion-Projects/movie_recommender

# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Option 2: User Installation

```bash
# Install to user directory
pip3 install --user torch torchvision sentence-transformers Pillow

# Also install other requirements
pip3 install --user -r requirements.txt
```

### Option 3: Conda Environment

```bash
# Create conda environment
conda create -n movie_rec python=3.10

# Activate it
conda activate movie_rec

# Install dependencies
pip install -r requirements.txt
```

---

## Step 1: Build Full Embedding Index (2000 Movies)

Once dependencies are installed, run the setup script:

```bash
cd /Users/tea/Documents/Passion-Projects/movie_recommender
python3 setup_embeddings.py
```

**What this does:**
- ✅ Checks all dependencies
- ✅ Downloads BERT model (~80 MB, one-time)
- ✅ Downloads ResNet-50 (~100 MB, one-time)
- ✅ Builds embedding index for 2000 movies (3-5 minutes)
- ✅ Caches embeddings to disk for fast reuse
- ✅ Tests recommendations
- ✅ Provides performance metrics

**Expected output:**
```
✅ Index built successfully in 180.5 seconds!

📊 Index Metrics:
   Total movies in database: 1247
   Movies in embedding index: 1247
   Coverage: 100.0%
   Movies with posters: 1189
   Poster coverage: 95.3%
   Device: cpu
```

### Manual Index Building

If you prefer to build manually:

```python
python3 << EOF
from backend.ml.embedding_recommender import EmbeddingRecommender
from backend.database import SessionLocal

print("Building embedding index...")
db = SessionLocal()
recommender = EmbeddingRecommender(db)

# Build index for 2000 movies (or all available)
recommender._build_movie_embeddings_index(max_movies=2000)

# Check metrics
metrics = recommender.get_embedding_quality_metrics()
print(f"✅ Built index with {metrics['movies_in_index']} movies")
print(f"   Coverage: {metrics['coverage']}")
print(f"   Device: {metrics['device']}")

db.close()
EOF
```

---

## Step 2: Enable in API

### ✅ Already Enabled!

The API parameter is already configured. You can use it immediately:

### REST API Usage

```bash
# Get embedding-based recommendations
curl "http://localhost:8000/movies/recommendations?user_id=1&limit=10&use_embeddings=true" \
  -H "Authorization: Bearer $TOKEN"
```

**Parameters:**
- `use_embeddings=true` - Enable deep learning recommendations
- `use_context=true` - Also apply temporal/diversity filtering
- `limit=10` - Number of recommendations

### Python API Usage

```python
from backend.ml.recommender import MovieRecommender
from backend.database import SessionLocal

db = SessionLocal()
recommender = MovieRecommender(db)

# Pure embedding recommendations
recs = recommender.get_embedding_recommendations(
    user_id=1,
    n_recommendations=10
)

# Hybrid with embeddings (recommended)
recs = recommender.get_hybrid_recommendations(
    user_id=1,
    n_recommendations=10,
    use_embeddings=True,  # Enable embeddings
    use_context=True       # Enable context-aware features
)
```

### Frontend Integration

```javascript
// In your React components
const fetchRecommendations = async (userId) => {
  const response = await fetch(
    `/movies/recommendations?user_id=${userId}&limit=10&use_embeddings=true`,
    {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    }
  );
  
  const recommendations = await response.json();
  return recommendations;
};
```

---

## Step 3: Monitor Performance

### Real-Time Performance Monitoring

Create this monitoring script:

```python
# File: monitor_embeddings.py
import time
from backend.ml.embedding_recommender import EmbeddingRecommender
from backend.ml.recommender import MovieRecommender
from backend.database import SessionLocal

def monitor_performance():
    """Monitor embedding recommendation performance"""
    db = SessionLocal()
    
    print("📊 Embedding System Performance Monitor")
    print("=" * 60)
    
    # 1. Check index status
    emb_rec = EmbeddingRecommender(db)
    metrics = emb_rec.get_embedding_quality_metrics()
    
    print("\n1️⃣  Index Status:")
    print(f"   Movies in index: {metrics['movies_in_index']}")
    print(f"   Coverage: {metrics['coverage']}")
    print(f"   Device: {metrics['device']}")
    print(f"   Cache age: {metrics['cache_age']}")
    
    # 2. Test recommendation speed
    recommender = MovieRecommender(db)
    
    print("\n2️⃣  Performance Test:")
    
    # Test 1: Pure embeddings
    start = time.time()
    recs = recommender.get_embedding_recommendations(user_id=1, n_recommendations=10)
    elapsed_emb = (time.time() - start) * 1000
    
    print(f"   Embedding recommendations: {elapsed_emb:.0f}ms")
    
    # Test 2: Hybrid with embeddings
    start = time.time()
    recs = recommender.get_hybrid_recommendations(
        user_id=1, 
        n_recommendations=10,
        use_embeddings=True
    )
    elapsed_hybrid = (time.time() - start) * 1000
    
    print(f"   Hybrid recommendations: {elapsed_hybrid:.0f}ms")
    
    # 3. Provide recommendations
    print("\n3️⃣  Performance Analysis:")
    
    if elapsed_emb < 100:
        print("   ✅ Excellent: < 100ms")
    elif elapsed_emb < 200:
        print("   ⚠️  Good but could improve: < 200ms")
    else:
        print("   ❌ Slow: > 200ms - Consider GPU or reduce index size")
    
    if metrics['device'] == 'cpu':
        print("\n   💡 Tip: Use GPU for 5-10x faster embeddings")
    
    print("\n4️⃣  Recommendations:")
    if elapsed_emb > 200:
        print("   • Reduce index size: max_movies=1000")
        print("   • Use GPU: Install CUDA-enabled PyTorch")
        print("   • Pre-build index on startup")
    else:
        print("   • Performance is good!")
        print("   • Monitor in production")
        print("   • Track user engagement metrics")
    
    db.close()

if __name__ == "__main__":
    monitor_performance()
```

### Run Monitoring

```bash
python3 monitor_embeddings.py
```

### Continuous Monitoring

For production, track these metrics:

#### 1. Latency Metrics
```python
# Log recommendation times
import logging
import time

start = time.time()
recommendations = get_recommendations(user_id, use_embeddings=True)
latency_ms = (time.time() - start) * 1000

logging.info(f"Recommendation latency: {latency_ms:.0f}ms")

# Alert if > 200ms
if latency_ms > 200:
    logging.warning(f"High latency: {latency_ms:.0f}ms")
```

#### 2. Cache Performance
```python
# Monitor cache hit rate
metrics = recommender.get_embedding_quality_metrics()
logging.info(f"Index coverage: {metrics['coverage']}")
logging.info(f"Cache age: {metrics['cache_age']}")

# Rebuild if cache is stale (> 6 hours)
if 'hours' in metrics['cache_age']:
    hours = int(metrics['cache_age'].split()[0])
    if hours > 6:
        logging.info("Cache stale, rebuilding...")
        recommender._build_movie_embeddings_index()
```

#### 3. User Engagement
```python
# Track click-through rate
from backend.models import RecommendationEvent

# When showing recommendations
for i, movie in enumerate(recommendations):
    recommender.track_recommendation(
        user_id=user_id,
        movie_id=movie.id,
        algorithm='embeddings',
        position=i+1
    )

# When user clicks
recommender.track_recommendation_click(user_id, movie_id)

# Analyze performance
performance = recommender.get_algorithm_performance(days=7)
ctr = performance['embeddings']['ctr']
logging.info(f"Embedding CTR: {ctr:.1f}%")
```

#### 4. GPU Monitoring (if using GPU)
```python
import torch

if torch.cuda.is_available():
    # Monitor GPU utilization
    memory_allocated = torch.cuda.memory_allocated() / 1e9
    memory_reserved = torch.cuda.memory_reserved() / 1e9
    
    logging.info(f"GPU Memory: {memory_allocated:.2f}GB allocated")
    logging.info(f"GPU Memory: {memory_reserved:.2f}GB reserved")
    
    # Alert if memory usage high
    if memory_allocated > 8.0:  # 8GB threshold
        logging.warning("High GPU memory usage")
```

---

## Production Setup

### Pre-build Index on Startup

Add to `backend/main.py`:

```python
@app.on_event("startup")
async def build_embeddings():
    """Build embedding index on startup"""
    try:
        from backend.ml.embedding_recommender import EmbeddingRecommender, DEEP_LEARNING_AVAILABLE
        from backend.database import SessionLocal
        
        if DEEP_LEARNING_AVAILABLE:
            logger.info("Building embedding index...")
            db = SessionLocal()
            recommender = EmbeddingRecommender(db)
            recommender._build_movie_embeddings_index(max_movies=2000)
            
            metrics = recommender.get_embedding_quality_metrics()
            logger.info(f"✅ Built index with {metrics['movies_in_index']} movies")
            logger.info(f"   Device: {metrics['device']}")
            
            db.close()
    except Exception as e:
        logger.warning(f"Could not build embedding index: {e}")
```

### Scheduled Rebuilds

Add to `backend/scheduler.py`:

```python
def rebuild_embeddings():
    """Rebuild embedding index"""
    from backend.ml.embedding_recommender import EmbeddingRecommender
    from backend.database import SessionLocal
    
    logger.info("Rebuilding embedding index...")
    db = SessionLocal()
    recommender = EmbeddingRecommender(db)
    recommender._build_movie_embeddings_index(max_movies=2000)
    db.close()
    logger.info("✅ Embedding index rebuilt")

# Add job (every 6 hours)
scheduler.add_job(
    func=rebuild_embeddings,
    trigger=IntervalTrigger(hours=6),
    id='rebuild_embeddings',
    name='Rebuild Embedding Index',
    replace_existing=True
)
```

### GPU Configuration

For GPU acceleration (5-10x faster):

```bash
# Install CUDA-enabled PyTorch
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# Verify GPU
python3 -c "import torch; print(f'GPU: {torch.cuda.is_available()}')"
```

---

## Validation Checklist

- [ ] Dependencies installed
- [ ] Setup script runs successfully
- [ ] Index built with > 1000 movies
- [ ] Coverage > 80%
- [ ] Recommendations generate < 200ms
- [ ] API parameter `use_embeddings=true` works
- [ ] Monitoring script runs
- [ ] Performance acceptable for production
- [ ] GPU detected (optional)
- [ ] Documentation reviewed

---

## Troubleshooting

### Issue: Dependencies won't install

**Solution**: Use virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Issue: Index build is slow

**Expected**: 3-5 minutes for first build (downloads models)
**Subsequent**: Uses cached embeddings (< 30 seconds)

**Speed up**:
- Use GPU (5-10x faster)
- Reduce max_movies to 1000
- Run during off-peak hours

### Issue: High memory usage

**Solution**:
- Reduce index size: `max_movies=1000`
- Use GPU (offloads from RAM to VRAM)
- Close other applications

### Issue: Recommendations slow

**Check**:
1. Is index built? `metrics['movies_in_index'] > 0`
2. Using CPU or GPU? `metrics['device']`
3. Cache warm? First request builds index

**Solutions**:
- Pre-build on startup
- Use GPU
- Reduce index size

---

## Next Steps After Setup

1. **Test Thoroughly**
   ```bash
   python3 setup_embeddings.py
   python3 backend/examples/embedding_demo.py
   ```

2. **A/B Test**
   - Compare embeddings vs baseline
   - Measure CTR, engagement, satisfaction
   - Gradually roll out

3. **Monitor**
   - Track latency, cache hit rate
   - Monitor user engagement
   - Alert on performance degradation

4. **Optimize**
   - Use GPU for production
   - Tune index size
   - Implement scheduled rebuilds

---

## Documentation

- **Quick Setup**: `backend/EMBEDDING_SETUP.md`
- **Full Guide**: `backend/EMBEDDING_RECOMMENDATIONS.md`
- **Summary**: `backend/EMBEDDING_SUMMARY.md`
- **Overview**: `EMBEDDING_README.md`
- **Demo**: `backend/examples/embedding_demo.py`

---

**Status**: Ready for implementation!  
**Setup Time**: 5-10 minutes (first time)  
**Production Ready**: Yes (optional feature)  
**GPU Recommended**: Yes (5-10x faster)

🚀 You're all set! Run `python3 setup_embeddings.py` to begin!

