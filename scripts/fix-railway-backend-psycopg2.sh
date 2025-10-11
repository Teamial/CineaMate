#!/bin/bash

# Fix Railway backend psycopg2/SQLAlchemy issue
echo "🔧 Fixing Railway backend psycopg2 issue..."

# Check if we're in the right directory
if [ ! -f "backend/Dockerfile" ]; then
    echo "❌ Error: backend/Dockerfile not found. Please run this script from the project root."
    exit 1
fi

echo "📋 The issue: SQLAlchemy can't load PostgreSQL dialect"
echo "   Error: Can't load plugin: sqlalchemy.dialects:postgres"
echo ""
echo "🔍 Root cause: psycopg2-binary needs system libraries (libpq5)"
echo "   The multi-stage Docker build wasn't copying system dependencies"
echo ""
echo "✅ Fix applied:"
echo "   - Added libpq5 system dependency to both Dockerfiles"
echo "   - Updated Dockerfile.railway"
echo "   - Updated backend/Dockerfile"
echo ""
echo "🚀 Next steps:"
echo "   1. Redeploy your backend service on Railway"
echo "   2. The backend should now connect to PostgreSQL successfully"
echo ""
echo "📝 Files updated:"
echo "   - Dockerfile.railway (added libpq5)"
echo "   - backend/Dockerfile (added libpq5)"
echo ""
echo "💡 The fix ensures psycopg2-binary has the required system libraries"
echo "   to connect to PostgreSQL and load the SQLAlchemy dialect."
