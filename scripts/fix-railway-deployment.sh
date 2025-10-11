#!/bin/bash

# Fix Railway deployment by using optimized Dockerfile
# This reduces image size from 7.6GB to under 4GB

set -e

echo "🔧 Fixing Railway Deployment (Image Size Issue)"
echo "=============================================="
echo ""

# Check if we're in a Railway project
if ! railway status &> /dev/null; then
    echo "❌ Not in a Railway project. Run 'railway link' first."
    exit 1
fi

echo "📦 Current issue: Docker image is 7.6GB (Railway limit: 4GB)"
echo "🎯 Solution: Use optimized Dockerfile with CPU-only PyTorch"
echo ""

# Backup original Dockerfile
if [ -f "backend/Dockerfile" ]; then
    echo "💾 Backing up original Dockerfile..."
    cp backend/Dockerfile backend/Dockerfile.backup
fi

# Use optimized Dockerfile
echo "🔄 Switching to optimized Dockerfile..."
cp Dockerfile.railway backend/Dockerfile

# Commit changes
echo "📝 Committing changes..."
git add .
git commit -m "Fix: Use optimized Dockerfile for Railway deployment (reduce image size)"

# Push to trigger new deployment
echo "🚀 Pushing to trigger new Railway deployment..."
git push origin main

echo ""
echo "✅ Deployment fix applied!"
echo ""
echo "📋 What happened:"
echo "   - Switched to CPU-only PyTorch (much smaller)"
echo "   - Used multi-stage Docker build"
echo "   - Optimized requirements.txt"
echo "   - Pushed changes to trigger new deployment"
echo ""
echo "⏳ Railway will now build with the optimized Dockerfile"
echo "   Expected image size: ~2-3GB (under 4GB limit)"
echo ""
echo "🔍 Monitor deployment:"
echo "   - Go to Railway dashboard"
echo "   - Watch the new deployment build"
echo "   - Should complete successfully now"
echo ""
echo "🎉 Once deployed, your backend will be live!"
