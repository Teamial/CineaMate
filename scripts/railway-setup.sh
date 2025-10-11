#!/bin/bash

# Simple Railway Setup Helper
# This script helps with initial setup, then guides you through the dashboard

set -e

echo "🚂 Railway Setup Helper"
echo "======================"
echo ""

# Check if Railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo "📦 Installing Railway CLI..."
    npm install -g @railway/cli
    echo "✅ Railway CLI installed"
else
    echo "✅ Railway CLI already installed"
fi

# Check if logged in
if ! railway whoami &> /dev/null; then
    echo "🔐 Please login to Railway:"
    railway login
else
    echo "✅ Already logged in to Railway"
    railway whoami
fi

echo ""
echo "🎯 Next Steps:"
echo "=============="
echo ""
echo "1. 📖 Read the deployment guide:"
echo "   open RAILWAY_DEPLOYMENT.md"
echo ""
echo "2. 🌐 Go to Railway Dashboard:"
echo "   https://railway.app"
echo ""
echo "3. 📦 Create New Project:"
echo "   - Click 'New Project'"
echo "   - Select 'Deploy from GitHub repo'"
echo "   - Choose your movie-recommender repository"
echo ""
echo "4. 🗄️ Add PostgreSQL Database:"
echo "   - Click 'New' → 'Database' → 'PostgreSQL'"
echo ""
echo "5. ⚙️ Set Environment Variables:"
echo "   - Go to your service → 'Variables'"
echo "   - Add: SECRET_KEY=$(openssl rand -hex 32)"
echo "   - Add: BACKEND_ALLOWED_ORIGINS=*"
echo ""
echo "6. 🚀 Deploy:"
echo "   - Railway will auto-deploy from GitHub"
echo "   - Get your URL from 'Deployments' tab"
echo ""
echo "7. 🎨 Deploy Frontend (separate service):"
echo "   - Create new service in same project"
echo "   - Set root directory to 'frontend'"
echo "   - Set build command: npm run build"
echo "   - Set start command: npx serve -s dist -l \$PORT"
echo ""
echo "📋 Full guide: RAILWAY_DEPLOYMENT.md"
echo ""
echo "💡 Pro tip: Keep this terminal open to run database commands later!"
echo "   railway run python movie_pipeline.py"
