#!/bin/bash

# Deploy Frontend to Vercel
# This keeps your backend on Railway and frontend on Vercel

set -e

echo "⚡ Deploying Frontend to Vercel"
echo "==============================="
echo ""

# Check if Vercel CLI is installed
if ! command -v vercel &> /dev/null; then
    echo "📦 Installing Vercel CLI..."
    npm install -g vercel
    echo "✅ Vercel CLI installed"
fi

# Check if logged in
if ! vercel whoami &> /dev/null; then
    echo "🔐 Please login to Vercel:"
    vercel login
else
    echo "✅ Already logged in to Vercel"
    vercel whoami
fi

echo ""
echo "🎯 What's your Railway backend URL?"
echo "Example: https://your-backend.railway.app"
read -p "Backend URL: " BACKEND_URL

echo ""
echo "🚀 Deploying to Vercel..."

# Deploy with environment variable
vercel --prod --env VITE_API_URL="$BACKEND_URL"

echo ""
echo "🎉 Frontend deployed to Vercel!"
echo ""
echo "📋 Next steps:"
echo "1. Update Railway backend CORS:"
echo "   - Go to Railway dashboard → Backend service → Variables"
echo "   - Update BACKEND_ALLOWED_ORIGINS with your Vercel URL"
echo ""
echo "2. Test your app:"
echo "   - Frontend: https://your-app.vercel.app"
echo "   - Backend: $BACKEND_URL"
echo ""
echo "3. Optional - Custom domain:"
echo "   - Add custom domain in Vercel dashboard"
echo "   - Update BACKEND_ALLOWED_ORIGINS with your custom domain"
