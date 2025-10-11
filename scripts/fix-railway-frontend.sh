#!/bin/bash

# Fix Railway frontend deployment configuration
echo "🔧 Fixing Railway frontend deployment configuration..."

# Check if we're in the right directory
if [ ! -f "frontend/Dockerfile" ]; then
    echo "❌ Error: frontend/Dockerfile not found. Please run this script from the project root."
    exit 1
fi

# Navigate to frontend directory
cd frontend

echo "📋 Current Railway configuration:"
echo "   - Using Dockerfile build method"
echo "   - Build context: frontend/"
echo "   - No start command (using Dockerfile CMD)"

# Deploy with explicit Dockerfile configuration
echo "🚀 Deploying with corrected configuration..."
railway up --dockerfile Dockerfile

echo "✅ Deployment initiated with correct configuration!"
echo "📝 The deployment should now use nginx instead of npx serve"
echo "🔍 Check Railway dashboard for deployment status"
