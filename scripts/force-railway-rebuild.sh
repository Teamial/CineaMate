#!/bin/bash

# Force Railway to rebuild backend with all fixes
echo "🔧 Forcing Railway backend rebuild with all fixes..."

# Check if Railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo "❌ Railway CLI not found. Please install it first:"
    echo "   npm install -g @railway/cli"
    exit 1
fi

echo "📋 Current status from Railway dashboard:"
echo "   ✅ pgvector service: Running (13 minutes ago)"
echo "   ❌ backend service: Crashed (6 minutes ago)"
echo "   ✅ DATABASE_URL format: Correct (postgres://...)"
echo ""
echo "🔍 The issue: Railway is using cached Docker image without our fixes"
echo ""
echo "🚀 Forcing complete rebuild..."

# Navigate to backend directory for proper context
cd backend

# Force rebuild without any cache
echo "📦 Building with --no-cache flag..."
railway up --no-cache

echo ""
echo "✅ Rebuild initiated!"
echo "📝 This should now:"
echo "   1. Install libpq5 system dependency"
echo "   2. Use the updated database.py with better error handling"
echo "   3. Test PostgreSQL connection on startup"
echo "   4. Provide detailed logs for debugging"
echo ""
echo "🔍 Monitor the deployment in Railway dashboard"
echo "   Look for these success messages:"
echo "   - 'Database engine created successfully'"
echo "   - 'PostgreSQL version: ...'"
echo "   - 'pgvector extension enabled successfully'"
