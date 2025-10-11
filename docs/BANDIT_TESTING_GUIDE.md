# Bandit Selector Testing Guide

## 🧪 Complete Test Plan for Thompson Sampling Bandit Integration

This guide provides comprehensive testing procedures to verify the bandit selector implementation before and after deployment.

---

## ✅ Pre-Deployment Tests (Before Migration)

### 1. Code Validation

All code has been validated and shows **no linter errors**:
- ✅ `backend/models.py` - BanditState model
- ✅ `backend/ml/bandit_selector.py` - Thompson Sampling implementation
- ✅ `backend/ml/recommender.py` - Bandit recommendations
- ✅ `backend/routes/movies.py` - Recommendation endpoint
- ✅ `backend/routes/analytics.py` - Feedback tracking

### 2. Import Validation

Activate your virtual environment and test imports:

```bash
source venv/bin/activate
python3 -c "from backend.models import BanditState; print('✓ BanditState model OK')"
python3 -c "from backend.ml.bandit_selector import BanditSelector; print('✓ BanditSelector OK')"
python3 -c "import numpy; print('✓ NumPy OK')"
```

Expected output:
```
✓ BanditState model OK
✓ BanditSelector OK
✓ NumPy OK
```

---

## 📋 Post-Migration Tests (After Database Setup)

### Test 1: Database Migration

**Run migration:**
```bash
cd /Users/tea/Documents/Passion-Projects/movie_recommender
source venv/bin/activate
python3 backend/migrate_add_bandit_states.py
```

**Verify table creation:**
```bash
# Connect to database
psql $DATABASE_URL

# Check table structure
\d bandit_states

# Expected columns:
# - id (integer, primary key)
# - context_key (varchar(200))
# - algorithm (varchar(50))
# - alpha (float)
# - beta (float)
# - total_pulls (integer)
# - total_successes (integer)
# - total_failures (integer)
# - created_at (timestamp)
# - updated_at (timestamp)

# Check indexes
\di | grep bandit

# Expected indexes:
# - idx_bandit_context
# - idx_bandit_algo
# - idx_bandit_context_algo (unique)

\q
```

**Pass criteria:** ✅ Table created with all columns and indexes

---

### Test 2: Bandit Selector Initialization

**Test script:**
```python
from backend.database import SessionLocal
from backend.ml.bandit_selector import BanditSelector

db = SessionLocal()
try:
    # Initialize bandit
    bandit = BanditSelector(db)
    print(f"✓ Bandit initialized with {len(bandit.algorithms)} algorithms")
    
    # Test context extraction
    context = bandit.extract_context(user_id=1)
    print(f"✓ Context extracted: {context}")
    
    # Test arm selection
    algorithms, confidences = bandit.select_arms(context, n_arms=3)
    print(f"✓ Selected arms: {list(zip(algorithms, confidences))}")
    
    # Verify confidences sum to 1
    assert abs(sum(confidences) - 1.0) < 0.01, "Confidences don't sum to 1"
    print("✓ Confidences normalized correctly")
    
    print("\n✅ All bandit selector tests passed!")
    
finally:
    db.close()
```

**Pass criteria:** 
- ✅ Bandit initializes with 6 algorithms
- ✅ Context extraction returns valid dict
- ✅ Arm selection returns 3 algorithms with normalized confidences

---

### Test 3: Bandit State Persistence

**Test script:**
```python
from backend.database import SessionLocal
from backend.ml.bandit_selector import BanditSelector
from backend.models import BanditState

db = SessionLocal()
try:
    bandit = BanditSelector(db)
    
    # Create test context
    test_context = {
        'time_period': 'evening',
        'day_of_week': 'weekend',
        'user_type': 'regular',
        'genre_saturation': 'low',
        'session_position': 'middle'
    }
    
    # Select arms (this should create states)
    algorithms, _ = bandit.select_arms(test_context, n_arms=3)
    print(f"✓ Selected: {algorithms}")
    
    # Verify states created in database
    context_key = bandit._context_to_key(test_context)
    states = db.query(BanditState).filter(
        BanditState.context_key == context_key
    ).all()
    
    print(f"✓ Created {len(states)} bandit states")
    assert len(states) == 6, f"Expected 6 states, got {len(states)}"
    
    # Test updating a state
    bandit.update_bandit(test_context, algorithms[0], 'success')
    
    # Verify update
    updated_state = db.query(BanditState).filter(
        BanditState.context_key == context_key,
        BanditState.algorithm == algorithms[0]
    ).first()
    
    assert updated_state.alpha == 2.0, f"Alpha should be 2.0, got {updated_state.alpha}"
    assert updated_state.total_successes == 1, "Success count should be 1"
    print(f"✓ State updated: α={updated_state.alpha}, β={updated_state.beta}")
    
    print("\n✅ All persistence tests passed!")
    
finally:
    db.close()
```

**Pass criteria:**
- ✅ States created in database for all algorithms
- ✅ Update_bandit successfully modifies alpha/beta
- ✅ Statistics correctly tracked

---

### Test 4: Recommendation Endpoint Integration

**Prerequisite:** API server must be running

**Start server:**
```bash
cd /Users/tea/Documents/Passion-Projects/movie_recommender
source venv/bin/activate
uvicorn backend.main:app --reload
```

**Test bandit recommendations:**

```bash
# Get auth token first (login)
TOKEN=$(curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=testuser&password=testpass" \
  | jq -r '.access_token')

# Test bandit recommendations (treatment group)
curl -X GET "http://localhost:8000/movies/recommendations?user_id=1&limit=5&use_bandit=true" \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.[0:2]'  # Show first 2 movies

# Test control recommendations
curl -X GET "http://localhost:8000/movies/recommendations?user_id=1&limit=5&use_bandit=false" \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.[0:2]'  # Show first 2 movies
```

**Verify in database:**
```sql
-- Check recommendation events
SELECT algorithm, COUNT(*) 
FROM recommendation_events 
WHERE created_at > NOW() - INTERVAL '5 minutes'
GROUP BY algorithm;

-- Should see entries like:
-- bandit_svd | 3
-- bandit_embeddings | 2
-- hybrid_control | 5
```

**Pass criteria:**
- ✅ Both endpoints return valid recommendations
- ✅ Bandit endpoint uses "bandit_*" algorithm names
- ✅ Control endpoint uses "hybrid_control"
- ✅ Recommendations tracked in database

---

### Test 5: Feedback Loop

**Test click tracking:**
```bash
# Track a click
curl -X POST "http://localhost:8000/analytics/track/click" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"user_id": 1, "movie_id": 550}'

# Response: {"status": "tracked", "action": "click"}
```

**Test rating tracking:**
```bash
# High rating (success)
curl -X POST "http://localhost:8000/analytics/track/rating" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"user_id": 1, "movie_id": 550, "rating": 4.5}'

# Low rating (failure)
curl -X POST "http://localhost:8000/analytics/track/rating" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"user_id": 1, "movie_id": 551, "rating": 1.5}'
```

**Test thumbs tracking:**
```bash
# Thumbs up (success)
curl -X POST "http://localhost:8000/analytics/track/thumbs-up" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"user_id": 1, "movie_id": 552}'

# Thumbs down (failure)
curl -X POST "http://localhost:8000/analytics/track/thumbs-down" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"user_id": 1, "movie_id": 553}'
```

**Verify bandit updates:**
```sql
-- Check bandit states have been updated
SELECT 
    algorithm,
    alpha,
    beta,
    total_pulls,
    total_successes,
    total_failures
FROM bandit_states
WHERE alpha > 1.0 OR beta > 1.0
ORDER BY algorithm;

-- Should see some algorithms with alpha > 1 (successes) or beta > 1 (failures)
```

**Pass criteria:**
- ✅ All tracking endpoints return success
- ✅ Bandit states alpha/beta values increase
- ✅ Successes/failures counted correctly

---

### Test 6: Analytics Endpoints

**Test bandit stats:**
```bash
curl -X GET "http://localhost:8000/analytics/bandit/stats" \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.summary'

# Expected output structure:
# {
#   "total_contexts": 2,
#   "total_pulls": 15,
#   "total_successes": 8,
#   "total_failures": 3,
#   "overall_success_rate": 0.727
# }
```

**Test algorithm performance:**
```bash
curl -X GET "http://localhost:8000/analytics/performance?days=1" \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.algorithms | keys'

# Should include both bandit_* and hybrid_control algorithms
```

**Pass criteria:**
- ✅ Bandit stats endpoint returns valid data
- ✅ Algorithm performance distinguishes treatment vs control
- ✅ Metrics calculated correctly

---

### Test 7: Monitoring System

**Run monitoring check:**
```bash
cd /Users/tea/Documents/Passion-Projects/movie_recommender
source venv/bin/activate
python3 backend/ml/monitoring_alerts.py
```

**Expected output:**
```
============================================================
RECOMMENDATION SYSTEM MONITORING REPORT
============================================================

Timestamp: 2025-10-11T...
Period: Last 7 days
Overall Status: HEALTHY (or WARNING/CRITICAL)

📊 Health Checks:

✅ Diversity: OK
   Metrics: [diversity metrics]

✅ Quality: OK
   Metrics: [quality metrics]

✅ Algorithm Balance: OK

✅ Engagement: OK

[Alerts section if any]

============================================================
```

**Verify report saved:**
```bash
cat monitoring_report.json | jq '.overall_status'
```

**Pass criteria:**
- ✅ Monitoring runs without errors
- ✅ All health checks complete
- ✅ Report JSON saved
- ✅ Alerts shown if thresholds breached

---

### Test 8: Scheduler Integration

**Test monitoring job added:**
```python
from backend.scheduler import get_scheduler

scheduler = get_scheduler()
jobs = scheduler.get_job_status()

monitoring_job = [j for j in jobs if j['id'] == 'daily_monitoring']
assert len(monitoring_job) == 1, "Monitoring job not found"

print(f"✓ Monitoring job scheduled: {monitoring_job[0]['next_run']}")
print(f"✓ Total jobs: {len(jobs)}")

print("\n✅ Scheduler integration test passed!")
```

**Pass criteria:**
- ✅ Monitoring job exists in scheduler
- ✅ Job scheduled for 9:00 AM daily
- ✅ No scheduler errors

---

## 🎯 Integration Test Scenarios

### Scenario 1: New User Journey

**Steps:**
1. New user signs up
2. Completes onboarding
3. Gets recommendations (cold start)
4. Clicks on 2 movies
5. Rates 1 movie highly (4.5 stars)
6. Gets more recommendations

**Verification:**
```sql
-- Check user got bandit recommendations
SELECT COUNT(*) FROM recommendation_events 
WHERE user_id = [new_user_id] 
  AND algorithm LIKE 'bandit_%';

-- Check bandit learned from feedback
SELECT algorithm, alpha, beta 
FROM bandit_states 
WHERE context_key IN (
  SELECT DISTINCT context->>'context_key' 
  FROM recommendation_events 
  WHERE user_id = [new_user_id]
);
```

**Pass criteria:**
- ✅ User receives recommendations
- ✅ Clicks and ratings tracked
- ✅ Bandit states updated
- ✅ Subsequent recommendations adapt

---

### Scenario 2: A/B Test Split

**Steps:**
1. Create 10 test users
2. Assign users 1, 3, 5, 7, 9 to bandit (use_bandit=true)
3. Assign users 2, 4, 6, 8, 10 to control (use_bandit=false)
4. Each user gets 20 recommendations
5. Track all interactions

**Verification:**
```sql
-- Compare A/B groups
SELECT 
    CASE 
        WHEN algorithm LIKE 'bandit_%' THEN 'treatment'
        WHEN algorithm = 'hybrid_control' THEN 'control'
    END as group,
    COUNT(*) as recommendations,
    COUNT(DISTINCT user_id) as users
FROM recommendation_events
WHERE user_id IN (1,2,3,4,5,6,7,8,9,10)
GROUP BY group;

-- Should show:
-- treatment | 100 | 5
-- control   | 100 | 5
```

**Pass criteria:**
- ✅ Groups properly split
- ✅ Correct algorithms assigned
- ✅ Equal representation

---

### Scenario 3: Context-Specific Learning

**Steps:**
1. Generate recommendations in different contexts:
   - Morning, weekday, cold start user
   - Evening, weekend, power user
   - Afternoon, weekday, regular user
2. Provide positive feedback for specific algorithm in each context
3. Get recommendations again in same contexts

**Verification:**
```sql
-- Check context-specific learning
SELECT 
    context->>'time_period' as time,
    context->>'day_of_week' as day,
    context->>'user_type' as user_type,
    algorithm,
    alpha,
    beta,
    alpha / (alpha + beta) as success_rate
FROM bandit_states bs
JOIN recommendation_events re ON 
    bs.context_key = re.context->>'context_key'
WHERE alpha > 1.0 OR beta > 1.0
ORDER BY time, day, user_type, success_rate DESC;
```

**Pass criteria:**
- ✅ Different contexts have different state distributions
- ✅ Algorithms with positive feedback show higher alpha
- ✅ Context-specific patterns emerge

---

## 📊 Performance Benchmarks

### Baseline Metrics (Pre-Bandit)

Collect these metrics BEFORE enabling bandit:
- [ ] Average CTR: ____%
- [ ] Average rating: ____
- [ ] Thumbs up/down ratio: ____
- [ ] Diversity score: ____
- [ ] Session length: ____ mins

### Target Improvements (Post-Bandit)

After 2-4 weeks of learning:
- [ ] CTR increase: +15-25%
- [ ] Rating improvement: +0.2-0.5 stars
- [ ] Thumbs up increase: +10-20%
- [ ] Diversity maintained: ±5%
- [ ] Session length increase: +10-15%

---

## 🚨 Known Issues & Troubleshooting

### Issue: Import errors during testing
**Cause:** Virtual environment not activated  
**Fix:** `source venv/bin/activate`

### Issue: Database connection errors
**Cause:** DATABASE_URL not set  
**Fix:** Load from .env: `export $(cat .env | grep DATABASE_URL | xargs)`

### Issue: No bandit updates
**Cause:** Context not saved in recommendation events  
**Fix:** Verify `context` field populated in recommendation tracking

### Issue: All algorithms selected equally
**Cause:** Not enough data yet (expected initially)  
**Fix:** Wait for more feedback, bandit explores first then exploits

---

## ✅ Final Checklist

Before marking deployment complete:

**Code Quality:**
- [x] No linter errors
- [x] All imports working
- [x] Type hints correct

**Database:**
- [ ] Migration successful
- [ ] Table created with indexes
- [ ] Can query bandit_states

**Functionality:**
- [ ] Bandit selector initializes
- [ ] Context extraction works
- [ ] Arm selection works
- [ ] State persistence works
- [ ] Updates propagate

**API Endpoints:**
- [ ] Recommendations endpoint (bandit mode)
- [ ] Recommendations endpoint (control mode)
- [ ] Click tracking
- [ ] Rating tracking
- [ ] Thumbs tracking
- [ ] Bandit stats endpoint

**Monitoring:**
- [ ] Monitoring script runs
- [ ] Reports generated
- [ ] Scheduler configured
- [ ] Alerts working

**Documentation:**
- [x] Deployment guide complete
- [x] Testing guide complete
- [x] Troubleshooting documented

---

## 🎉 Success Criteria

The system is ready for production when:
1. ✅ All tests in this document pass
2. ✅ No critical errors in monitoring
3. ✅ Bandit learns from feedback (alpha/beta changing)
4. ✅ A/B groups properly differentiated
5. ✅ Performance metrics tracked
6. ✅ Team trained on new features

---

**Testing Date:** 2025-10-11  
**Version:** 1.0.0  
**Status:** Ready for Testing  
**Next Review:** After 1 week of production data

