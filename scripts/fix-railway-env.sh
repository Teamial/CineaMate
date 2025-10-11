#!/bin/bash

# Fix Railway environment variables for database connection

set -e

echo "🔧 Fixing Railway Environment Variables"
echo "======================================="
echo ""

# Check if we're in a Railway project
if ! railway status &> /dev/null; then
    echo "❌ Not in a Railway project. Run 'railway link' first."
    exit 1
fi

echo "📋 Current environment variables:"
railway variables

echo ""
echo "🔍 Checking for DATABASE_URL..."
DATABASE_URL=$(railway variables get DATABASE_URL 2>/dev/null || echo "")

if [ -z "$DATABASE_URL" ]; then
    echo "❌ DATABASE_URL not found!"
    echo ""
    echo "🔧 To fix this:"
    echo "1. Go to Railway dashboard"
    echo "2. Click on your PostgreSQL service"
    echo "3. Go to 'Variables' tab"
    echo "4. Copy the DATABASE_URL value"
    echo "5. Go to your backend service"
    echo "6. Go to 'Variables' tab"
    echo "7. Add DATABASE_URL with the copied value"
    echo ""
    echo "Or run this command with your DATABASE_URL:"
    echo "railway variables set DATABASE_URL='your-database-url-here'"
else
    echo "✅ DATABASE_URL found: ${DATABASE_URL:0:50}..."
fi

echo ""
echo "🔍 Checking for SECRET_KEY..."
SECRET_KEY=$(railway variables get SECRET_KEY 2>/dev/null || echo "")

if [ -z "$SECRET_KEY" ]; then
    echo "❌ SECRET_KEY not found!"
    echo "🔧 Generating and setting SECRET_KEY..."
    NEW_SECRET_KEY=$(openssl rand -hex 32)
    railway variables set SECRET_KEY="$NEW_SECRET_KEY"
    echo "✅ SECRET_KEY set: $NEW_SECRET_KEY"
else
    echo "✅ SECRET_KEY found"
fi

echo ""
echo "🔍 Checking for BACKEND_ALLOWED_ORIGINS..."
CORS=$(railway variables get BACKEND_ALLOWED_ORIGINS 2>/dev/null || echo "")

if [ -z "$CORS" ]; then
    echo "❌ BACKEND_ALLOWED_ORIGINS not found!"
    echo "🔧 Setting BACKEND_ALLOWED_ORIGINS to * (allow all origins)"
    railway variables set BACKEND_ALLOWED_ORIGINS="*"
    echo "✅ BACKEND_ALLOWED_ORIGINS set to *"
else
    echo "✅ BACKEND_ALLOWED_ORIGINS found: $CORS"
fi

echo ""
echo "🎉 Environment variables check complete!"
echo ""
echo "📋 Next steps:"
echo "1. If DATABASE_URL was missing, set it manually in Railway dashboard"
echo "2. Restart your backend service"
echo "3. Check the logs to see if it connects successfully"
echo ""
echo "🔗 Railway Dashboard: https://railway.app"
