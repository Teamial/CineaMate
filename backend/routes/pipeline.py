"""
API endpoints for pipeline management and monitoring
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

from ..database import get_db
from ..models import PipelineRun, User
from ..auth import get_current_user

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


# Schemas
class PipelineRunResponse(BaseModel):
    id: int
    run_date: datetime
    movies_processed: Optional[int]
    status: str
    source_categories: Optional[List[str]]
    duration_seconds: Optional[float]
    error_message: Optional[str]
    
    class Config:
        from_attributes = True


class PipelineRunRequest(BaseModel):
    update_type: str = "quick"  # quick, daily, full


class PipelineStatusResponse(BaseModel):
    is_running: bool
    last_run: Optional[PipelineRunResponse]
    total_runs: int
    successful_runs: int
    failed_runs: int
    scheduled_jobs: List[dict]


# Endpoints
@router.get("/status", response_model=PipelineStatusResponse)
async def get_pipeline_status(db: Session = Depends(get_db)):
    """Get current pipeline status and statistics"""
    
    # Get latest run
    last_run = db.query(PipelineRun).order_by(desc(PipelineRun.run_date)).first()
    
    # Get statistics
    total_runs = db.query(PipelineRun).count()
    successful_runs = db.query(PipelineRun).filter(PipelineRun.status == "SUCCESS").count()
    failed_runs = db.query(PipelineRun).filter(PipelineRun.status == "FAILED").count()
    
    # Check if currently running
    is_running = False
    if last_run and last_run.status == "RUNNING":
        is_running = True
    
    # Get scheduled jobs info
    scheduled_jobs = []
    try:
        from ..scheduler import get_scheduler
        scheduler = get_scheduler()
        scheduled_jobs = scheduler.get_job_status()
    except Exception as e:
        # Scheduler might not be running
        pass
    
    return {
        "is_running": is_running,
        "last_run": last_run,
        "total_runs": total_runs,
        "successful_runs": successful_runs,
        "failed_runs": failed_runs,
        "scheduled_jobs": scheduled_jobs
    }


@router.get("/runs", response_model=List[PipelineRunResponse])
async def get_pipeline_runs(
    limit: int = 20,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get pipeline run history"""
    
    query = db.query(PipelineRun).order_by(desc(PipelineRun.run_date))
    
    if status:
        query = query.filter(PipelineRun.status == status.upper())
    
    runs = query.limit(limit).all()
    return runs


@router.get("/runs/{run_id}", response_model=PipelineRunResponse)
async def get_pipeline_run(run_id: int, db: Session = Depends(get_db)):
    """Get details of a specific pipeline run"""
    
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    
    return run


@router.post("/run")
async def trigger_pipeline_run(
    request: PipelineRunRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Manually trigger a pipeline run
    Requires authentication
    """
    
    # Check if pipeline is already running
    latest_run = db.query(PipelineRun).order_by(desc(PipelineRun.run_date)).first()
    if latest_run and latest_run.status == "RUNNING":
        raise HTTPException(
            status_code=409,
            detail="Pipeline is already running. Please wait for it to complete."
        )
    
    # Validate update type
    valid_types = ['quick', 'daily', 'full']
    if request.update_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid update_type. Must be one of: {', '.join(valid_types)}"
        )
    
    # Create a new pipeline run record
    new_run = PipelineRun(
        run_date=datetime.utcnow(),
        status="RUNNING",
        movies_processed=0,
        source_categories=[]
    )
    db.add(new_run)
    db.commit()
    db.refresh(new_run)
    
    # Trigger the pipeline in the background
    background_tasks.add_task(
        run_pipeline_task,
        run_id=new_run.id,
        update_type=request.update_type
    )
    
    return {
        "message": f"Pipeline {request.update_type} update started",
        "run_id": new_run.id,
        "status": "RUNNING",
        "triggered_by": current_user.username
    }


def run_pipeline_task(run_id: int, update_type: str):
    """Background task to run the pipeline"""
    from ..scheduler import get_scheduler
    from ..database import SessionLocal
    import traceback
    
    db = SessionLocal()
    start_time = datetime.utcnow()
    
    try:
        # Get scheduler and run the pipeline
        scheduler = get_scheduler()
        scheduler.run_manual_update(update_type)
        
        # Update run status to success
        run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
        if run:
            duration = (datetime.utcnow() - start_time).total_seconds()
            run.status = "SUCCESS"
            run.duration_seconds = duration
            db.commit()
            
    except Exception as e:
        # Update run status to failed
        run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
        if run:
            duration = (datetime.utcnow() - start_time).total_seconds()
            run.status = "FAILED"
            run.duration_seconds = duration
            run.error_message = str(e) + "\n" + traceback.format_exc()
            db.commit()
    finally:
        db.close()


@router.get("/scheduler/status")
async def get_scheduler_status(current_user: User = Depends(get_current_user)):
    """Get scheduler service status (requires auth)"""
    
    try:
        from ..scheduler import get_scheduler
        scheduler = get_scheduler()
        jobs = scheduler.get_job_status()
        
        return {
            "scheduler_running": scheduler.scheduler.running,
            "total_jobs": len(jobs),
            "jobs": jobs
        }
    except Exception as e:
        return {
            "scheduler_running": False,
            "error": str(e),
            "message": "Scheduler service is not available"
        }


@router.post("/scheduler/start")
async def start_scheduler(current_user: User = Depends(get_current_user)):
    """Start the scheduler service (requires auth)"""
    
    try:
        from ..scheduler import get_scheduler
        scheduler = get_scheduler()
        
        if scheduler.scheduler.running:
            return {"message": "Scheduler is already running"}
        
        scheduler.start()
        return {"message": "Scheduler started successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start scheduler: {str(e)}")


@router.post("/scheduler/stop")
async def stop_scheduler(current_user: User = Depends(get_current_user)):
    """Stop the scheduler service (requires auth)"""
    
    try:
        from ..scheduler import get_scheduler
        scheduler = get_scheduler()
        
        if not scheduler.scheduler.running:
            return {"message": "Scheduler is not running"}
        
        scheduler.stop()
        return {"message": "Scheduler stopped successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop scheduler: {str(e)}")

