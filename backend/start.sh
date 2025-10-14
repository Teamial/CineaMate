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

echo "🔧 Running bandit experiment migration..."
$PYTHON_CMD backend/migrate_add_bandit_experiment.py || echo "Bandit migration skipped or already applied"

# Test imports before starting the app
echo "🔧 Testing critical imports..."
$PYTHON_CMD -c "
try:
    from backend.main import app
    print('✅ FastAPI app imports successfully')
except Exception as e:
    print(f'❌ FastAPI app import failed: {e}')
    import traceback
    traceback.print_exc()
    exit(1)
"

# Start the FastAPI app
echo "🚀 Starting FastAPI server on port ${PORT:-8000}..."
exec $PYTHON_CMD -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'
