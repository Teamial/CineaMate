#!/bin/bash

# Railway Deployment Script for Movie Recommender
# Make sure you have Railway CLI installed: npm install -g @railway/cli

set -e

echo "🚀 Deploying Movie Recommender to Railway..."

# Check if Railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo "❌ Railway CLI not found. Install it with: npm install -g @railway/cli"
    exit 1
fi

# Check if logged in
if ! railway whoami &> /dev/null; then
    echo "❌ Not logged in to Railway. Run: railway login"
    exit 1
fi

echo "✅ Railway CLI found and logged in"

# Generate a secure secret key if not provided
if [ -z "$SECRET_KEY" ]; then
    SECRET_KEY=$(openssl rand -hex 32)
    echo "🔑 Generated new SECRET_KEY: $SECRET_KEY"
fi

# Initialize Railway project
echo "📦 Initializing Railway project..."
railway init

# Add PostgreSQL database
echo "🗄️ Adding PostgreSQL database..."
railway add postgresql

# Deploy backend
echo "🔧 Deploying backend..."
railway up

# Set backend environment variables
echo "⚙️ Setting backend environment variables..."
railway variables set SECRET_KEY="$SECRET_KEY"
railway variables set BACKEND_ALLOWED_ORIGINS="*"  # Update this with your frontend domain later

# Get the backend URL
BACKEND_URL=$(railway status --json | jq -r '.deployment.url // "https://your-backend.railway.app"')
echo "🌐 Backend URL: $BACKEND_URL"

# Deploy frontend (separate service)
echo "🎨 Deploying frontend..."
echo "Note: You'll need to create a separate Railway service for the frontend"
echo "1. Go to railway.app dashboard"
echo "2. Create new service"
echo "3. Connect your GitHub repo"
echo "4. Set build command: cd frontend && npm run build"
echo "5. Set start command: npx serve -s dist -l \$PORT"

# Set frontend environment variables (you'll do this in the dashboard)
echo "⚙️ Frontend environment variables to set in Railway dashboard:"
echo "   VITE_API_URL=$BACKEND_URL"

FRONTEND_URL="https://your-frontend.railway.app"
echo "🌐 Frontend URL: $FRONTEND_URL (set after deployment)"

echo ""
echo "🎉 Deployment complete!"
echo ""
echo "📋 Next steps:"
echo "1. Update BACKEND_ALLOWED_ORIGINS with your frontend domain: $FRONTEND_URL"
echo "2. Run database migrations: railway run python -c \"from backend.database import engine, Base; Base.metadata.create_all(bind=engine)\""
echo "3. Import movie data: railway run python movie_pipeline.py"
echo "4. Test your app: $FRONTEND_URL"
echo ""
echo "🔗 Useful URLs:"
echo "   Frontend: $FRONTEND_URL"
echo "   Backend API: $BACKEND_URL"
echo "   API Docs: $BACKEND_URL/docs"
echo ""
echo "💡 To update BACKEND_ALLOWED_ORIGINS:"
echo "   railway variables set BACKEND_ALLOWED_ORIGINS=\"$FRONTEND_URL\""
