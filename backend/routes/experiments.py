"""
Experiment Management API Endpoints

REST API for creating, managing, and monitoring bandit experiments.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import uuid
import logging

from ..database import get_db
from ..auth import get_current_user, User
from ..models import Experiment, PolicyAssignment
from ..ml.experiment_manager import ExperimentManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/experiments", tags=["experiments"])

# Request/Response Models
class ExperimentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="Experiment name")
    start_at: datetime = Field(..., description="When experiment starts")
    end_at: Optional[datetime] = Field(None, description="When experiment ends (optional)")
    traffic_pct: float = Field(0.1, ge=0.0, le=1.0, description="Percentage of traffic to include")
    default_policy: str = Field("thompson", description="Fallback policy")
    notes: Optional[str] = Field(None, description="Additional notes")

class ExperimentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    end_at: Optional[datetime] = None
    traffic_pct: Optional[float] = Field(None, ge=0.0, le=1.0)
    notes: Optional[str] = None

class ExperimentResponse(BaseModel):
    id: str
    name: str
    start_at: datetime
    end_at: Optional[datetime]
    traffic_pct: float
    default_policy: str
    notes: Optional[str]
    created_at: datetime
    status: str
    stats: Dict[str, Any]

class AssignmentResponse(BaseModel):
    user_id: int
    policy: str
    bucket: int
    assigned_at: datetime

# Endpoints
@router.post("/", response_model=ExperimentResponse)
async def create_experiment(
    experiment_data: ExperimentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new bandit experiment
    
    Requires admin privileges for production safety.
    """
    # TODO: Add admin check
    # if not current_user.is_admin:
    #     raise HTTPException(status_code=403, detail="Admin privileges required")
    
    try:
        manager = ExperimentManager(db)
        experiment = manager.create_experiment(
            name=experiment_data.name,
            start_at=experiment_data.start_at,
            end_at=experiment_data.end_at,
            traffic_pct=experiment_data.traffic_pct,
            default_policy=experiment_data.default_policy,
            notes=experiment_data.notes
        )
        
        # Get stats for response
        stats = manager.get_experiment_stats(experiment.id)
        
        logger.info(f"Created experiment {experiment.id} by user {current_user.id}")
        
        return ExperimentResponse(
            id=str(experiment.id),
            name=experiment.name,
            start_at=experiment.start_at,
            end_at=experiment.end_at,
            traffic_pct=experiment.traffic_pct,
            default_policy=experiment.default_policy,
            notes=experiment.notes,
            created_at=experiment.created_at,
            status=stats['status'],
            stats=stats
        )
        
    except Exception as e:
        logger.error(f"Failed to create experiment: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{experiment_id}", response_model=ExperimentResponse)
async def get_experiment(
    experiment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get experiment details and statistics"""
    try:
        exp_uuid = uuid.UUID(experiment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid experiment ID format")
    
    manager = ExperimentManager(db)
    
    try:
        stats = manager.get_experiment_stats(exp_uuid)
        experiment = db.query(Experiment).filter(Experiment.id == exp_uuid).first()
        
        if not experiment:
            raise HTTPException(status_code=404, detail="Experiment not found")
        
        return ExperimentResponse(
            id=str(experiment.id),
            name=experiment.name,
            start_at=experiment.start_at,
            end_at=experiment.end_at,
            traffic_pct=experiment.traffic_pct,
            default_policy=experiment.default_policy,
            notes=experiment.notes,
            created_at=experiment.created_at,
            status=stats['status'],
            stats=stats
        )
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get experiment {experiment_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{experiment_id}", response_model=ExperimentResponse)
async def update_experiment(
    experiment_id: str,
    update_data: ExperimentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update experiment configuration"""
    try:
        exp_uuid = uuid.UUID(experiment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid experiment ID format")
    
    experiment = db.query(Experiment).filter(Experiment.id == exp_uuid).first()
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")
    
    # Update fields
    if update_data.name is not None:
        experiment.name = update_data.name
    if update_data.end_at is not None:
        experiment.end_at = update_data.end_at
    if update_data.traffic_pct is not None:
        experiment.traffic_pct = update_data.traffic_pct
    if update_data.notes is not None:
        experiment.notes = update_data.notes
    
    try:
        db.commit()
        
        # Get updated stats
        manager = ExperimentManager(db)
        stats = manager.get_experiment_stats(exp_uuid)
        
        logger.info(f"Updated experiment {experiment_id} by user {current_user.id}")
        
        return ExperimentResponse(
            id=str(experiment.id),
            name=experiment.name,
            start_at=experiment.start_at,
            end_at=experiment.end_at,
            traffic_pct=experiment.traffic_pct,
            default_policy=experiment.default_policy,
            notes=experiment.notes,
            created_at=experiment.created_at,
            status=stats['status'],
            stats=stats
        )
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update experiment {experiment_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{experiment_id}/assignments", response_model=List[AssignmentResponse])
async def get_experiment_assignments(
    experiment_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    policy: Optional[str] = Query(None, description="Filter by policy"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user assignments for an experiment"""
    try:
        exp_uuid = uuid.UUID(experiment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid experiment ID format")
    
    query = db.query(PolicyAssignment).filter(PolicyAssignment.experiment_id == exp_uuid)
    
    if policy:
        query = query.filter(PolicyAssignment.policy == policy)
    
    assignments = query.offset(offset).limit(limit).all()
    
    return [
        AssignmentResponse(
            user_id=assignment.user_id,
            policy=assignment.policy,
            bucket=assignment.bucket,
            assigned_at=assignment.assigned_at
        )
        for assignment in assignments
    ]

@router.post("/{experiment_id}/stop")
async def stop_experiment(
    experiment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """End an experiment"""
    try:
        exp_uuid = uuid.UUID(experiment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid experiment ID format")
    
    manager = ExperimentManager(db)
    
    try:
        manager.end_experiment(exp_uuid)
        logger.info(f"Stopped experiment {experiment_id} by user {current_user.id}")
        
        return {"status": "success", "message": "Experiment ended successfully"}
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to stop experiment {experiment_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=List[ExperimentResponse])
async def list_experiments(
    status: Optional[str] = Query(None, description="Filter by status: active, scheduled, ended"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List experiments with optional filtering"""
    query = db.query(Experiment)
    
    if status == "active":
        now = datetime.utcnow()
        query = query.filter(
            Experiment.start_at <= now,
            (Experiment.end_at.is_(None)) | (Experiment.end_at > now)
        )
    elif status == "scheduled":
        now = datetime.utcnow()
        query = query.filter(Experiment.start_at > now)
    elif status == "ended":
        now = datetime.utcnow()
        query = query.filter(Experiment.end_at.isnot(None), Experiment.end_at <= now)
    
    experiments = query.order_by(Experiment.created_at.desc()).offset(offset).limit(limit).all()
    
    manager = ExperimentManager(db)
    
    return [
        ExperimentResponse(
            id=str(exp.id),
            name=exp.name,
            start_at=exp.start_at,
            end_at=exp.end_at,
            traffic_pct=exp.traffic_pct,
            default_policy=exp.default_policy,
            notes=exp.notes,
            created_at=exp.created_at,
            status=manager._get_experiment_status(exp),
            stats=manager.get_experiment_stats(exp.id)
        )
        for exp in experiments
    ]

@router.get("/{experiment_id}/validate")
async def validate_experiment(
    experiment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Validate experiment configuration and health"""
    try:
        exp_uuid = uuid.UUID(experiment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid experiment ID format")
    
    manager = ExperimentManager(db)
    
    try:
        validation = manager.validate_experiment(exp_uuid)
        return validation
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to validate experiment {experiment_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{experiment_id}/traffic-allocation")
async def get_traffic_allocation(
    experiment_id: str,
    policies: List[str] = Query(..., description="List of policies to allocate traffic to"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get traffic allocation for policies in an experiment"""
    try:
        exp_uuid = uuid.UUID(experiment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid experiment ID format")
    
    manager = ExperimentManager(db)
    
    try:
        allocation = manager.get_traffic_allocation(exp_uuid, policies)
        return {
            "experiment_id": experiment_id,
            "policies": policies,
            "allocation": allocation,
            "total_traffic": sum(allocation.values())
        }
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get traffic allocation for experiment {experiment_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
