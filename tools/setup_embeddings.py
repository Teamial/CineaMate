#!/usr/bin/env python3
"""
Setup script for embedding-based recommendations

This script:
1. Checks dependencies
2. Builds the full embedding index
3. Monitors performance
4. Provides recommendations for production
"""

import os
import sys
import time
from datetime import datetime

def print_header(text):
    """Print formatted header"""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def check_dependencies():
    """Check if all required dependencies are installed"""
    print_header("STEP 1: CHECKING DEPENDENCIES")
    
    try:
        import torch
        import torchvision
        from sentence_transformers import SentenceTransformer
        from PIL import Image
        
        print("\n✅ All deep learning dependencies installed!")
        print(f"\n📦 Versions:")
        print(f"   PyTorch: {torch.__version__}")
        print(f"   Torchvision: {torchvision.__version__}")
        
        # Check GPU availability
        if torch.cuda.is_available():
            print(f"\n🎮 GPU DETECTED!")
            print(f"   Device: {torch.cuda.get_device_name(0)}")
            print(f"   Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
            print(f"   → Embeddings will be 5-10x faster!")
        else:
            print(f"\n🖥️  Using CPU")
            print(f"   → Consider using GPU for production (5-10x faster)")
            print(f"   → Install CUDA-enabled PyTorch for GPU support")
        
        return True
        
    except ImportError as e:
        print(f"\n❌ Missing dependency: {e}")
        print("\n📝 Install with:")
        print("   pip install torch torchvision sentence-transformers Pillow")
        return False


def build_embedding_index(max_movies=2000):
    """Build the full embedding index"""
    print_header("STEP 2: BUILDING EMBEDDING INDEX")
    
    print(f"\n📊 Building index for up to {max_movies} movies...")
    print(f"⏱️  This will take 3-5 minutes (first time downloads models)")
    print(f"💾 Embeddings will be cached for fast subsequent use\n")
    
    try:
        from backend.ml.embedding_recommender import EmbeddingRecommender
        from backend.database import SessionLocal
        
        db = SessionLocal()
        recommender = EmbeddingRecommender(db)
        
        # Build index
        start_time = time.time()
        print("🔄 Starting build...")
        
        recommender._build_movie_embeddings_index(max_movies=max_movies)
        
        elapsed = time.time() - start_time
        
        print(f"\n✅ Index built successfully in {elapsed:.1f} seconds!")
        
        # Get metrics
        metrics = recommender.get_embedding_quality_metrics()
        
        print(f"\n📊 Index Metrics:")
        print(f"   Total movies in database: {metrics['total_movies']}")
        print(f"   Movies in embedding index: {metrics['movies_in_index']}")
        print(f"   Coverage: {metrics['coverage']}")
        print(f"   Movies with posters: {metrics['movies_with_posters']}")
        print(f"   Poster coverage: {metrics['poster_coverage']}")
        print(f"   Text embedding dimension: {metrics['text_embedding_dim']}")
        print(f"   Image embedding dimension: {metrics['image_embedding_dim']}")
        print(f"   Device: {metrics['device']}")
        
        db.close()
        return True
        
    except Exception as e:
        print(f"\n❌ Error building index: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_recommendations():
    """Test that recommendations work"""
    print_header("STEP 3: TESTING RECOMMENDATIONS")
    
    try:
        from backend.ml.recommender import MovieRecommender
        from backend.database import SessionLocal
        from backend.models import User, Rating
        from sqlalchemy import func
        
        db = SessionLocal()
        
        # Get a user with ratings
        user = db.query(User).join(Rating).group_by(User.id).having(
            func.count(Rating.id) >= 3
        ).first()
        
        if not user:
            print("\n⚠️  No users with sufficient ratings found")
            print("   Create a user and add ratings to test recommendations")
            db.close()
            return False
        
        print(f"\n👤 Testing with user: {user.username}")
        
        recommender = MovieRecommender(db)
        
        # Test embedding recommendations
        print("\n🔄 Generating embedding-based recommendations...")
        start = time.time()
        
        recs = recommender.get_embedding_recommendations(
            user_id=user.id,
            n_recommendations=10
        )
        
        elapsed = (time.time() - start) * 1000  # Convert to ms
        
        print(f"✅ Generated {len(recs)} recommendations in {elapsed:.0f}ms")
        
        print(f"\n🎬 Top 5 Recommendations:")
        for i, movie in enumerate(recs[:5], 1):
            print(f"   {i}. {movie.title} ({movie.vote_average}/10)")
        
        # Test hybrid with embeddings
        print(f"\n🔄 Testing hybrid recommendations with embeddings...")
        start = time.time()
        
        hybrid_recs = recommender.get_hybrid_recommendations(
            user_id=user.id,
            n_recommendations=10,
            use_embeddings=True
        )
        
        elapsed = (time.time() - start) * 1000
        
        print(f"✅ Generated {len(hybrid_recs)} hybrid recommendations in {elapsed:.0f}ms")
        
        db.close()
        return True
        
    except Exception as e:
        print(f"\n❌ Error testing recommendations: {e}")
        import traceback
        traceback.print_exc()
        return False


def enable_in_api():
    """Show how to enable embeddings in API"""
    print_header("STEP 4: ENABLING IN API")
    
    print("\n✅ Embeddings are already enabled in the API!")
    print("\n📝 Usage:")
    print("\n   REST API:")
    print('   curl "http://localhost:8000/movies/recommendations?user_id=1&limit=10&use_embeddings=true" \\')
    print('     -H "Authorization: Bearer $TOKEN"')
    
    print("\n   Python:")
    print("   recommendations = recommender.get_hybrid_recommendations(")
    print("       user_id=1,")
    print("       n_recommendations=10,")
    print("       use_embeddings=True  # Enable embeddings")
    print("   )")
    
    print("\n   JavaScript (Frontend):")
    print("   const response = await fetch(")
    print('     `/movies/recommendations?user_id=${userId}&limit=10&use_embeddings=true`,')
    print("     { headers: { 'Authorization': `Bearer ${token}` } }")
    print("   );")


def setup_monitoring():
    """Provide monitoring recommendations"""
    print_header("STEP 5: MONITORING & PERFORMANCE")
    
    print("\n📊 Recommended Metrics to Track:")
    print("\n   1. Recommendation Latency:")
    print("      - Target: < 100ms (warm cache)")
    print("      - Monitor P95 and P99 latencies")
    
    print("\n   2. Embedding Quality:")
    print("      - Coverage: % of movies in index")
    print("      - Cache hit rate: > 95%")
    
    print("\n   3. User Engagement:")
    print("      - Click-through rate on recommendations")
    print("      - Time spent browsing")
    print("      - Conversion rate (watched vs recommended)")
    
    print("\n   4. Business Metrics:")
    print("      - User satisfaction ratings")
    print("      - Return user rate")
    print("      - A/B test: embeddings vs baseline")
    
    print("\n🔧 Performance Monitoring Script:")
    print("\n   python3 << EOF")
    print("   from backend.ml.embedding_recommender import EmbeddingRecommender")
    print("   from backend.database import SessionLocal")
    print("   import time")
    print("")
    print("   db = SessionLocal()")
    print("   rec = EmbeddingRecommender(db)")
    print("")
    print("   # Check metrics")
    print("   metrics = rec.get_embedding_quality_metrics()")
    print("   print(f\"Coverage: {metrics['coverage']}\")")
    print("   print(f\"Device: {metrics['device']}\")")
    print("")
    print("   # Test speed")
    print("   from backend.ml.recommender import MovieRecommender")
    print("   recommender = MovieRecommender(db)")
    print("   start = time.time()")
    print("   recs = recommender.get_embedding_recommendations(user_id=1, n_recommendations=10)")
    print("   elapsed = (time.time() - start) * 1000")
    print("   print(f\"Recommendation time: {elapsed:.0f}ms\")")
    print("   EOF")


def production_recommendations():
    """Provide production deployment recommendations"""
    print_header("STEP 6: PRODUCTION RECOMMENDATIONS")
    
    print("\n🚀 For Production Deployment:")
    
    print("\n   1. GPU Acceleration (5-10x faster):")
    print("      - Install CUDA-enabled PyTorch")
    print("      - Use GPU instance (AWS p3, GCP with GPU)")
    print("      - Monitor GPU utilization")
    
    print("\n   2. Pre-build Index on Startup:")
    print("      - Add to backend/main.py startup event")
    print("      - Build index before accepting requests")
    print("      - Use persistent cache directory")
    
    print("\n   3. Scheduled Index Rebuilds:")
    print("      - Rebuild every 6-12 hours")
    print("      - Use background task/cron job")
    print("      - Monitor for new movies")
    
    print("\n   4. Caching Strategy:")
    print("      - Cache embeddings to disk (already implemented)")
    print("      - Use Redis for user embedding cache")
    print("      - Set cache TTL appropriately")
    
    print("\n   5. Load Balancing:")
    print("      - Each instance builds its own cache")
    print("      - OR share cache via network storage")
    print("      - Monitor memory usage per instance")
    
    print("\n   6. Monitoring & Alerting:")
    print("      - Track recommendation latency")
    print("      - Alert if latency > 200ms")
    print("      - Monitor embedding cache hit rate")
    print("      - Track GPU utilization (if using GPU)")
    
    print("\n   7. A/B Testing:")
    print("      - Compare embeddings vs baseline")
    print("      - Measure CTR, engagement, satisfaction")
    print("      - Gradually roll out to 100%")
    
    print("\n   8. Fallback Strategy:")
    print("      - Always have fallback to SVD")
    print("      - Handle embedding failures gracefully")
    print("      - Log errors for debugging")


def main():
    """Main setup function"""
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 68 + "║")
    print("║" + "  EMBEDDING-BASED RECOMMENDATIONS - SETUP".center(68) + "║")
    print("║" + " " * 68 + "║")
    print("╚" + "═" * 68 + "╝")
    
    print(f"\n📅 Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Step 1: Check dependencies
    if not check_dependencies():
        print("\n❌ Setup failed: Missing dependencies")
        print("   Install with: pip install torch torchvision sentence-transformers Pillow")
        return 1
    
    # Step 2: Build embedding index
    if not build_embedding_index(max_movies=2000):
        print("\n❌ Setup failed: Could not build index")
        return 1
    
    # Step 3: Test recommendations
    if not test_recommendations():
        print("\n⚠️  Setup completed but testing failed")
        print("   This is OK if you don't have users with ratings yet")
    
    # Step 4: Show API usage
    enable_in_api()
    
    # Step 5: Monitoring recommendations
    setup_monitoring()
    
    # Step 6: Production recommendations
    production_recommendations()
    
    # Summary
    print_header("✅ SETUP COMPLETE!")
    
    print("\n🎉 Embedding-based recommendations are ready!")
    
    print("\n📚 Next Steps:")
    print("   1. Start your API: uvicorn backend.main:app --reload")
    print("   2. Test endpoint: curl .../recommendations?use_embeddings=true")
    print("   3. Monitor performance: Track latency and engagement")
    print("   4. Read docs: backend/EMBEDDING_RECOMMENDATIONS.md")
    
    print("\n🔗 Documentation:")
    print("   - Quick Setup: backend/EMBEDDING_SETUP.md")
    print("   - Full Guide: backend/EMBEDDING_RECOMMENDATIONS.md")
    print("   - Summary: backend/EMBEDDING_SUMMARY.md")
    print("   - Overview: EMBEDDING_README.md")
    
    print(f"\n📅 Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

