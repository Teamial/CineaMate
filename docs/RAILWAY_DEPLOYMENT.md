# 🚂 Railway Deployment - Step by Step

## Prerequisites
1. Railway account: [railway.app](https://railway.app)
2. GitHub repository with your code
3. Railway CLI: `npm install -g @railway/cli`

## Step 1: Prepare Your Repository

Make sure your code is pushed to GitHub:
```bash
git add .
git commit -m "Ready for cloud deployment"
git push origin main
```

## Step 2: Deploy Backend

### 2.1 Create Backend Service
1. Go to [railway.app](https://railway.app)
2. Click "New Project"
3. Select "Deploy from GitHub repo"
4. Choose your repository
5. Railway will detect it's a Python project

### 2.2 Configure Backend
1. In Railway dashboard, go to your service
2. Click "Variables" tab
3. Add these environment variables:

```
SECRET_KEY=your-secret-key-here
BACKEND_ALLOWED_ORIGINS=*
```

### 2.3 Add Database
1. Click "New" → "Database" → "PostgreSQL"
2. Railway will automatically set `DATABASE_URL`
3. Your backend will connect automatically

### 2.4 Deploy
1. Railway will automatically deploy when you push to GitHub
2. Get your backend URL from the "Deployments" tab

## Step 3: Deploy Frontend

### 3.1 Create Frontend Service
1. In the same Railway project, click "New Service"
2. Select "Deploy from GitHub repo"
3. Choose the same repository
4. Set the **Root Directory** to `frontend`

### 3.2 Configure Frontend Build
1. Go to "Settings" → "Build"
2. Set **Build Command**: `npm run build`
3. Set **Start Command**: `npx serve -s dist -l $PORT`
4. Set **Output Directory**: `dist`

### 3.3 Set Environment Variables
1. Go to "Variables" tab
2. Add: `VITE_API_URL=https://your-backend-url.railway.app`

## Step 4: Configure Domains

### 4.1 Backend Domain
1. Go to backend service → "Settings" → "Domains"
2. Railway provides: `https://your-backend.railway.app`

### 4.2 Frontend Domain  
1. Go to frontend service → "Settings" → "Domains"
2. Railway provides: `https://your-frontend.railway.app`

### 4.3 Update CORS
1. Go to backend service → "Variables"
2. Update: `BACKEND_ALLOWED_ORIGINS=https://your-frontend.railway.app`

## Step 5: Initialize Database

### 5.1 Run Migrations
1. Go to backend service → "Deployments"
2. Click on latest deployment → "View Logs"
3. Or use Railway CLI:

```bash
railway login
railway link  # Link to your project
railway run python -c "from backend.database import engine, Base; Base.metadata.create_all(bind=engine)"
```

### 5.2 Import Movie Data
```bash
railway run python movie_pipeline.py
```

## Step 6: Test Your Deployment

1. **Backend Health**: `https://your-backend.railway.app/health`
2. **API Docs**: `https://your-backend.railway.app/docs`
3. **Frontend**: `https://your-frontend.railway.app`

## Troubleshooting

### Backend Issues
- Check logs in Railway dashboard
- Verify environment variables are set
- Ensure DATABASE_URL is automatically provided

### Frontend Issues
- Check build logs for errors
- Verify VITE_API_URL points to correct backend
- Check browser console for API errors

### Database Issues
- Ensure pgvector extension is enabled (Railway handles this)
- Check connection string format
- Verify database is running

## Cost
- **Database**: $5/month
- **Backend**: $5/month  
- **Frontend**: $5/month
- **Total**: ~$15/month

## Custom Domain (Optional)
1. Go to service → "Settings" → "Domains"
2. Click "Custom Domain"
3. Add your domain
4. Update DNS records as instructed

---

## Quick Commands

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Link to project (after creating in dashboard)
railway link

# View logs
railway logs

# Run commands
railway run python movie_pipeline.py

# Set variables
railway variables set SECRET_KEY=your-key
```

Your app will be live 24/7! 🎉
