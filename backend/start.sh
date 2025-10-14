#!/bin/bash

# Startup script for Railway deployment
# Initializes database and starts the FastAPI app

# Remove set -e to prevent script from exiting on non-critical errors
# set -e

echo "🚀 Starting Movie Recommender Backend..."

# Use python3 explicitly (Railway uses python3)
PYTHON_CMD=$(command -v python3 || command -v python)

# Initialize database with pgvector extension
echo "🔧 Initializing database..."
if ! $PYTHON_CMD backend/init_db.py; then
    echo "⚠️ Database initialization failed, continuing anyway..."
fi

# Create database tables
echo "🔧 Creating database tables..."
if ! $PYTHON_CMD -c "from backend.database import engine, Base; Base.metadata.create_all(bind=engine)"; then
    echo "⚠️ Database table creation failed, continuing anyway..."
fi

echo "🔧 Running bandit experiment migration..."
if ! $PYTHON_CMD backend/migrate_add_bandit_experiment.py; then
    echo "⚠️ Bandit migration failed, continuing anyway..."
fi

echo "🔧 Running recommendation_events migration (simple)..."
if ! $PYTHON_CMD backend/migrate_recommendation_events_simple.py; then
    echo "⚠️ Recommendation events migration failed, continuing anyway..."
fi

# Test imports before starting the app
echo "🔧 Testing critical imports..."
if ! $PYTHON_CMD -c "
try:
    from backend.main import app
    print('✅ FastAPI app imports successfully')
except Exception as e:
    print(f'❌ FastAPI app import failed: {e}')
    import traceback
    traceback.print_exc()
    exit(1)
"; then
    echo "❌ Critical import test failed, but continuing anyway..."
fi

# Start the FastAPI app
echo "🚀 Starting FastAPI server on port ${PORT:-8000}..."
exec $PYTHON_CMD -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'
