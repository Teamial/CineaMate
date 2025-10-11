<!-- 4ee8c472-6593-45fe-aff4-91bbd188f263 2f656aa2-eab5-47e0-8b9c-7b1bca32a1a9 -->
# Fix Railway Deployment

## Problem Analysis

Railway is failing with `sh: 1: ./start.sh: not found` because:

1. **Root package.json** has `"start": "./start.sh"` pointing to root directory
2. **No start.sh in root** - the script exists in `backend/start.sh` and `scripts/start.sh`
3. **Railway auto-detection** is running `npm start` before/instead of the Dockerfile CMD
4. **Dockerfile is configured correctly** - it runs `/app/backend/start.sh`

## Solution Strategy

Fix the deployment by ensuring Railway uses the Dockerfile properly and providing a fallback start.sh in the root.

## Implementation Plan

### Step 1: Create Root-Level start.sh

Copy `backend/start.sh` to the project root for npm start compatibility:

**File**: `start.sh` (root level)

```bash
#!/bin/bash
# Railway deployment startup script
# This is called by npm start

set -e

echo "🚀 Starting Movie Recommender Backend..."

# Initialize database with pgvector extension
echo "🔧 Initializing database..."
python backend/init_db.py || echo "Database already initialized"

# Create database tables
echo "🔧 Creating database tables..."
python -c "from backend.database import engine, Base; Base.metadata.create_all(bind=engine)"

# Start the FastAPI app
echo "🚀 Starting FastAPI server..."
exec python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

Key changes:

- Uses `${PORT:-8000}` to respect Railway's PORT environment variable
- Handles database initialization errors gracefully
- Starts uvicorn on the correct host

### Step 2: Make start.sh Executable

Add executable permissions to the new start.sh:

```bash
chmod +x start.sh
```

### Step 3: Update Railway Configuration

**File**: `deployment/railway.json`

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "numReplicas": 1,
    "sleepApplication": false,
    "restartPolicyType": "ON_FAILURE",
    "startCommand": "./start.sh"
  }
}
```

Changes:

- Use **NIXPACKS** instead of DOCKERFILE (better for mixed Node/Python)
- Explicitly set `startCommand` to `./start.sh`
- Remove dockerfilePath (using Nixpacks instead)

### Step 4: Alternative - Use Dockerfile Approach

If NIXPACKS doesn't work, ensure Dockerfile deployment:

**Update**: `deployment/railway.json`

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE",
    "dockerfilePath": "backend/Dockerfile"
  },
  "deploy": {
    "numReplicas": 1,
    "sleepApplication": false,
    "restartPolicyType": "ON_FAILURE"
  }
}
```

**And update**: `backend/Dockerfile` CMD to use PORT variable:

```dockerfile
CMD ["/bin/bash", "-c", "python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

### Step 5: Create Railway-specific Procfile

**File**: `Procfile` (root level)

```
web: ./start.sh
```

This tells Railway explicitly how to start the web service.

### Step 6: Update package.json Start Command

**File**: `package.json`

Option A - Point to new root start.sh (already done):

```json
{
  "scripts": {
    "start": "./start.sh"
  }
}
```

Option B - Use Python directly:

```json
{
  "scripts": {
    "start": "python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"
  }
}
```

### Step 7: Verify Railway Environment Variables

Ensure these are set in Railway:

- `DATABASE_URL` - PostgreSQL connection string
- `PORT` - Auto-set by Railway (usually 8000)
- `SECRET_KEY` - Your JWT secret
- `TMDB_API_KEY` - If using TMDB

### Step 8: Test Deployment

1. Commit changes:
```bash
git add start.sh Procfile deployment/railway.json
git commit -m "Fix Railway deployment start script"
git push
```

2. Railway will auto-deploy

3. Check logs for:
```
🚀 Starting Movie Recommender Backend...
🔧 Initializing database...
🔧 Creating database tables...
🚀 Starting FastAPI server...
INFO: Started server process
INFO: Waiting for application startup.
INFO: Application startup complete.
INFO: Uvicorn running on http://0.0.0.0:8000
```


## Files to Create/Modify

### New Files:

1. **`start.sh`** (root) - Main startup script
2. **`Procfile`** (root) - Railway process definition

### Modified Files:

1. **`deployment/railway.json`** - Update builder and start command
2. **`package.json`** - Ensure start script is correct (already correct)
3. **`backend/Dockerfile`** (optional) - Use PORT env variable

## Deployment Options

### Option 1: Simple (Recommended)

- Create root `start.sh`
- Create `Procfile`
- Deploy

### Option 2: Dockerfile

- Keep Dockerfile approach
- Update to use PORT env variable
- Ensure railway.json uses DOCKERFILE builder

### Option 3: Nixpacks (Railway default)

- Create `start.sh` and `Procfile`
- Let Railway auto-detect
- Simplest for Python + Node projects

## Troubleshooting

### If deployment still fails:

1. **Check Railway logs** for actual error
2. **Verify build phase** completes successfully
3. **Check start command** in Railway dashboard
4. **Manually set start command** in Railway UI: `./start.sh`
5. **Check file permissions** - start.sh must be executable

### Common Issues:

**"Permission denied"**:

```bash
chmod +x start.sh
git add start.sh
git commit -m "Make start.sh executable"
```

**"Python module not found"**:

- Ensure requirements.railway.txt has all dependencies
- Check Railway uses correct Python version (3.11)

**"Database connection failed"**:

- Verify DATABASE_URL environment variable
- Check PostgreSQL service is linked

## Success Criteria

✅ Railway build completes successfully

✅ Start script executes without errors

✅ FastAPI server starts on correct port

✅ API is accessible at Railway URL

✅ Database connection works

✅ No crash loop restarts

## Testing Locally

Before deploying, test the start script:

```bash
# Set environment variables
export DATABASE_URL="your_local_db_url"
export PORT=8000

# Run start script
./start.sh
```

Should see:

```
🚀 Starting Movie Recommender Backend...
🔧 Initializing database...
🔧 Creating database tables...
🚀 Starting FastAPI server...
INFO: Uvicorn running on http://0.0.0.0:8000
```

---

## Implementation Order

1. Create `start.sh` in root
2. Make it executable
3. Create `Procfile`
4. Update `deployment/railway.json`
5. Commit and push
6. Monitor Railway deployment
7. Troubleshoot if needed

### To-dos

- [ ] Create diversity_recommender.py with long-tail discovery, serendipity scoring, niche genre boosting, and coverage tracking
- [ ] Build evaluator.py with offline metrics (RMSE, Precision@K, diversity, novelty) and online metrics (CTR, quality)
- [ ] Implement bandit_selector.py with Thompson Sampling for context-aware algorithm selection
- [ ] Add experiment fields (experiment_id, variant, bandit_context) to RecommendationEvent and create BanditState table
- [ ] Create training_pipeline.py for data prep, model training, evaluation, deployment, and continuous learning
- [ ] Build experiment_manager.py for A/B test configuration, variant assignment, and statistical testing
- [ ] Integrate bandit selector into recommender.py and movies.py endpoint, enable embeddings/graph by default
- [ ] Add diversity metrics, bandit state, and A/B test results endpoints to analytics.py
- [ ] Create/update scheduler.py for automated model retraining every 6 hours and bandit parameter persistence
- [ ] Run offline evaluation to establish baseline metrics for current algorithm
- [ ] Deploy first A/B test comparing baseline vs bandit-optimized recommendations
- [ ] Set up monitoring and alerts for diversity, quality, bandit balance, and training failures
- [ ] Create comprehensive documentation for diversity algorithm, bandit selector, evaluation, A/B testing, and training pipeline