#!/bin/bash

# Fix CORS configuration for Railway deployment
# This script sets the BACKEND_ALLOWED_ORIGINS to include the frontend domain

echo "🔧 Fixing CORS configuration for Railway deployment..."

# Check if railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo "❌ Railway CLI not found. Please install it first:"
    echo "   npm install -g @railway/cli"
    echo "   or"
    echo "   curl -fsSL https://railway.app/install.sh | sh"
    exit 1
fi

# Check if user is logged in
if ! railway whoami &> /dev/null; then
    echo "❌ Not logged in to Railway. Please run: railway login"
    exit 1
fi

echo "🔍 Current Railway projects:"
railway status

echo ""
echo "🔍 Checking current BACKEND_ALLOWED_ORIGINS..."
CURRENT_CORS=$(railway variables get BACKEND_ALLOWED_ORIGINS 2>/dev/null || echo "NOT_SET")

if [ "$CURRENT_CORS" = "NOT_SET" ]; then
    echo "❌ BACKEND_ALLOWED_ORIGINS not found!"
else
    echo "✅ Current BACKEND_ALLOWED_ORIGINS: $CURRENT_CORS"
fi

echo ""
echo "🔧 Setting BACKEND_ALLOWED_ORIGINS to allow frontend domain..."
echo "   Frontend: https://cineamate.up.railway.app"
echo "   Backend: https://backend-production-003c.up.railway.app"

# Set the CORS to allow the frontend domain
railway variables --set "BACKEND_ALLOWED_ORIGINS=https://cineamate.up.railway.app"

echo ""
echo "✅ BACKEND_ALLOWED_ORIGINS updated!"
echo ""
echo "🔄 The backend will need to restart to pick up the new environment variable."
echo "   This usually happens automatically on Railway."
echo ""
echo "🧪 Test the fix by:"
echo "   1. Wait 1-2 minutes for the backend to restart"
echo "   2. Try clicking thumbs up/down on a movie"
echo "   3. Check browser console for CORS errors"
echo ""
echo "📝 If you need to allow additional domains, run:"
echo "   railway variables --set \"BACKEND_ALLOWED_ORIGINS=https://cineamate.up.railway.app,https://your-other-domain.com\""
