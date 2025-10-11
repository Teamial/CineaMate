<!-- 4ee8c472-6593-45fe-aff4-91bbd188f263 2f656aa2-eab5-47e0-8b9c-7b1bca32a1a9 -->
# ML Recommendation Algorithm Improvement

## Problem Statement

Current system prioritizes popular/safe recommendations over discovery. Advanced features (embeddings, graph, context-aware) are disabled. Need serendipitous recommendations with context-aware algorithm selection and real-time performance optimization.

## Solution Architecture

### 1. Diversity-First Recommendation Strategies

**Create new recommendation strategies** in `backend/ml/diversity_recommender.py`:

- **Long-tail discovery**: Boost movies with vote_count < 1000 but vote_average > 7.5
- **Niche genre emphasis**: Special handling for anime, foreign language, documentary
- **Serendipity scoring**: Recommend movies dissimilar to user's history but high-rated
- **Popularity dampening**: Apply logarithmic dampening to popularity scores
- **Coverage optimization**: Track recommended movie IDs, boost underrecommended content

Key metrics to optimize:

- **Gini coefficient** (lower = better diversity)
- **Coverage rate** (% of catalog recommended)
- **Novelty score** (avg popularity rank of recommendations)
- **Serendipity score** (avg dissimilarity to user profile)

### 2. Multi-Armed Bandit Algorithm Selector

**Create context-aware bandit** in `backend/ml/bandit_selector.py`:

Implement **Thompson Sampling** to select best algorithm per context:

Available algorithms ("arms"):

- SVD (matrix factorization)
- Embeddings (BERT + ResNet deep learning)
- Graph (knowledge graph)
- Item-based CF (collaborative filtering)
- Long-tail diversity
- Serendipity explorer

Context features:

- Time of day (morning/afternoon/evening/night)
- Day of week (weekday/weekend)
- User profile (cold-start/regular/power user)
- Recent genre saturation (prevent fatigue)
- Session position (early = exploitative, later = exploratory)

Bandit maintains **Beta distributions** for each (context, algorithm) pair:

- Track successes (clicks, ratings ≥4, thumbs up)
- Track failures (no click, ratings ≤2, thumbs down)
- Select algorithm by sampling from distributions
- Update distributions in real-time as feedback arrives

### 3. Comprehensive Evaluation Framework

**Create evaluation module** in `backend/ml/evaluator.py`:

**Offline Metrics** (train/test split):

- **Accuracy**: RMSE, MAE, Precision@K, Recall@K
- **Ranking**: NDCG, MRR
- **Diversity**: Intra-list diversity, coverage
- **Novelty**: Avg popularity rank, long-tail %
- **Serendipity**: Unexpected relevant items

**Online Metrics** (live traffic):

- **Engagement**: CTR, rating rate, thumbs up/down ratio
- **Quality**: Avg rating of clicked items
- **Discovery**: % anime/niche genre clicks
- **Session**: Time on site, recommendations per session
- **Business**: Conversion rate, retention

Implement **cross-validation** and **temporal validation** (train on past, test on future).

### 4. A/B Testing Infrastructure

**Enhance RecommendationEvent model** to support experiments:

Add to `backend/models.py`:

```python
class RecommendationEvent:
    experiment_id = Column(String(50))  # A/B test identifier
    variant = Column(String(50))  # control/variant_a/variant_b
    bandit_context = Column(JSON)  # Context at selection time
    algorithm_confidence = Column(Float)  # Bandit's confidence score
```

**Create experiment manager** in `backend/ml/experiment_manager.py`:

- Configure experiments (% traffic split, variants)
- Random assignment with consistent hashing (user_id → variant)
- Track per-variant performance
- Statistical significance testing (chi-square, t-test)
- Early stopping rules (if variant clearly wins/loses)

### 5. Real-Time Monitoring Dashboard

**Extend analytics endpoints** in `backend/routes/analytics.py`:

New endpoints:

- `GET /analytics/diversity-metrics`: Gini, coverage, novelty, serendipity
- `GET /analytics/algorithm-performance`: Per-algorithm CTR, avg rating, confidence intervals
- `GET /analytics/bandit-state`: Current bandit parameters, arm selection rates
- `GET /analytics/experiments`: Active A/B tests, statistical significance
- `GET /analytics/long-tail-coverage`: Anime/niche genre recommendation rates

**Real-time dashboards** tracking:

- Algorithm selection frequency over time
- Context-specific performance (time of day, user type)
- Diversity trends (are we recommending more niche content?)
- Bandit exploration vs exploitation ratio

### 6. Model Training & Deployment Pipeline

**Create training pipeline** in `backend/ml/training_pipeline.py`:

**Step 1: Data preparation**

- Extract user-item interactions (ratings, clicks, thumbs)
- Train/validation/test split (70/15/15 or temporal)
- Feature engineering (user profile, movie attributes, context)

**Step 2: Model training**

- Train each recommendation algorithm on training set
- Hyperparameter tuning with validation set
- Generate embeddings for all movies (if not exists)

**Step 3: Evaluation**

- Compute offline metrics on test set
- Save metrics to `ModelUpdateLog` table
- Compare against baseline/previous version

**Step 4: Deployment**

- If metrics improve, deploy new model
- Gradual rollout (10% → 50% → 100% traffic)
- Monitor online metrics for degradation
- Rollback mechanism if performance drops

**Step 5: Continuous learning**

- Incremental updates every N hours (e.g., 6 hours)
- Warm-start from previous model
- Process only new ratings since last update
- Log update metrics for monitoring

## Implementation Files

### New Files to Create:

1. **`backend/ml/diversity_recommender.py`** (300 lines)

   - Long-tail discovery algorithm
   - Serendipity scorer
   - Niche genre boosting
   - Coverage tracker

2. **`backend/ml/bandit_selector.py`** (250 lines)

   - Thompson Sampling implementation
   - Context feature extraction
   - Arm selection logic
   - Real-time parameter updates

3. **`backend/ml/evaluator.py`** (400 lines)

   - Offline evaluation metrics
   - Online metrics aggregation
   - Cross-validation framework
   - Diversity/novelty/serendipity metrics

4. **`backend/ml/experiment_manager.py`** (200 lines)

   - A/B test configuration
   - Variant assignment
   - Statistical significance testing
   - Early stopping logic

5. **`backend/ml/training_pipeline.py`** (500 lines)

   - Data preparation
   - Model training orchestration
   - Evaluation and deployment
   - Continuous learning scheduler

6. **`backend/migrate_add_bandit_fields.py`** (50 lines)

   - Add experiment_id, variant, bandit_context to RecommendationEvent
   - Add BanditState table for persisting bandit parameters

### Files to Modify:

1. **`backend/models.py`**

   - Add experiment fields to RecommendationEvent
   - Add BanditState model

2. **`backend/ml/recommender.py`**

   - Integrate bandit selector into `get_hybrid_recommendations()`
   - Add diversity post-processing
   - Enable embeddings and graph by default

3. **`backend/routes/movies.py`**

   - Use bandit selector for algorithm choice
   - Track experiment variant
   - Add diversity parameter

4. **`backend/routes/analytics.py`**

   - Add diversity metrics endpoints
   - Add bandit state endpoints
   - Add A/B test results endpoints

5. **`backend/scheduler.py`** (if exists, else create)

   - Schedule model retraining every 6 hours
   - Schedule bandit parameter persistence

## Key Algorithm Changes

### Current (Line 99-105 in `backend/routes/movies.py`):

```python
recommendations = recommender.get_hybrid_recommendations(
    user_id, pool_size, 
    use_context=False,
    use_embeddings=False,
    use_graph=False
)
```

### Proposed:

```python
# Extract context features
context = bandit_selector.extract_context(user_id, session_data)

# Select best algorithm for this context
selected_algorithms, confidences = bandit_selector.select_arms(
    context, n_arms=3
)

# Generate recommendations with selected algorithms
recommendations = recommender.get_contextual_recommendations(
    user_id=user_id,
    algorithms=selected_algorithms,
    weights=confidences,
    diversity_weight=0.3,  # 30% boost for long-tail
    n_recommendations=pool_size
)

# Track for A/B testing
experiment_id, variant = experiment_manager.assign_variant(user_id)
```

## Deployment Strategy

### Phase 1: Foundation (Weeks 1-2)

- Build diversity recommender
- Implement evaluation framework
- Create training pipeline
- Run offline evaluation to establish baseline

### Phase 2: Bandit Integration (Week 3)

- Implement Thompson Sampling bandit
- Integrate with recommendation endpoint
- Enable real-time feedback loop
- Monitor arm selection rates

### Phase 3: A/B Testing (Week 4)

- Deploy experiment framework
- Run first A/B test: baseline vs bandit
- Analyze statistical significance
- Iterate based on results

### Phase 4: Continuous Improvement (Ongoing)

- Schedule automated retraining
- Monitor diversity metrics
- Tune bandit exploration rate
- Expand to more algorithms/contexts

## Success Metrics

### Primary Goals:

- **Diversity**: 40% increase in long-tail recommendation rate (vote_count < 1000)
- **Discovery**: 3x increase in anime/niche genre clicks
- **Quality**: Maintain avg rating ≥ 4.0 for clicked recommendations
- **Engagement**: 20% increase in CTR

### Secondary Goals:

- **Coverage**: Recommend 80%+ of catalog over time
- **Serendipity**: 50%+ of clicks on movies dissimilar to user history
- **Context awareness**: 15%+ better performance with bandit vs static weighting
- **Model freshness**: Successful retraining every 6 hours with <5% performance variance

## Monitoring & Alerts

Set up alerts for:

- **Diversity drop**: If long-tail recommendation rate drops below baseline
- **Quality degradation**: If avg rating of clicked items < 3.5
- **Bandit imbalance**: If one arm dominates >70% of selections
- **Model training failure**: If pipeline fails or metrics degrade >10%
- **A/B test significance**: When p-value < 0.05 for key metrics

## Rollback Plan

If any metric degrades >15%:

1. Immediate rollback to previous algorithm weights
2. Disable bandit, use static weights
3. Investigate failure in logs
4. Fix and re-test offline before re-deployment

## Documentation

Create comprehensive docs:

- `docs/DIVERSITY_ALGORITHM.md`: Long-tail discovery strategy
- `docs/BANDIT_SELECTOR.md`: Thompson Sampling explanation
- `docs/EVALUATION_FRAMEWORK.md`: Metrics definitions and interpretation
- `docs/AB_TESTING_GUIDE.md`: How to run experiments
- `docs/TRAINING_PIPELINE.md`: Model training and deployment process

### To-dos

- [ ] Create diversity_recommender.py with long-tail discovery, serendipity scoring, niche genre boosting, and coverage tracking
- [ ] Build evaluator.py with offline metrics (RMSE, Precision@K, diversity, novelty) and online metrics (CTR, quality)
- [ ] Implement bandit_selector.py with Thompson Sampling for context-aware algorithm selection
- [ ] Add experiment fields (experiment_id, variant, bandit_context) to RecommendationEvent and create BanditState table
- [ ] Create training_pipeline.py for data prep, model training, evaluation, deployment, and continuous learning
- [ ] Build experiment_manager.py for A/B test configuration, variant assignment, and statistical testing
- [ ] Integrate bandit selector into recommender.py and movies.py endpoint, enable embeddings/graph by default
- [ ] Add diversity metrics, bandit state, and A/B test results endpoints to analytics.py
- [ ] Create/update scheduler.py for automated model retraining every 6 hours and bandit parameter persistence
- [ ] Run offline evaluation to establish baseline metrics for current algorithm
- [ ] Deploy first A/B test comparing baseline vs bandit-optimized recommendations
- [ ] Set up monitoring and alerts for diversity, quality, bandit balance, and training failures
- [ ] Create comprehensive documentation for diversity algorithm, bandit selector, evaluation, A/B testing, and training pipeline