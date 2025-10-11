# Railway Deployment - Fixed ✅

**Date**: October 11, 2025  
**Status**: Ready to deploy

## Problem Solved

Railway was failing with `sh: 1: ./start.sh: not found` because npm was looking for start.sh in the root directory, but it only existed in `backend/`.

## What Was Fixed

### 1. Created Root-Level `start.sh` ✅
- Location: `/start.sh` (project root)
- Handles Railway's PORT environment variable
- Initializes database gracefully
- Starts FastAPI server on correct host/port

### 2. Created `Procfile` ✅
- Tells Railway explicitly how to start the web service
- Simple one-liner: `web: ./start.sh`

### 3. Updated Railway Configuration ✅
- Changed from DOCKERFILE to NIXPACKS builder
- Added explicit `startCommand: ./start.sh`
- Better for mixed Python/Node projects

### 4. Made Script Executable ✅
- Ran `chmod +x start.sh`
- Railway can now execute the script

## Files Created/Modified

```
New Files:
✅ start.sh - Railway startup script
✅ Procfile - Process definition

Modified Files:
✅ deployment/railway.json - Updated builder to NIXPACKS
```

## Next Steps - Deploy to Railway

### Option 1: Quick Deploy (Recommended)

```bash
# Add and commit the changes
git add start.sh Procfile deployment/railway.json
git commit -m "Fix Railway deployment - add root start.sh and Procfile"
git push
```

Railway will automatically detect the changes and redeploy.

### Option 2: Test Locally First

```bash
# Set environment variables
export DATABASE_URL="postgresql://user:pass@localhost:5432/movies"
export PORT=8000

# Test the start script
./start.sh
```

You should see:
```
🚀 Starting Movie Recommender Backend...
🔧 Initializing database...
🔧 Creating database tables...
🚀 Starting FastAPI server...
INFO: Uvicorn running on http://0.0.0.0:8000
```

If it works locally, commit and push!

## What to Expect

### Build Phase
```
✓ Detecting app...
✓ Installing dependencies...
✓ Build complete
```

### Deploy Phase
```
🚀 Starting Movie Recommender Backend...
🔧 Initializing database...
Database already initialized
🔧 Creating database tables...
🚀 Starting FastAPI server...
INFO: Started server process [1]
INFO: Waiting for application startup.
INFO: Application startup complete.
INFO: Uvicorn running on http://0.0.0.0:8000
```

### Success Indicators
- ✅ No crash loops
- ✅ Health check passes
- ✅ API responds at Railway URL
- ✅ Database connection works

## Troubleshooting

### If Build Fails
1. Check Railway build logs for specific error
2. Verify all dependencies in `deployment/requirements.railway.txt`
3. Check Python version is 3.11

### If Start Fails
1. Check deploy logs in Railway dashboard
2. Verify `DATABASE_URL` environment variable is set
3. Ensure PostgreSQL service is linked
4. Check start.sh has correct permissions (should be executable)

### If Still Having Issues

Try the Dockerfile approach instead:

```bash
# Revert railway.json to use Dockerfile
git restore deployment/railway.json

# Then manually update to:
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

# Commit and push
git add deployment/railway.json
git commit -m "Use Dockerfile approach for Railway"
git push
```

## Environment Variables Required

Make sure these are set in Railway:

- ✅ `DATABASE_URL` - PostgreSQL connection (auto-set if using Railway PostgreSQL)
- ✅ `PORT` - Auto-set by Railway
- ✅ `SECRET_KEY` - Your JWT secret key
- ✅ `TMDB_API_KEY` - (Optional) For movie data

## Commit & Deploy Commands

```bash
# Stage the changes
git add start.sh Procfile deployment/railway.json

# Commit
git commit -m "Fix Railway deployment - add root start.sh and Procfile"

# Push to trigger deployment
git push

# Watch Railway logs
# Go to Railway dashboard → Your service → Deployments → View logs
```

## Success! 🎉

Once deployed, your API will be available at your Railway URL:
- API: `https://your-app.railway.app`
- Docs: `https://your-app.railway.app/docs`
- Health: `https://your-app.railway.app/health` (if you have a health endpoint)

---

**Status**: Implementation Complete ✅  
**Ready to Deploy**: YES ✅  
**Estimated Deploy Time**: 2-5 minutes

