#!/usr/bin/env python3
"""Monitor embedding-based recommendation performance"""

from backend.ml.embedding_recommender import EmbeddingRecommender
from backend.ml.recommender import MovieRecommender
from backend.database import SessionLocal
import time
import sys

def monitor():
    try:
        db = SessionLocal()
        
        print("\n" + "=" * 70)
        print("  EMBEDDING-BASED RECOMMENDATIONS - PERFORMANCE MONITOR")
        print("=" * 70)
        print()
        
        # 1. Check embedding quality
        print("📊 EMBEDDING QUALITY METRICS")
        print("-" * 70)
        try:
            rec = EmbeddingRecommender(db)
            metrics = rec.get_embedding_quality_metrics()
            
            print(f"✅ Coverage: {metrics['coverage']}")
            print(f"   Movies in index: {metrics['movies_in_index']}")
            print(f"   Total movies: {metrics['total_movies']}")
            print(f"   Poster coverage: {metrics['poster_coverage']}")
            print(f"   Device: {metrics['device']}")
            print(f"   Text dimension: {metrics.get('text_embedding_dim', 384)}")
            print(f"   Image dimension: {metrics.get('image_embedding_dim', 2048)}")
        except Exception as e:
            print(f"⚠️  Could not load metrics: {e}")
            print(f"   Run: python3 setup_embeddings.py")
        print()
        
        # 2. Measure recommendation speed
        print("⚡ PERFORMANCE TEST (3 runs for accuracy)")
        print("-" * 70)
        recommender = MovieRecommender(db)
        
        # Test 1: Embeddings (3 runs)
        emb_times = []
        for i in range(3):
            start = time.time()
            emb_recs = recommender.get_embedding_recommendations(1, 10)
            emb_times.append((time.time() - start) * 1000)
        emb_avg = sum(emb_times) / len(emb_times)
        print(f"Embedding-based:")
        print(f"  Run 1: {emb_times[0]:.0f}ms (cold)")
        print(f"  Run 2: {emb_times[1]:.0f}ms (warm)")
        print(f"  Run 3: {emb_times[2]:.0f}ms (warm)")
        print(f"  Average: {emb_avg:.0f}ms")
        print()
        
        # Test 2: Baseline (SVD)
        try:
            svd_times = []
            for i in range(3):
                start = time.time()
                svd_recs = recommender.get_svd_recommendations(1, 10)
                svd_times.append((time.time() - start) * 1000)
            svd_avg = sum(svd_times) / len(svd_times)
            print(f"SVD baseline:")
            print(f"  Average: {svd_avg:.0f}ms")
            print()
        except Exception as e:
            print(f"⚠️  SVD unavailable: {e}")
            print()
        
        # Test 3: Hybrid with embeddings
        hybrid_times = []
        for i in range(3):
            start = time.time()
            hybrid_recs = recommender.get_hybrid_recommendations(1, 10, use_embeddings=True)
            hybrid_times.append((time.time() - start) * 1000)
        hybrid_avg = sum(hybrid_times) / len(hybrid_times)
        print(f"Hybrid (with embeddings):")
        print(f"  Run 1: {hybrid_times[0]:.0f}ms (cold)")
        print(f"  Run 2: {hybrid_times[1]:.0f}ms (warm)")
        print(f"  Run 3: {hybrid_times[2]:.0f}ms (warm)")
        print(f"  Average: {hybrid_avg:.0f}ms")
        print()
        
        # Performance targets
        print("🎯 PERFORMANCE TARGETS")
        print("-" * 70)
        print("  Warm cache: < 100ms ✅ (with GPU) ⚠️ (CPU: ~1000ms)")
        print("  P95: < 200ms")
        print("  P99: < 500ms")
        print()
        
        # Assessment
        if emb_avg < 100:
            print("  ✅ Excellent performance!")
        elif emb_avg < 500:
            print("  ✅ Good performance (consider GPU for faster)")
        elif emb_avg < 2000:
            print("  ⚠️  Acceptable on CPU, GPU highly recommended for production")
        else:
            print("  ❌ Slow performance, check system resources")
        print()
        
        # 3. Show sample recommendations
        print("🎬 SAMPLE RECOMMENDATIONS")
        print("-" * 70)
        for i, movie in enumerate(emb_recs[:5], 1):
            print(f"{i}. {movie.title} ({movie.vote_average:.1f}/10)")
        print()
        
        # 4. System info
        print("💻 SYSTEM INFO")
        print("-" * 70)
        try:
            import torch
            print(f"PyTorch version: {torch.__version__}")
            if torch.cuda.is_available():
                print(f"GPU: {torch.cuda.get_device_name(0)}")
                print(f"CUDA version: {torch.version.cuda}")
            else:
                print("Device: CPU (consider GPU for 5-10x speedup)")
        except:
            pass
        print()
        
        # 5. Recommendations
        print("📋 RECOMMENDATIONS")
        print("-" * 70)
        if emb_avg > 500:
            print("⚠️  For production, consider:")
            print("   1. GPU acceleration (5-10x faster)")
            print("   2. Pre-build index on startup")
            print("   3. Redis cache for user embeddings")
            print("   4. Load balancing with shared cache")
        else:
            print("✅ System performing well!")
            print("   Monitor:")
            print("   - Cache hit rate (target: > 95%)")
            print("   - User engagement (CTR, watch rate)")
            print("   - Memory usage per request")
        print()
        
        print("=" * 70)
        print("✅ Monitoring complete!")
        print("=" * 70)
        print()
        
        db.close()
        return True
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Monitoring cancelled")
        return False
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = monitor()
    sys.exit(0 if success else 1)
