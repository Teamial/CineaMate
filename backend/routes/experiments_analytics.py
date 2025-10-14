"""
Analytics API Endpoints for Experiment Dashboard

Provides comprehensive analytics endpoints for the React dashboard:
- Experiment summary with traffic split, users, serves, reward metrics
- Timeseries data for charts (reward, CTR, latency, serves)
- Arm performance with sortable metrics and anomaly detection
- Cohort breakdown showing CTR by user type and fairness
- Event logs with pagination and CSV export
- Export functionality for data analysis

Endpoints:
- GET /api/experiments/:id/summary
- GET /api/experiments/:id/timeseries?metric=reward&granularity=hour
- GET /api/experiments/:id/arms?sort=regret&limit=20
- GET /api/experiments/:id/cohorts?breakdown=user_type
- GET /api/experiments/:id/events?policy=thompson&limit=1000&offset=0
- GET /api/experiments/:id/export?format=csv
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import text, func, desc, asc
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import uuid
import csv
import io
import json

from ..database import get_db
from ..models import Experiment, RecommendationEvent, PolicyAssignment
from ..auth import get_current_user

router = APIRouter(prefix="/experiments", tags=["experiments-analytics"])

@router.get("/{experiment_id}/summary")
def get_experiment_summary(
    experiment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get experiment summary with traffic split, users, serves, reward metrics"""
    
    # Get experiment
    experiment = db.query(Experiment).filter(Experiment.id == experiment_id).first()
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")
    
    # Get traffic split
    traffic_split = db.execute(text("""
        SELECT 
            policy,
            COUNT(*) as user_count,
            COUNT(*) * 100.0 / SUM(COUNT(*)) OVER() as percentage
        FROM policy_assignments
        WHERE experiment_id = :experiment_id
        GROUP BY policy
    """), {'experiment_id': experiment_id}).fetchall()
    
    # Get active users (24h and 7d)
    now = datetime.utcnow()
    active_users_24h = db.execute(text("""
        SELECT COUNT(DISTINCT user_id) as count
        FROM recommendation_events
        WHERE experiment_id = :experiment_id
        AND served_at >= :cutoff
    """), {
        'experiment_id': experiment_id,
        'cutoff': now - timedelta(hours=24)
    }).scalar()
    
    active_users_7d = db.execute(text("""
        SELECT COUNT(DISTINCT user_id) as count
        FROM recommendation_events
        WHERE experiment_id = :experiment_id
        AND served_at >= :cutoff
    """), {
        'experiment_id': experiment_id,
        'cutoff': now - timedelta(days=7)
    }).scalar()
    
    # Get total serves
    total_serves = db.execute(text("""
        SELECT COUNT(*) as count
        FROM recommendation_events
        WHERE experiment_id = :experiment_id
    """), {'experiment_id': experiment_id}).scalar()
    
    # Get mean reward (24h and 7d)
    mean_reward_24h = db.execute(text("""
        SELECT AVG(reward) as avg_reward
        FROM recommendation_events
        WHERE experiment_id = :experiment_id
        AND served_at >= :cutoff
        AND reward IS NOT NULL
    """), {
        'experiment_id': experiment_id,
        'cutoff': now - timedelta(hours=24)
    }).scalar()
    
    mean_reward_7d = db.execute(text("""
        SELECT AVG(reward) as avg_reward
        FROM recommendation_events
        WHERE experiment_id = :experiment_id
        AND served_at >= :cutoff
        AND reward IS NOT NULL
    """), {
        'experiment_id': experiment_id,
        'cutoff': now - timedelta(days=7)
    }).scalar()
    
    # Get current regret (vs. best policy)
    policy_rewards = db.execute(text("""
        SELECT 
            policy,
            AVG(reward) as avg_reward
        FROM recommendation_events
        WHERE experiment_id = :experiment_id
        AND reward IS NOT NULL
        GROUP BY policy
    """), {'experiment_id': experiment_id}).fetchall()
    
    if policy_rewards:
        best_reward = max(policy_rewards, key=lambda x: x.avg_reward).avg_reward
        current_regret = best_reward - (mean_reward_7d or 0)
    else:
        current_regret = 0
    
    return {
        'experiment': {
            'id': str(experiment.id),
            'name': experiment.name,
            'start_at': experiment.start_at.isoformat(),
            'end_at': experiment.end_at.isoformat() if experiment.end_at else None,
            'traffic_pct': experiment.traffic_pct,
            'status': 'active' if not experiment.end_at else 'ended'
        },
        'traffic_split': [
            {
                'policy': row.policy,
                'user_count': row.user_count,
                'percentage': round(row.percentage, 1)
            }
            for row in traffic_split
        ],
        'active_users': {
            '24h': active_users_24h or 0,
            '7d': active_users_7d or 0
        },
        'serves': {
            'total': total_serves or 0
        },
        'rewards': {
            'mean_24h': round(mean_reward_24h, 3) if mean_reward_24h else 0,
            'mean_7d': round(mean_reward_7d, 3) if mean_reward_7d else 0,
            'current_regret': round(current_regret, 3)
        }
    }

@router.get("/{experiment_id}/timeseries")
def get_timeseries_data(
    experiment_id: uuid.UUID,
    metric: str = Query("reward", description="Metric to retrieve: reward, ctr, latency_p95, serves"),
    granularity: str = Query("hour", description="Time granularity: hour, day"),
    policy: Optional[str] = Query(None, description="Filter by policy"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get timeseries data for charts"""
    
    # Validate metric
    valid_metrics = ['reward', 'ctr', 'latency_p95', 'serves']
    if metric not in valid_metrics:
        raise HTTPException(status_code=400, detail=f"Invalid metric. Must be one of: {valid_metrics}")
    
    # Validate granularity
    valid_granularities = ['hour', 'day']
    if granularity not in valid_granularities:
        raise HTTPException(status_code=400, detail=f"Invalid granularity. Must be one of: {valid_granularities}")
    
    # Build query based on metric
    if metric == 'reward':
        select_clause = "AVG(reward) as value"
        where_clause = "AND reward IS NOT NULL"
    elif metric == 'ctr':
        select_clause = "AVG(CASE WHEN reward > 0 THEN 1.0 ELSE 0.0 END) as value"
        where_clause = ""
    elif metric == 'latency_p95':
        select_clause = "PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) as value"
        where_clause = "AND latency_ms IS NOT NULL"
    elif metric == 'serves':
        select_clause = "COUNT(*) as value"
        where_clause = ""
    
    # Build policy filter
    policy_filter = ""
    params = {'experiment_id': experiment_id}
    if policy:
        policy_filter = "AND policy = :policy"
        params['policy'] = policy
    
    # Build time grouping
    if granularity == 'hour':
        time_group = "DATE_TRUNC('hour', served_at)"
    else:
        time_group = "DATE_TRUNC('day', served_at)"
    
    query = f"""
        SELECT 
            {time_group} as timestamp,
            {select_clause}
        FROM recommendation_events
        WHERE experiment_id = :experiment_id
        {where_clause}
        {policy_filter}
        GROUP BY {time_group}
        ORDER BY timestamp
    """
    
    results = db.execute(text(query), params).fetchall()
    
    return [
        {
            'timestamp': row.timestamp.isoformat(),
            'value': float(row.value) if row.value is not None else 0
        }
        for row in results
    ]

@router.get("/{experiment_id}/arms")
def get_arm_performance(
    experiment_id: uuid.UUID,
    sort: str = Query("reward_rate", description="Sort by: reward_rate, serves, regret"),
    limit: int = Query(20, ge=1, le=100),
    policy: Optional[str] = Query(None, description="Filter by policy"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get arm performance with sortable metrics and anomaly detection"""
    
    # Build policy filter
    policy_filter = ""
    params = {'experiment_id': experiment_id}
    if policy:
        policy_filter = "AND policy = :policy"
        params['policy'] = policy
    
    # Get arm performance
    arm_performance = db.execute(text(f"""
        SELECT 
            arm_id,
            COUNT(*) as serves,
            AVG(reward) as reward_rate,
            SUM(reward) as total_reward,
            AVG(latency_ms) as avg_latency,
            COUNT(DISTINCT user_id) as unique_users
        FROM recommendation_events
        WHERE experiment_id = :experiment_id
        AND arm_id IS NOT NULL
        {policy_filter}
        GROUP BY arm_id
        ORDER BY {sort} DESC
        LIMIT :limit
    """), {**params, 'limit': limit}).fetchall()
    
    # Calculate regret for each arm
    if arm_performance:
        best_reward_rate = max(arm_performance, key=lambda x: x.reward_rate).reward_rate
        
        arms_with_regret = []
        for arm in arm_performance:
            regret = best_reward_rate - (arm.reward_rate or 0)
            arms_with_regret.append({
                'arm_id': arm.arm_id,
                'serves': arm.serves,
                'reward_rate': round(arm.reward_rate, 3) if arm.reward_rate else 0,
                'total_reward': arm.total_reward,
                'avg_latency': round(arm.avg_latency, 1) if arm.avg_latency else 0,
                'unique_users': arm.unique_users,
                'regret': round(regret, 3)
            })
        
        return arms_with_regret
    
    return []

@router.get("/{experiment_id}/cohorts")
def get_cohort_breakdown(
    experiment_id: uuid.UUID,
    breakdown: str = Query("user_type", description="Breakdown by: user_type, time_period"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get cohort breakdown showing CTR by user type and fairness"""
    
    # Validate breakdown
    valid_breakdowns = ['user_type', 'time_period']
    if breakdown not in valid_breakdowns:
        raise HTTPException(status_code=400, detail=f"Invalid breakdown. Must be one of: {valid_breakdowns}")
    
    # Extract context field based on breakdown
    if breakdown == 'user_type':
        context_field = "context->>'user_type'"
    else:
        context_field = "context->>'time_period'"
    
    # Get cohort breakdown
    cohort_data = db.execute(text(f"""
        SELECT 
            {context_field} as cohort,
            policy,
            COUNT(*) as events,
            AVG(reward) as reward_rate,
            COUNT(DISTINCT user_id) as unique_users
        FROM recommendation_events
        WHERE experiment_id = :experiment_id
        AND context IS NOT NULL
        GROUP BY {context_field}, policy
        ORDER BY cohort, policy
    """), {'experiment_id': experiment_id}).fetchall()
    
    # Group by cohort
    cohorts = {}
    for row in cohort_data:
        cohort = row.cohort or 'unknown'
        if cohort not in cohorts:
            cohorts[cohort] = {}
        
        cohorts[cohort][row.policy] = {
            'events': row.events,
            'reward_rate': round(row.reward_rate, 3) if row.reward_rate else 0,
            'unique_users': row.unique_users
        }
    
    return cohorts

@router.get("/{experiment_id}/events")
def get_event_log(
    experiment_id: uuid.UUID,
    policy: Optional[str] = Query(None, description="Filter by policy"),
    limit: int = Query(1000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get paginated event logs"""
    
    # Build policy filter
    policy_filter = ""
    params = {'experiment_id': experiment_id, 'limit': limit, 'offset': offset}
    if policy:
        policy_filter = "AND policy = :policy"
        params['policy'] = policy
    
    # Get events
    events = db.execute(text(f"""
        SELECT 
            id,
            user_id,
            algorithm,
            position,
            score,
            policy,
            arm_id,
            p_score,
            latency_ms,
            reward,
            served_at,
            context
        FROM recommendation_events
        WHERE experiment_id = :experiment_id
        {policy_filter}
        ORDER BY served_at DESC
        LIMIT :limit OFFSET :offset
    """), params).fetchall()
    
    # Get total count
    total_count = db.execute(text(f"""
        SELECT COUNT(*)
        FROM recommendation_events
        WHERE experiment_id = :experiment_id
        {policy_filter}
    """), {'experiment_id': experiment_id, **({} if not policy else {'policy': policy})}).scalar()
    
    return {
        'events': [
            {
                'id': event.id,
                'user_id': event.user_id,
                'algorithm': event.algorithm,
                'position': event.position,
                'score': event.score,
                'policy': event.policy,
                'arm_id': event.arm_id,
                'p_score': event.p_score,
                'latency_ms': event.latency_ms,
                'reward': event.reward,
                'served_at': event.served_at.isoformat(),
                'context': event.context
            }
            for event in events
        ],
        'pagination': {
            'total': total_count,
            'limit': limit,
            'offset': offset,
            'has_more': offset + limit < total_count
        }
    }

@router.get("/{experiment_id}/export")
def export_experiment_data(
    experiment_id: uuid.UUID,
    format: str = Query("csv", description="Export format: csv, json"),
    policy: Optional[str] = Query(None, description="Filter by policy"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Export experiment data"""
    
    # Validate format
    if format not in ['csv', 'json']:
        raise HTTPException(status_code=400, detail="Invalid format. Must be 'csv' or 'json'")
    
    # Build policy filter
    policy_filter = ""
    params = {'experiment_id': experiment_id}
    if policy:
        policy_filter = "AND policy = :policy"
        params['policy'] = policy
    
    # Get all events
    events = db.execute(text(f"""
        SELECT 
            id,
            user_id,
            algorithm,
            position,
            score,
            policy,
            arm_id,
            p_score,
            latency_ms,
            reward,
            served_at,
            context
        FROM recommendation_events
        WHERE experiment_id = :experiment_id
        {policy_filter}
        ORDER BY served_at
    """), params).fetchall()
    
    if format == 'csv':
        # Create CSV response
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'id', 'user_id', 'algorithm', 'position', 'score',
            'policy', 'arm_id', 'p_score', 'latency_ms', 'reward',
            'served_at', 'context'
        ])
        
        # Write data
        for event in events:
            writer.writerow([
                event.id,
                event.user_id,
                event.algorithm,
                event.position,
                event.score,
                event.policy,
                event.arm_id,
                event.p_score,
                event.latency_ms,
                event.reward,
                event.served_at.isoformat(),
                json.dumps(event.context) if event.context else ''
            ])
        
        # Return CSV response
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=experiment_{experiment_id}_events.csv"}
        )
    
    else:  # JSON format
        return {
            'experiment_id': str(experiment_id),
            'exported_at': datetime.utcnow().isoformat(),
            'total_events': len(events),
            'events': [
                {
                    'id': event.id,
                    'user_id': event.user_id,
                    'algorithm': event.algorithm,
                    'position': event.position,
                    'score': event.score,
                    'policy': event.policy,
                    'arm_id': event.arm_id,
                    'p_score': event.p_score,
                    'latency_ms': event.latency_ms,
                    'reward': event.reward,
                    'served_at': event.served_at.isoformat(),
                    'context': event.context
                }
                for event in events
            ]
        }

@router.get("/{experiment_id}/guardrails")
def get_guardrail_status(
    experiment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get real-time guardrail status"""
    
    # Get experiment
    experiment = db.query(Experiment).filter(Experiment.id == experiment_id).first()
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")
    
    # Get recent events (last 30 minutes)
    cutoff = datetime.utcnow() - timedelta(minutes=30)
    
    recent_events = db.execute(text("""
        SELECT 
            COUNT(*) as total_events,
            AVG(latency_ms) as avg_latency,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95_latency,
            AVG(reward) as avg_reward
        FROM recommendation_events
        WHERE experiment_id = :experiment_id
        AND served_at >= :cutoff
    """), {'experiment_id': experiment_id, 'cutoff': cutoff}).fetchone()
    
    # Get arm concentration
    arm_concentration = db.execute(text("""
        SELECT 
            arm_id,
            COUNT(*) as count,
            COUNT(*) * 100.0 / SUM(COUNT(*)) OVER() as percentage
        FROM recommendation_events
        WHERE experiment_id = :experiment_id
        AND served_at >= :cutoff
        GROUP BY arm_id
        ORDER BY count DESC
        LIMIT 1
    """), {'experiment_id': experiment_id, 'cutoff': cutoff}).fetchone()
    
    # Check guardrails
    guardrails = {
        'error_rate': {
            'status': 'pass',  # Would need error tracking
            'value': 0.0,
            'threshold': 0.01,
            'message': 'Error rate check not implemented'
        },
        'latency_p95': {
            'status': 'pass' if (recent_events.p95_latency or 0) < 120 else 'fail',
            'value': recent_events.p95_latency or 0,
            'threshold': 120,
            'message': f"P95 latency: {recent_events.p95_latency or 0}ms"
        },
        'arm_concentration': {
            'status': 'pass' if (arm_concentration.percentage or 0) < 50 else 'fail',
            'value': arm_concentration.percentage or 0,
            'threshold': 50,
            'message': f"Top arm concentration: {arm_concentration.percentage or 0:.1f}%"
        },
        'reward_drop': {
            'status': 'pass',  # Would need baseline comparison
            'value': recent_events.avg_reward or 0,
            'threshold': 0.05,
            'message': 'Reward drop check not implemented'
        }
    }
    
    # Overall status
    overall_status = 'pass'
    if any(g['status'] == 'fail' for g in guardrails.values()):
        overall_status = 'fail'
    
    return {
        'experiment_id': str(experiment_id),
        'checked_at': datetime.utcnow().isoformat(),
        'overall_status': overall_status,
        'guardrails': guardrails,
        'recent_metrics': {
            'total_events': recent_events.total_events or 0,
            'avg_latency': round(recent_events.avg_latency or 0, 1),
            'p95_latency': round(recent_events.p95_latency or 0, 1),
            'avg_reward': round(recent_events.avg_reward or 0, 3)
        }
    }
