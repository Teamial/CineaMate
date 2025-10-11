# Bandit Selector A/B Testing Deployment Guide

## 🎯 Overview

This guide walks you through deploying the Thompson Sampling bandit selector for intelligent algorithm selection with A/B testing.

**What's New:**
- ✅ Thompson Sampling bandit for algorithm selection
- ✅ Automated A/B testing (bandit vs hybrid)
- ✅ Continuous learning from user feedback
- ✅ Automated monitoring and alerting
- ✅ Bandit performance dashboard

---

## 📋 Pre-Deployment Checklist

### 1. Database Requirements
- [ ] PostgreSQL database accessible
- [ ] `DATABASE_URL` environment variable set
- [ ] Database has existing tables (users, movies, ratings, etc.)

### 2. Dependencies
- [ ] Python 3.8+ installed
- [ ] All requirements installed: `pip install -r deployment/requirements.txt`
- [ ] NumPy available for Thompson Sampling

### 3. Existing System
- [ ] API server running on port 8000
- [ ] Frontend deployed and accessible
- [ ] Recommendation system functional

---

## 🚀 Deployment Steps

### Step 1: Run Database Migration

```bash
cd /Users/tea/Documents/Passion-Projects/movie_recommender
python backend/migrate_add_bandit_states.py
```

**Expected Output:**
```
🎰 Adding bandit_states table for Thompson Sampling...
📊 Creating bandit_states table...
✅ Created bandit_states table with indexes

✨ Migration completed successfully!

Next steps:
1. Restart your API server
2. The bandit selector will automatically start learning
3. Monitor performance with: python backend/ml/monitoring_alerts.py
```

**Verify Migration:**
```bash
# Connect to your database
psql $DATABASE_URL

# Check table exists
\dt bandit_states

# Should show:
#  Schema |      Name      | Type  |  Owner
# --------+----------------+-------+---------
#  public | bandit_states  | table | user
```

### Step 2: Restart API Server

```bash
# Development
uvicorn backend.main:app --reload

# Production (with gunicorn)
gunicorn backend.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Step 3: Verify Bandit Integration

**Test the recommendations endpoint:**
```bash
# Get your auth token first
TOKEN="your_jwt_token"

# Test bandit recommendations (A/B test group)
curl -X GET "http://localhost:8000/movies/recommendations?user_id=1&use_bandit=true" \
  -H "Authorization: Bearer $TOKEN"

# Test hybrid recommendations (control group)
curl -X GET "http://localhost:8000/movies/recommendations?user_id=1&use_bandit=false" \
  -H "Authorization: Bearer $TOKEN"
```

**Check bandit statistics:**
```bash
curl -X GET "http://localhost:8000/analytics/bandit/stats" \
  -H "Authorization: Bearer $TOKEN"
```

### Step 4: Enable Automated Monitoring

The monitoring is already integrated into the scheduler. It runs daily at 9 AM.

**Test monitoring manually:**
```bash
python backend/ml/monitoring_alerts.py
```

**Expected Output:**
```
============================================================
RECOMMENDATION SYSTEM MONITORING REPORT
============================================================

Timestamp: 2025-10-11T...
Period: Last 7 days
Overall Status: HEALTHY

📊 Health Checks:

✅ Diversity: OK
   Metrics:
      • long_tail_percentage: 0.234
      • genre_diversity: 0.456

✅ Quality: OK
   Metrics:
      • avg_rating: 4.1
      • ctr: 0.23

✅ Algorithm Balance: OK

✅ Engagement: OK

✅ No alerts - system is healthy!

============================================================
💾 Report saved to: monitoring_report.json
```

---

## 🧪 A/B Testing Configuration

### Current Setup

The system automatically runs A/B testing:

- **Treatment Group (A)**: `use_bandit=true` (default)
  - Uses Thompson Sampling to select algorithms
  - Learns from user feedback
  - Optimizes for context (time, user type, etc.)

- **Control Group (B)**: `use_bandit=false`
  - Uses classic hybrid approach
  - Fixed algorithm weights
  - No learning

### Frontend Integration

Update your frontend to randomly assign users to A/B groups:

```javascript
// In your recommendations fetch logic
const userId = getCurrentUserId();
const useBandit = userId % 2 === 0; // 50/50 split

const response = await fetch(
  `/movies/recommendations?user_id=${userId}&use_bandit=${useBandit}`,
  {
    headers: { 'Authorization': `Bearer ${token}` }
  }
);
```

Or use session-based assignment:
```javascript
// Store in session on first visit
if (!sessionStorage.getItem('ab_group')) {
  sessionStorage.setItem('ab_group', Math.random() < 0.5 ? 'bandit' : 'control');
}

const useBandit = sessionStorage.getItem('ab_group') === 'bandit';
```

---

## 📊 Monitoring & Analytics

### Available Endpoints

#### 1. Bandit Statistics
```bash
GET /analytics/bandit/stats
```

Returns:
- Overall success rate
- Per-algorithm performance
- Context-specific stats
- Selection rates

#### 2. Algorithm Performance
```bash
GET /analytics/performance?days=30
```

Compare performance between:
- `bandit_svd`, `bandit_embeddings`, etc. (treatment)
- `hybrid_control` (control)

#### 3. Recommendation Stats
```bash
GET /analytics/recommendations/stats?days=7
```

Overall recommendation metrics.

### Monitoring Dashboard

Create a simple dashboard that tracks:

1. **A/B Test Results:**
   - CTR: Bandit vs Control
   - Rating conversion: Bandit vs Control
   - Average rating: Bandit vs Control

2. **Bandit Learning:**
   - Algorithm selection rates over time
   - Success rates by algorithm
   - Context distribution

3. **System Health:**
   - Diversity metrics
   - Quality metrics
   - Engagement metrics

### Sample Dashboard Query

```sql
-- Compare A/B groups
SELECT 
    CASE 
        WHEN algorithm LIKE 'bandit_%' THEN 'treatment'
        WHEN algorithm = 'hybrid_control' THEN 'control'
        ELSE 'other'
    END as ab_group,
    COUNT(*) as total_recs,
    SUM(CASE WHEN clicked THEN 1 ELSE 0 END)::float / COUNT(*) * 100 as ctr,
    AVG(rating_value) as avg_rating,
    SUM(CASE WHEN thumbs_up THEN 1 ELSE 0 END) as thumbs_up,
    SUM(CASE WHEN thumbs_down THEN 1 ELSE 0 END) as thumbs_down
FROM recommendation_events
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY ab_group;
```

---

## 🔄 Continuous Learning

### How It Works

1. **User gets recommendations** → Algorithm selected by bandit
2. **User clicks/rates/thumbs** → Feedback tracked
3. **System updates bandit state** → Alpha/beta parameters adjusted
4. **Next recommendation** → Bandit uses updated knowledge

### Feedback Loop

The system automatically updates the bandit when:

- ✅ **Success** (α += 1):
  - User clicks recommendation
  - User rates ≥ 4.0 stars
  - User gives thumbs up

- ❌ **Failure** (β += 1):
  - User rates ≤ 2.0 stars
  - User gives thumbs down

- ⚪ **Neutral** (no update):
  - User rates 2.5-3.5 stars
  - No interaction yet

### Monitoring Learning Progress

```bash
# Check bandit stats
curl -X GET "http://localhost:8000/analytics/bandit/stats" \
  -H "Authorization: Bearer $TOKEN"
```

Look for:
- Increasing alpha/beta values (bandit is learning)
- Emerging winners (some algorithms selected more often)
- Context-specific patterns (different algorithms for different contexts)

---

## 🎛️ Configuration

### Bandit Parameters

Edit `backend/ml/bandit_selector.py`:

```python
class BanditSelector:
    def __init__(self, db: Session):
        self.algorithms = ['svd', 'embeddings', 'graph', 'item_cf', 'long_tail', 'serendipity']
        self.default_alpha = 1.0  # Starting optimism
        self.default_beta = 1.0   # Starting pessimism
```

**Tuning Guide:**
- Higher α → More optimistic, more exploration
- Higher β → More pessimistic, more exploitation
- Both = 1.0 → Uniform prior (recommended)

### Success Criteria

Edit feedback tracking in `backend/routes/analytics.py`:

```python
# Adjust thresholds
if data.rating >= 4.0:  # Change to 4.5 for stricter success
    outcome = 'success'
elif data.rating <= 2.0:  # Change to 2.5 for stricter failure
    outcome = 'failure'
```

### Monitoring Thresholds

Edit `backend/ml/monitoring_alerts.py`:

```python
self.thresholds = {
    'min_long_tail_rate': 0.20,  # Adjust diversity threshold
    'min_avg_rating': 3.5,        # Adjust quality threshold
    'max_algorithm_dominance': 0.70,  # Adjust exploration threshold
    'min_ctr': 0.10,              # Adjust engagement threshold
}
```

---

## 🐛 Troubleshooting

### Issue: Bandit table doesn't exist

**Symptoms:** `relation "bandit_states" does not exist`

**Solution:**
```bash
python backend/migrate_add_bandit_states.py
```

### Issue: All recommendations use same algorithm

**Symptoms:** Bandit stats show one algorithm at 100%

**Causes:**
- Not enough data yet (wait for feedback)
- One algorithm genuinely performing much better
- Context too coarse (all users in same context)

**Solution:**
1. Check if enough feedback collected: `SELECT COUNT(*) FROM bandit_states`
2. Check algorithm performance: `GET /analytics/performance`
3. Wait longer for bandit to explore

### Issue: Monitoring alerts not triggering

**Symptoms:** No alerts despite issues

**Causes:**
- Thresholds too lenient
- Not enough data in time window

**Solution:**
1. Adjust thresholds in `monitoring_alerts.py`
2. Reduce time window: `check_all_metrics(days=3)`
3. Run manually to test: `python backend/ml/monitoring_alerts.py`

### Issue: Bandit state not updating

**Symptoms:** Alpha/beta values stay at 1.0

**Causes:**
- Feedback not being tracked
- Context/algorithm not matching
- Database transaction issues

**Solution:**
1. Check logs for "Bandit success/failure" messages
2. Verify recommendation events have context field: 
   ```sql
   SELECT context, algorithm FROM recommendation_events LIMIT 5;
   ```
3. Test feedback tracking:
   ```bash
   curl -X POST "http://localhost:8000/analytics/track/thumbs-up" \
     -H "Content-Type: application/json" \
     -d '{"user_id": 1, "movie_id": 550}'
   ```

---

## 📈 Success Metrics

### Week 1 Goals
- [ ] Bandit table created and populated
- [ ] All 6 algorithms have some pulls
- [ ] Feedback loop working (alpha/beta changing)
- [ ] No critical monitoring alerts

### Week 2-4 Goals
- [ ] Clear algorithm preferences emerging
- [ ] CTR improving vs control group
- [ ] Context-specific patterns visible
- [ ] Diversity maintained (no single algo > 70%)

### Production Goals
- [ ] 15-25% CTR improvement over baseline
- [ ] Better ratings for recommended movies
- [ ] Reduced thumbs-down rate
- [ ] Maintained or improved diversity

---

## 🔐 Security Notes

1. **Bandit Stats Endpoint:** Currently requires authentication. Keep it that way.
2. **Monitoring Reports:** Contain system metrics. Don't expose publicly.
3. **Context Data:** May contain user behavior patterns. Handle per privacy policy.

---

## 📚 Additional Resources

- **Bandit Algorithm:** `docs/BANDIT_SELECTOR.md`
- **Continuous Learning:** `backend/CONTINUOUS_LEARNING.md`
- **Monitoring:** `backend/ml/monitoring_alerts.py`
- **A/B Testing Theory:** Thompson Sampling (Bayesian optimization)

---

## ✅ Post-Deployment Checklist

- [ ] Migration successful
- [ ] API restarted and healthy
- [ ] Recommendations endpoint responding
- [ ] Bandit stats accessible
- [ ] Feedback tracking working
- [ ] Monitoring scheduled (9 AM daily)
- [ ] Frontend updated for A/B split
- [ ] Dashboard/analytics configured
- [ ] Team trained on new features
- [ ] Monitoring alerts configured

---

## 🎉 You're Done!

The Thompson Sampling bandit is now live and learning from your users. 

**What happens next:**
1. Bandit explores all algorithms (uniform sampling)
2. Users interact with recommendations (feedback collected)
3. Bandit learns which algorithms work best in which contexts
4. System optimizes automatically
5. Performance improves week over week

**Monitor progress:**
- Daily monitoring reports at 9 AM
- Check bandit stats: `GET /analytics/bandit/stats`
- Compare A/B groups: `GET /analytics/performance`

**Need help?** Check logs for "Bandit" messages or review `BANDIT_SELECTOR.md`

---

**Deployment Date:** 2025-10-11  
**Version:** 1.0.0  
**Status:** ✅ Ready for Production

