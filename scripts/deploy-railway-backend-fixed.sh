#!/bin/bash

# Deploy Railway backend with all fixes applied
echo "🚀 Deploying Railway backend with comprehensive fixes..."

# Check if we're in the right directory
if [ ! -f "backend/Dockerfile" ]; then
    echo "❌ Error: backend/Dockerfile not found. Please run this script from the project root."
    exit 1
fi

# Check if Railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo "❌ Railway CLI not found. Please install it first:"
    echo "   npm install -g @railway/cli"
    exit 1
fi

echo "📋 Applied fixes:"
echo "   ✅ Updated Dockerfile with libpq5 system dependency"
echo "   ✅ Enhanced database.py with URL format conversion"
echo "   ✅ Added better error handling and diagnostics"
echo "   ✅ Added connection testing"
echo ""
echo "🔧 Forcing Railway to rebuild without cache..."
railway up --no-cache

echo ""
echo "✅ Deployment initiated with all fixes!"
echo "📝 The backend should now:"
echo "   1. Install libpq5 system dependency"
echo "   2. Convert DATABASE_URL format if needed"
echo "   3. Test PostgreSQL connection on startup"
echo "   4. Provide detailed error messages if issues occur"
echo ""
echo "🔍 Check Railway logs for:"
echo "   - 'Database engine created successfully'"
echo "   - 'PostgreSQL version: ...'"
echo "   - Any error messages with detailed diagnostics"
