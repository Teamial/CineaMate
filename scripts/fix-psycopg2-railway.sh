#!/bin/bash

# Fix psycopg2/SQLAlchemy issue on Railway
echo "🔧 Fixing psycopg2/SQLAlchemy issue on Railway..."

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

echo "📋 The persistent issue:"
echo "   Error: Can't load plugin: sqlalchemy.dialects:postgres"
echo "   DATABASE_URL format: postgres://... (correct)"
echo ""
echo "🔍 Root cause: psycopg2-binary not properly installed/accessible"
echo ""
echo "✅ Applied fixes:"
echo "   1. Explicit psycopg2-binary installation with --force-reinstall"
echo "   2. psycopg2 version verification in both build and production stages"
echo "   3. Enhanced database.py with driver availability check"
echo "   4. Better error handling and diagnostics"
echo ""
echo "🚀 Deploying with comprehensive psycopg2 fixes..."

# Navigate to backend directory
cd backend

# Deploy with Railway CLI
echo "📦 Deploying to Railway..."
railway up

echo ""
echo "✅ Deployment initiated with psycopg2 fixes!"
echo "📝 Expected results:"
echo "   - 'psycopg2 version: 2.9.10' (in build logs)"
echo "   - 'psycopg2 version: 2.9.10' (in production stage)"
echo "   - 'Database engine created successfully'"
echo "   - 'PostgreSQL version: ...'"
echo ""
echo "🔍 If it still fails, check Railway logs for:"
echo "   - psycopg2 import errors"
echo "   - libpq5 system library issues"
echo "   - SQLAlchemy dialect loading errors"
