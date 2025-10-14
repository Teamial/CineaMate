from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from fastapi.responses import RedirectResponse
from .database import engine, Base
from .routes import movies, ratings, auth, user_features, pipeline, onboarding, analytics, experiments, experiments_analytics
import logging

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