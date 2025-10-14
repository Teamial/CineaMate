# Multi-Armed Bandit A/B Testing Runbook

## Overview

This runbook provides operational procedures for managing multi-armed bandit experiments, including rollout, monitoring, rollback, and troubleshooting.

## Table of Contents

1. [Pre-Launch Checklist](#pre-launch-checklist)
2. [Experiment Launch](#experiment-launch)
3. [Monitoring Procedures](#monitoring-procedures)
4. [Rollback Procedures](#rollback-procedures)
5. [Troubleshooting](#troubleshooting)
6. [Emergency Contacts](#emergency-contacts)

## Pre-Launch Checklist

### Database Preparation
- [ ] Run migrations: `python backend/migrate_add_bandit_experiment.py`
- [ ] Verify tables created: `psql -d movierecs -c "\dt"`
- [ ] Check database connectivity and performance
- [ ] Ensure sufficient disk space for experiment data

### System Health Checks
- [ ] Verify API endpoints are responding
- [ ] Check Redis cache connectivity (if enabled)
- [ ] Validate background workers are running
- [ ] Confirm scheduler jobs are active

### Configuration Review
- [ ] Review guardrail thresholds
- [ ] Verify decision criteria settings
- [ ] Check traffic allocation percentages
- [ ] Validate policy parameters

### Testing
- [ ] Run unit tests: `pytest backend/tests/test_policies.py`
- [ ] Run property tests: `pytest backend/tests/property_tests.py`
- [ ] Run integration tests: `pytest backend/tests/test_integration.py`
- [ ] Test offline replay with sample data

## Experiment Launch

### 1. Create Experiment

```bash
# Launch experiment via script
python scripts/launch_online_experiment.py \
  --name "Bandit Test v1" \
  --duration 14 \
  --traffic 0.8 \
  --policies "thompson,egreedy,ucb,control"

# Or create via API
curl -X POST "http://localhost:8000/api/experiments" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Bandit Test v1",
    "traffic_pct": 0.8,
    "default_policy": "thompson",
    "notes": "Production bandit experiment"
  }'
```

### 2. Verify Launch

```bash
# Check experiment status
curl "http://localhost:8000/api/experiments/{experiment_id}"

# Verify traffic allocation
curl "http://localhost:8000/api/experiments/{experiment_id}/summary"

# Check guardrails status
curl "http://localhost:8000/api/experiments/{experiment_id}/guardrails"
```

### 3. Monitor Initial Traffic

- [ ] Verify users are being assigned to policies
- [ ] Check recommendation requests are being logged
- [ ] Confirm reward calculations are working
- [ ] Monitor API response times

## Monitoring Procedures

### Real-Time Monitoring

#### Dashboard Monitoring
1. **Open Dashboard**: Navigate to `/experiments/{experiment_id}`
2. **Check Summary Cards**: Verify traffic split and user counts
3. **Monitor Reward Trends**: Watch cumulative reward curves
4. **Review Guardrails**: Ensure all checks are passing
5. **Check Latency**: Verify P95 < 120ms

#### Key Metrics to Watch
- **Traffic Split**: Should match configured percentages
- **Active Users**: Should be consistent with expected traffic
- **Reward Rate**: Monitor for significant drops
- **Latency**: P95 should remain < 120ms
- **Error Rate**: Should be < 1%

### Automated Monitoring

#### Guardrails (Every 5 minutes)
- Error rate < 1%
- P95 latency < 120ms
- No single arm > 50% traffic
- Reward not > 5% below control

#### Decision Engine (Daily at 9 AM)
- Statistical significance tests
- Ship/iterate/kill recommendations
- Performance trend analysis

### Alert Thresholds

| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| Error Rate | > 0.5% | > 1% | Check logs, consider rollback |
| P95 Latency | > 100ms | > 120ms | Check database, scale if needed |
| Reward Drop | > 3% | > 5% | Investigate policy behavior |
| Arm Concentration | > 40% | > 50% | Check policy learning |

## Rollback Procedures

### Automatic Rollback

The system will automatically rollback if:
- 2+ guardrails fail
- Critical guardrails (error rate, latency) fail
- Maximum rollback attempts exceeded

### Manual Rollback

#### 1. Immediate Rollback
```bash
# Stop experiment
curl -X POST "http://localhost:8000/api/experiments/{experiment_id}/stop"

# Verify rollback
curl "http://localhost:8000/api/experiments/{experiment_id}"
```

#### 2. Emergency Rollback
```bash
# Direct database rollback
python -c "
from backend.ml.guardrails import rollback_experiment
from backend.database import SessionLocal
rollback_experiment(SessionLocal(), '{experiment_id}')
"
```

#### 3. Verify Rollback
- [ ] Check experiment end_at timestamp
- [ ] Verify users revert to control policy
- [ ] Confirm no new recommendations served
- [ ] Monitor system stability

### Post-Rollback Actions

1. **Investigate Root Cause**
   - Review guardrail failure logs
   - Analyze policy behavior
   - Check system performance metrics

2. **Document Incident**
   - Record rollback reason
   - Note affected users
   - Document lessons learned

3. **Plan Next Steps**
   - Fix identified issues
   - Adjust guardrail thresholds if needed
   - Plan re-launch strategy

## Troubleshooting

### Common Issues

#### Policy Not Learning
**Symptoms**: Low reward rates, high regret
**Causes**: Insufficient exploration, reward calculation issues
**Solutions**:
- Check reward calculation logic
- Verify policy state updates
- Increase exploration time
- Review arm catalog

#### High Latency
**Symptoms**: P95 latency > 120ms
**Causes**: Database performance, cache misses
**Solutions**:
- Check database query performance
- Verify Redis cache hit rates
- Monitor policy selection time
- Scale database if needed

#### Guardrail Failures
**Symptoms**: Frequent guardrail alerts
**Causes**: Threshold misconfiguration, data quality issues
**Solutions**:
- Review threshold configurations
- Check for data quality issues
- Verify experiment traffic allocation
- Adjust thresholds if appropriate

#### Dashboard Not Loading
**Symptoms**: Dashboard components not rendering
**Causes**: API failures, authentication issues
**Solutions**:
- Check API endpoint availability
- Verify authentication and permissions
- Review browser console for errors
- Check network connectivity

### Debug Commands

#### Check Experiment Status
```bash
python -c "
from backend.ml.experiment_manager import ExperimentManager
from backend.database import SessionLocal
manager = ExperimentManager(SessionLocal())
print(manager.get_experiment_status('{experiment_id}'))
"
```

#### Test Policy Selection
```bash
python -c "
from backend.ml.policies import get_policy
from backend.database import SessionLocal
policy = get_policy('thompson', SessionLocal())
print(policy.select({}, ['arm1', 'arm2']))
"
```

#### Check Guardrails
```bash
python -c "
from backend.ml.guardrails import check_experiment_guardrails
from backend.database import SessionLocal
print(check_experiment_guardrails(SessionLocal(), '{experiment_id}'))
"
```

#### Analyze Policy Performance
```bash
python -c "
from backend.ml.decision_engine import analyze_experiment_decision
from backend.database import SessionLocal
print(analyze_experiment_decision(SessionLocal(), '{experiment_id}'))
"
```

### Log Analysis

#### Key Log Files
- **Application Logs**: `/var/log/movierecs/app.log`
- **Guardrail Logs**: `/var/log/movierecs/guardrails.log`
- **Worker Logs**: `/var/log/movierecs/workers.log`
- **API Logs**: `/var/log/movierecs/api.log`

#### Useful Log Queries
```bash
# Check guardrail failures
grep "GUARDRAIL FAIL" /var/log/movierecs/guardrails.log

# Monitor policy updates
grep "Policy.*updated" /var/log/movierecs/app.log

# Check reward calculations
grep "Reward.*computed" /var/log/movierecs/workers.log

# Monitor API errors
grep "ERROR" /var/log/movierecs/api.log
```

## Emergency Contacts

### On-Call Rotation
- **Primary**: Data Engineering Team Lead
- **Secondary**: ML Engineering Team Lead
- **Escalation**: Engineering Manager

### Contact Information
- **Slack**: #bandit-experiments
- **Email**: bandit-alerts@company.com
- **Phone**: +1-555-BANDIT-1

### Escalation Procedures
1. **Level 1**: On-call engineer (0-15 minutes)
2. **Level 2**: Team lead (15-30 minutes)
3. **Level 3**: Engineering manager (30+ minutes)

## Maintenance Procedures

### Daily Tasks
- [ ] Review experiment status
- [ ] Check guardrail health
- [ ] Monitor key metrics
- [ ] Review decision engine recommendations

### Weekly Tasks
- [ ] Analyze experiment performance
- [ ] Review guardrail thresholds
- [ ] Check system capacity
- [ ] Update documentation

### Monthly Tasks
- [ ] Performance review
- [ ] Capacity planning
- [ ] Security audit
- [ ] Disaster recovery test

## Appendix

### Configuration Files
- **Guardrails**: `backend/ml/guardrails.py`
- **Decision Engine**: `backend/ml/decision_engine.py`
- **Policies**: `backend/ml/policies/`
- **Dashboard**: `frontend/src/components/experiments/`

### Useful Scripts
- **Launch**: `scripts/launch_online_experiment.py`
- **Offline Replay**: `tools/offline_replay.py`
- **Evaluation**: `tools/offline_evaluator.py`
- **Data Loading**: `tools/load_movielens.py`

### External Dependencies
- **PostgreSQL**: Database
- **Redis**: Caching (optional)
- **FastAPI**: Backend framework
- **React**: Frontend framework

---

**Last Updated**: 2024-01-15
**Version**: 1.0
**Maintained By**: Data Engineering Team
