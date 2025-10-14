from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from fastapi.responses import RedirectResponse
from .database import engine, Base
from .routes import movies, ratings, auth, user_features, pipeline, onboarding, analytics, experiments, experiments_analytics
import logging
from sqlalchemy import text, inspect

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create database tables
try:
    Base.metadata.create_all(bind=engine)
    logger.info("✅ Database tables created successfully")
except Exception as e:
    logger.error(f"❌ Failed to create database tables: {e}")
    logger.warning("App will continue but some features may not work")

# Initialize FastAPI app
app = FastAPI(
    title="Movie Recommender API",
    description="API for movie recommendations with user ratings, reviews, and watchlists",
    version="3.0.0"
)

# CORS middleware for React frontend
allowed_origins = os.getenv("BACKEND_ALLOWED_ORIGINS", "").split(",") if os.getenv("BACKEND_ALLOWED_ORIGINS") else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(movies.router)
app.include_router(ratings.router)
app.include_router(user_features.router)
app.include_router(pipeline.router)
app.include_router(onboarding.router)
app.include_router(analytics.router)
app.include_router(experiments.router)
app.include_router(experiments_analytics.router)

# Initialize scheduler on startup
@app.on_event("startup")
async def startup_event():
    """Initialize scheduler when app starts"""
    try:
        from .scheduler import get_scheduler
        scheduler = get_scheduler()
        scheduler.start()
        logger.info("✅ Pipeline scheduler started")
    except Exception as e:
        logger.warning(f"⚠️ Could not start scheduler: {e}")
        logger.warning("Pipeline scheduler will need to be started manually")
    
    # Also try to start guardrails scheduler
    try:
        from .scheduler_pkg.guardrails_scheduler import setup_guardrails_scheduler
        from .scheduler import get_scheduler
        scheduler = get_scheduler()
        setup_guardrails_scheduler(scheduler)
        logger.info("✅ Guardrails scheduler configured")
    except Exception as e:
        logger.warning(f"⚠️ Could not configure guardrails scheduler: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    try:
        from .scheduler import get_scheduler
        scheduler = get_scheduler()
        scheduler.stop()
        logger.info("✅ Pipeline scheduler stopped")
    except:
        pass

@app.get("/")
def root():
    return {
        "message": "Welcome to Movie Recommender API v3.0",
        "docs": "/docs",
        "features": ["authentication", "favorites", "watchlist", "reviews", "ratings", "bandit_experiments"],
        "version": "3.0.0"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.post("/admin/fix-schema")
def fix_recommendation_events_schema():
    """Fix recommendation_events table schema by adding missing columns"""
    try:
        with engine.connect() as conn:
            logger.info("🔧 Fixing recommendation_events table schema...")
            
            # List of columns to add
            columns_to_add = [
                ("experiment_id", "UUID NULL"),
                ("policy", "VARCHAR(20) NULL"),
                ("arm_id", "VARCHAR(50) NULL"),
                ("p_score", "FLOAT NULL"),
                ("latency_ms", "INTEGER NULL"),
                ("reward", "FLOAT NULL"),
                ("served_at", "TIMESTAMPTZ NULL")
            ]
            
            added_count = 0
            
            for column_name, column_type in columns_to_add:
                # Check if column exists
                result = conn.execute(text(f"""
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'recommendation_events' 
                    AND column_name = '{column_name}'
                """))
                
                if result.fetchone() is None:
                    # Column doesn't exist, add it
                    alter_sql = f"ALTER TABLE recommendation_events ADD COLUMN {column_name} {column_type}"
                    conn.execute(text(alter_sql))
                    logger.info(f"✅ Added column: {column_name}")
                    added_count += 1
                else:
                    logger.info(f"ℹ️  Column {column_name} already exists")
            
            # Create indexes
            indexes_to_create = [
                ("idx_recommendation_events_experiment_id", "CREATE INDEX IF NOT EXISTS idx_recommendation_events_experiment_id ON recommendation_events(experiment_id)"),
                ("idx_recommendation_events_policy", "CREATE INDEX IF NOT EXISTS idx_recommendation_events_policy ON recommendation_events(policy)"),
                ("idx_recommendation_events_arm_id", "CREATE INDEX IF NOT EXISTS idx_recommendation_events_arm_id ON recommendation_events(arm_id)"),
                ("idx_recommendation_events_served_at", "CREATE INDEX IF NOT EXISTS idx_recommendation_events_served_at ON recommendation_events(served_at)")
            ]
            
            for index_name, create_sql in indexes_to_create:
                try:
                    conn.execute(text(create_sql))
                    logger.info(f"✅ Created index: {index_name}")
                except Exception as e:
                    logger.warning(f"⚠️  Index {index_name} may already exist: {e}")
            
            # Commit changes
            conn.commit()
            
            logger.info(f"✅ Schema fix completed! Added {added_count} columns.")
            return {"status": "success", "added_columns": added_count, "message": f"Added {added_count} columns to recommendation_events table"}
            
    except Exception as e:
        logger.error(f"❌ Error fixing schema: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/proxy/image/{path:path}")
@app.get("/api/proxy/image/{path:path}")
def proxy_image(path: str):
    """Proxy TMDB images to avoid CORS issues"""
    import requests
    from fastapi.responses import Response
    
    try:
        # Construct the full TMDB URL
        tmdb_url = f"https://image.tmdb.org/t/p/{path}"
        
        # Fetch the image from TMDB
        response = requests.get(tmdb_url, timeout=10)
        response.raise_for_status()
        
        # Return the image with proper headers
        return Response(
            content=response.content,
            media_type=response.headers.get('content-type', 'image/jpeg'),
            headers={
                'Cache-Control': 'public, max-age=86400',  # Cache for 24 hours
                'Access-Control-Allow-Origin': '*'
            }
        )
    except Exception as e:
        logger.warning(f"Failed to proxy image {path}: {e}")
        # Return a placeholder or error response
        return Response(
            content=b'', 
            media_type='image/svg+xml',
            status_code=404
        )