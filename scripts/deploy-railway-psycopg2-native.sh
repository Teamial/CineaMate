#!/bin/bash

# Deploy Railway backend with native psycopg2 (not binary)
echo "🔧 Deploying Railway backend with native psycopg2..."

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

echo "📋 New approach: Using native psycopg2 instead of psycopg2-binary"
echo ""
echo "🔍 Why this should work:"
echo "   - psycopg2-binary can have compatibility issues in some environments"
echo "   - Native psycopg2 compiles against system PostgreSQL libraries"
echo "   - More reliable in containerized environments"
echo ""
echo "✅ Changes made:"
echo "   1. Added libpq-dev and postgresql-client to build stage"
echo "   2. Added libpq-dev and postgresql-client to production stage"
echo "   3. Changed from psycopg2-binary to psycopg2 in requirements"
echo "   4. Explicit psycopg2 installation with --force-reinstall"
echo "   5. Version verification in both stages"
echo ""
echo "🚀 Deploying with native psycopg2..."

# Navigate to backend directory
cd backend

# Deploy with Railway CLI
echo "📦 Deploying to Railway..."
railway up

echo ""
echo "✅ Deployment initiated with native psycopg2!"
echo "📝 Expected results:"
echo "   - 'psycopg2 version: 2.9.10' (in build logs)"
echo "   - 'psycopg2 version: 2.9.10' (in production stage)"
echo "   - 'Database engine created successfully'"
echo "   - 'PostgreSQL version: ...'"
echo ""
echo "🔍 Monitor the build logs for:"
echo "   - psycopg2 compilation during build"
echo "   - Successful import verification"
echo "   - SQLAlchemy engine creation"
echo ""
echo "💡 If this still fails, the issue might be:"
echo "   - Railway environment incompatibility"
echo "   - Python/SQLAlchemy version conflicts"
echo "   - Network connectivity issues"
