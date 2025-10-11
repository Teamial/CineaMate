#!/bin/bash

# Quick Cloud Setup Script for Movie Recommender
# This script helps you get started with cloud deployment

set -e

echo "🎬 Movie Recommender Cloud Setup"
echo "================================"
echo ""

# Check if Railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo "📦 Installing Railway CLI..."
    npm install -g @railway/cli
    echo "✅ Railway CLI installed"
else
    echo "✅ Railway CLI already installed"
fi

# Check if logged in
if ! railway whoami &> /dev/null; then
    echo "🔐 Please login to Railway:"
    railway login
else
    echo "✅ Already logged in to Railway"
fi

echo ""
echo "🚀 Ready to deploy! Choose an option:"
echo ""
echo "1. 🚂 Deploy to Railway (Recommended - $15/month)"
echo "2. 🌊 Deploy to DigitalOcean App Platform ($27/month)"
echo "3. ⚡ Deploy to Vercel + Supabase ($45/month)"
echo "4. 📖 Show deployment guide"
echo ""

read -p "Enter your choice (1-4): " choice

case $choice in
    1)
        echo "🚂 Deploying to Railway..."
        ./deploy-railway.sh
        ;;
    2)
        echo "🌊 DigitalOcean deployment guide:"
        echo "1. Create account at digitalocean.com"
        echo "2. Create new App Platform project"
        echo "3. Connect your GitHub repository"
        echo "4. Use the app.yaml configuration from DEPLOYMENT_GUIDE.md"
        ;;
    3)
        echo "⚡ Vercel + Supabase deployment guide:"
        echo "1. Create Vercel account at vercel.com"
        echo "2. Create Supabase account at supabase.com"
        echo "3. Deploy backend to Vercel"
        echo "4. Deploy frontend to Vercel"
        echo "5. Configure Supabase database"
        ;;
    4)
        echo "📖 Opening deployment guide..."
        if command -v open &> /dev/null; then
            open DEPLOYMENT_GUIDE.md
        else
            echo "Please open DEPLOYMENT_GUIDE.md to view the full guide"
        fi
        ;;
    *)
        echo "❌ Invalid choice"
        exit 1
        ;;
esac

echo ""
echo "🎉 Setup complete! Your app will be available 24/7 in the cloud."
