#!/bin/bash

# Railway CLI Deployment Script
# Use this if GitHub integration isn't working

set -e

echo "🚂 Railway CLI Deployment"
echo "========================"
echo ""

# Check if Railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo "📦 Installing Railway CLI..."
    npm install -g @railway/cli
    echo "✅ Railway CLI installed"
fi

echo "🔐 Please login to Railway in your browser..."
echo "This will open a browser window for authentication"
echo ""

# Login (this will open browser)
railway login

echo ""
echo "📦 Creating new Railway project..."
railway init

echo ""
echo "🗄️ Adding PostgreSQL database..."
railway add postgresql

echo ""
echo "🔧 Setting up environment variables..."

# Generate secret key
SECRET_KEY=$(openssl rand -hex 32)
echo "Generated SECRET_KEY: $SECRET_KEY"

# Set environment variables
railway variables set SECRET_KEY="$SECRET_KEY"
railway variables set BACKEND_ALLOWED_ORIGINS="*"

echo ""
echo "🚀 Deploying backend..."
railway up

echo ""
echo "⏳ Waiting for deployment to complete..."
sleep 10

# Get deployment URL
BACKEND_URL=$(railway status --json | jq -r '.deployment.url // "https://your-backend.railway.app"')
echo "🌐 Backend URL: $BACKEND_URL"

echo ""
echo "🎉 Backend deployment complete!"
echo ""
echo "📋 Next steps:"
echo "1. Test backend: $BACKEND_URL/health"
echo "2. View API docs: $BACKEND_URL/docs"
echo "3. Initialize database: railway run python -c \"from backend.database import engine, Base; Base.metadata.create_all(bind=engine)\""
echo "4. Import movies: railway run python movie_pipeline.py"
echo ""
echo "🎨 For frontend deployment:"
echo "1. Go to railway.app dashboard"
echo "2. Create new service in same project"
echo "3. Deploy from GitHub: Teamial/movie_recommender"
echo "4. Set root directory: frontend"
echo "5. Set build command: npm run build"
echo "6. Set start command: npx serve -s dist -l \$PORT"
echo "7. Set VITE_API_URL: $BACKEND_URL"
