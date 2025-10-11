#!/bin/bash

# Startup script for Railway deployment
# Initializes database and starts the FastAPI app

set -e

echo "🚀 Starting Movie Recommender Backend..."

# Initialize database with pgvector extension
echo "🔧 Initializing database..."
python backend/init_db.py

# Create database tables
echo "🔧 Creating database tables..."
python -c "from backend.database import engine, Base; Base.metadata.create_all(bind=engine)"

# Start the FastAPI app
echo "🚀 Starting FastAPI server..."
exec python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
