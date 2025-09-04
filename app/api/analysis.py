from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel, HttpUrl
import httpx
from typing import Optional
import uuid
from datetime import datetime
import os
from dotenv import load_dotenv

from app.models import get_db, AnalysisTask, TaskStatus, User
from app.api.auth import get_current_user
from app.tasks.analysis_tasks import analyze_pr_task
from app.services.github_service import github_service
from app.utils.logging import logger
from app.utils.monitoring import REQUEST_COUNT

load_dotenv()

router = APIRouter(prefix="/api/v1", tags=["analysis"])

class AnalyzePRRequest(BaseModel):
    repo_url: HttpUrl
    pr_number: int
    github_token: Optional[str] = None  # Optional override

class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: int
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]

class AnalysisResultResponse(BaseModel):
    task_id: str
    status: str
    results: Optional[dict]
    metadata: Optional[dict]

@router.post("/analyze-pr")
async def analyze_pr(
    request: AnalyzePRRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Start PR analysis task."""
    try:
        REQUEST_COUNT.labels(method="POST", endpoint="/analyze-pr", status="started").inc()
        
        # Parse and validate repository URL
        repo = github_service.parse_repo_url(str(request.repo_url))
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid repository URL format"
            )
        
        # Use provided token or user's stored token
        github_token = request.github_token or current_user.access_token

        logger.info(f"DEBUG - Request github_token: {request.github_token[:12] if request.github_token else 'None'}")
        logger.info(f"DEBUG - User access_token: {current_user.access_token[:12] if current_user.access_token else 'None'}")
        logger.info(f"DEBUG - Final github_token: {github_token[:12] if github_token else 'None'}")
        logger.info(f"DEBUG - User ID: {current_user.id}, Username: {current_user.github_username}")

        if not github_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="GitHub access token required"
            )
        
        # Verify repository access
        has_access = await github_service.check_repo_access(repo, github_token)
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"No access to repository: {repo}"
            )
        
        # Check if PR exists
        async with httpx.AsyncClient() as client:
            pr_response = await client.get(
                f"https://api.github.com/repos/{repo}/pulls/{request.pr_number}",
                headers={"Authorization": f"token {github_token}"}
            )
            
            if pr_response.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"PR #{request.pr_number} not found in {repo}"
                )
            elif pr_response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to fetch PR details: {pr_response.status_code}"
                )
            
            pr_details = pr_response.json()
        
        # Check for existing running task for this PR
        existing_task = db.query(AnalysisTask).filter(
            AnalysisTask.user_id == current_user.id,
            AnalysisTask.repo_url == str(request.repo_url),
            AnalysisTask.pr_number == request.pr_number,
            AnalysisTask.status.in_([TaskStatus.PENDING, TaskStatus.PROCESSING])
        ).first()
        
        if existing_task:
            logger.info("Returning existing task", task_id=existing_task.task_id)
            return {
                "task_id": existing_task.task_id,
                "status": "already_running",
                "message": "Analysis already in progress for this PR"
            }
        
        # Create new analysis task
        task_id = str(uuid.uuid4())
        
        task_record = AnalysisTask(
            task_id=task_id,
            user_id=current_user.id,
            repo_url=str(request.repo_url),
            pr_number=request.pr_number,
            commit_sha=pr_details["head"]["sha"],
            status=TaskStatus.PENDING
        )
        
        db.add(task_record)
        db.commit()
        
        # Queue the analysis task
        analyze_pr_task.delay(
            task_id=task_id,
            repo_url=str(request.repo_url),
            pr_number=request.pr_number,
            user_id=current_user.id
        )
        
        logger.info("PR analysis queued", 
                   task_id=task_id, 
                   repo=repo, 
                   pr=request.pr_number,
                   user=current_user.github_username)

        try:
            import redis
            r = redis.Redis.from_url(os.getenv('REDIS_URL', 'redis://redis:6379/0'))
            queue_length = r.llen('celery')
            logger.info("Current queue length", length=queue_length)
        except Exception as e:
            logger.error("Failed to check queue", error=str(e))
        
        REQUEST_COUNT.labels(method="POST", endpoint="/analyze-pr", status="success").inc()
        
        return {
            "task_id": task_id,
            "status": "queued",
            "message": "PR analysis started",
            "repo": repo,
            "pr_number": request.pr_number
        }
        
    except HTTPException:
        REQUEST_COUNT.labels(method="POST", endpoint="/analyze-pr", status="error").inc()
        raise
    except Exception as e:
        logger.error("Failed to start PR analysis", error=str(e))
        REQUEST_COUNT.labels(method="POST", endpoint="/analyze-pr", status="error").inc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start analysis"
        )

@router.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get analysis task status."""
    try:
        task = db.query(AnalysisTask).filter(
            AnalysisTask.task_id == task_id,
            AnalysisTask.user_id == current_user.id
        ).first()
        
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )
        
        return TaskStatusResponse(
            task_id=task.task_id,
            status=task.status.value,
            progress=task.progress,
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            error_message=task.error_message
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get task status", task_id=task_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve task status"
        )

@router.get("/results/{task_id}", response_model=AnalysisResultResponse)
async def get_analysis_results(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get analysis results."""
    try:
        task = db.query(AnalysisTask).filter(
            AnalysisTask.task_id == task_id,
            AnalysisTask.user_id == current_user.id
        ).first()
        
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )
        
        if task.status != TaskStatus.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Task not completed. Status: {task.status.value}"
            )
        
        return AnalysisResultResponse(
            task_id=task.task_id,
            status=task.status.value,
            results=task.results,
            metadata={
                "repo_url": task.repo_url,
                "pr_number": task.pr_number,
                "commit_sha": task.commit_sha,
                "analysis_timestamp": task.completed_at.isoformat() if task.completed_at else None
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get analysis results", task_id=task_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve analysis results"
        )

@router.get("/history")
async def get_analysis_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 10,
    offset: int = 0
):
    """Get user's analysis history."""
    try:
        tasks = db.query(AnalysisTask).filter(
            AnalysisTask.user_id == current_user.id
        ).order_by(
            AnalysisTask.created_at.desc()
        ).offset(offset).limit(limit).all()
        
        history = []
        for task in tasks:
            history.append({
                "task_id": task.task_id,
                "repo_url": task.repo_url,
                "pr_number": task.pr_number,
                "status": task.status.value,
                "created_at": task.created_at,
                "completed_at": task.completed_at,
                "has_results": task.results is not None
            })
        
        return {
            "history": history,
            "total": len(history),
            "limit": limit,
            "offset": offset
        }
        
    except Exception as e:
        logger.error("Failed to get analysis history", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve analysis history"
        )