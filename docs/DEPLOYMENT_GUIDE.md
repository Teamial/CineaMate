# 🚀 Cloud Deployment Guide

## Option 1: Railway (Recommended - Easiest)

### Prerequisites
1. Create a Railway account at [railway.app](https://railway.app)
2. Install Railway CLI: `npm install -g @railway/cli`
3. Login: `railway login`

### Step 1: Deploy Database
```bash
# Create a new project
railway new movie-recommender

# Add PostgreSQL database
railway add postgresql

# Get database URL
railway variables
```

### Step 2: Deploy Backend
```bash
# Navigate to project root
cd /Users/tea/Documents/Passion-Projects/movie_recommender

# Deploy backend
railway up --service backend

# Set environment variables
railway variables set DATABASE_URL="postgresql://user:pass@host:port/db"
railway variables set SECRET_KEY="your-super-secret-key-here"
railway variables set BACKEND_ALLOWED_ORIGINS="https://your-frontend-domain.com"
```

### Step 3: Deploy Frontend
```bash
# Deploy frontend (separate service)
railway up --service frontend --dockerfile Dockerfile --build-context frontend

# Set frontend environment variables
railway variables set VITE_API_URL="https://your-backend-domain.railway.app"
```

### Step 4: Configure Domains
- Railway will provide URLs like `https://backend-production-xxxx.up.railway.app`
- You can add custom domains in Railway dashboard

---

## Option 2: DigitalOcean App Platform

### Prerequisites
1. Create DigitalOcean account
2. Install doctl CLI
3. Create a DigitalOcean App

### Step 1: Create app.yaml
```yaml
name: movie-recommender
services:
- name: backend
  source_dir: /
  github:
    repo: your-username/movie-recommender
    branch: main
  run_command: python -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT
  environment_slug: python
  instance_count: 1
  instance_size_slug: basic-xxs
  envs:
  - key: DATABASE_URL
    value: ${db.DATABASE_URL}
  - key: SECRET_KEY
    value: your-secret-key
  - key: BACKEND_ALLOWED_ORIGINS
    value: https://your-frontend-domain.com

- name: frontend
  source_dir: /frontend
  github:
    repo: your-username/movie-recommender
    branch: main
  build_command: npm run build
  run_command: npx serve -s dist -l $PORT
  environment_slug: node-js
  instance_count: 1
  instance_size_slug: basic-xxs
  envs:
  - key: VITE_API_URL
    value: https://your-backend-domain.ondigitalocean.app

databases:
- name: db
  engine: PG
  version: "16"
```

---

## Option 3: Vercel + Supabase (Serverless)

### Backend on Vercel
1. Create `vercel.json`:
```json
{
  "version": 2,
  "builds": [
    {
      "src": "backend/main.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "backend/main.py"
    }
  ]
}
```

2. Deploy: `vercel --prod`

### Frontend on Vercel
1. Set build command: `npm run build`
2. Set output directory: `frontend/dist`
3. Deploy: `vercel --prod`

### Database on Supabase
1. Create Supabase project
2. Enable pgvector extension
3. Update DATABASE_URL

---

## Environment Variables Needed

### Backend
- `DATABASE_URL`: PostgreSQL connection string
- `SECRET_KEY`: JWT secret key (generate with `openssl rand -hex 32`)
- `BACKEND_ALLOWED_ORIGINS`: Comma-separated list of allowed origins

### Frontend
- `VITE_API_URL`: Backend API URL

---

## Post-Deployment Steps

1. **Run Database Migrations**
```bash
# Connect to your cloud database and run:
python -c "from backend.database import engine, Base; Base.metadata.create_all(bind=engine)"
```

2. **Import Movie Data**
```bash
# Run your movie pipeline
python movie_pipeline.py
```

3. **Test the Deployment**
- Check health endpoint: `https://your-backend.railway.app/health`
- Test API docs: `https://your-backend.railway.app/docs`
- Verify frontend loads images correctly

---

## Cost Estimates

### Railway
- Database: $5/month
- Backend: $5/month  
- Frontend: $5/month
- **Total: ~$15/month**

### DigitalOcean
- App Platform: $12/month
- Managed Database: $15/month
- **Total: ~$27/month**

### Vercel + Supabase
- Vercel Pro: $20/month
- Supabase Pro: $25/month
- **Total: ~$45/month**

---

## Recommended: Start with Railway

Railway is the easiest and most cost-effective option for your movie recommender app. It handles:
- Automatic deployments from Git
- Built-in PostgreSQL with pgvector
- Automatic HTTPS
- Simple environment variable management
- Reasonable pricing

Would you like me to help you set up Railway deployment?
