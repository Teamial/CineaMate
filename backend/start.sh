#!/bin/bash

# Startup script for Railway deployment
# Initializes database and starts the FastAPI app

set -e

echo "🚀 Starting Movie Recommender Backend..."

# Use python3 explicitly (Railway uses python3)
PYTHON_CMD=$(command -v python3 || command -v python)

# Initialize database with pgvector extension
echo "🔧 Initializing database..."
$PYTHON_CMD backend/init_db.py || echo "Database already initialized"

# Create database tables
echo "🔧 Creating database tables..."
$PYTHON_CMD -c "from backend.database import engine, Base; Base.metadata.create_all(bind=engine)"

# Start the FastAPI app
echo "🚀 Starting FastAPI server..."
exec $PYTHON_CMD -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}
