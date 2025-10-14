#!/bin/bash

# Run bandit experiment migration on Railway deployment
# This script connects to the Railway deployment and runs the migration

echo "🔧 Running bandit experiment migration on Railway..."

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

echo "🔍 Current Railway project:"
railway status

echo ""
echo "🚀 Running bandit experiment migration..."
echo "   This will add missing columns to recommendation_events table"
echo ""

# Run the migration script on Railway
railway run python backend/migrate_add_bandit_experiment.py

echo ""
echo "✅ Migration completed!"
echo ""
echo "🧪 Test the thumbs up/down feature now:"
echo "   1. Go to https://cineamate.up.railway.app"
echo "   2. Log in to your account"
echo "   3. Try clicking thumbs up/down on any movie"
echo "   4. Check browser console for any errors"
echo ""
echo "📝 If you still see errors, check the Railway logs:"
echo "   railway logs"
