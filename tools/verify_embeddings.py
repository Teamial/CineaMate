#!/usr/bin/env python3
"""
Quick verification that embedding system is ready
"""

import sys

def verify():
    print("\n🔍 Verifying Embedding-Based Recommendations Setup...\n")
    
    # Step 1: Check dependencies
    print("1️⃣  Checking dependencies...")
    try:
        import torch
        import torchvision
        from sentence_transformers import SentenceTransformer
        from PIL import Image
        print("   ✅ All dependencies installed")
        print(f"   PyTorch: {torch.__version__}")
        
        if torch.cuda.is_available():
            print(f"   🎮 GPU: {torch.cuda.get_device_name(0)}")
        else:
            print(f"   🖥️  Device: CPU")
    except ImportError as e:
        print(f"   ❌ Missing: {e}")
        return False
    
    # Step 2: Check if recommender can be imported
    print("\n2️⃣  Checking recommender system...")
    try:
        from backend.ml.embedding_recommender import DEEP_LEARNING_AVAILABLE, EmbeddingRecommender
        from backend.database import SessionLocal
        
        if DEEP_LEARNING_AVAILABLE:
            print("   ✅ Embedding recommender available")
        else:
            print("   ❌ Deep learning not available")
            return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False
    
    # Step 3: Check database connection
    print("\n3️⃣  Checking database connection...")
    try:
        db = SessionLocal()
        from backend.models import Movie
        movie_count = db.query(Movie).count()
        print(f"   ✅ Database connected ({movie_count} movies)")
        db.close()
    except Exception as e:
        print(f"   ❌ Database error: {e}")
        return False
    
    # Step 4: Check if index exists or needs building
    print("\n4️⃣  Checking embedding index...")
    try:
        db = SessionLocal()
        rec = EmbeddingRecommender(db)
        
        if rec._movie_embeddings_cache:
            metrics = rec.get_embedding_quality_metrics()
            print(f"   ✅ Index exists: {metrics['movies_in_index']} movies")
            print(f"   Coverage: {metrics['coverage']}")
            print(f"   Device: {metrics['device']}")
        else:
            print(f"   ⚠️  Index not built yet")
            print(f"   Run: python3 setup_embeddings.py")
        
        db.close()
    except Exception as e:
        print(f"   ⚠️  Index needs to be built: {e}")
    
    # Summary
    print("\n" + "=" * 60)
    print("✅ SYSTEM READY FOR EMBEDDING-BASED RECOMMENDATIONS!")
    print("=" * 60)
    
    print("\n📋 Next Steps:")
    print("   1. Build index: python3 setup_embeddings.py")
    print("   2. Test API: curl http://localhost:8000/movies/recommendations?use_embeddings=true")
    print("   3. Monitor: Track performance and engagement")
    
    print("\n📚 Documentation:")
    print("   • Quick Start: QUICK_START_EMBEDDINGS.md")
    print("   • Full Guide: backend/EMBEDDING_RECOMMENDATIONS.md")
    
    return True


if __name__ == "__main__":
    try:
        success = verify()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Verification cancelled")
        sys.exit(1)
