import os
from datetime import datetime, timezone
from celery import Celery
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from app.models import get_db, AnalysisTask, TaskStatus, User
from app.models.database import SessionLocal
from app.utils.logging import logger
from app.utils.monitoring import ANALYSIS_COUNT, ERROR_COUNT
from typing import Dict

import asyncio
# Remove nest_asyncio completely - it causes issues in Celery

# Load environment variables
load_dotenv()

# Celery configuration using environment variables
celery_app = Celery(
    "code_review_agent",
    broker=os.getenv('REDIS_URL', 'redis://redis:6379/0'),
    backend=os.getenv('REDIS_RESULTS_URL', 'redis://redis:6379/1'),
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

def run_async_analysis(repo_url: str, pr_number: int, github_token: str):
    """Synchronous wrapper for async analysis."""
    try:
        # Import here to avoid circular imports at module level
        from app.services.analysis_service import analysis_service
        
        # Use asyncio.run() instead of manual loop management
        result = asyncio.run(analysis_service.analyze_pr(
            repo_url=repo_url,
            pr_number=pr_number,
            github_token=github_token
        ))
        return result
    except Exception as e:
        logger.error("Async analysis failed", error=str(e))
        raise

@celery_app.task(max_retries=3)
def analyze_pr_task(task_id: str, repo_url: str, pr_number: int, user_id: int):
    """Celery task to analyze a GitHub pull request."""
    from datetime import datetime, timezone
    from contextlib import contextmanager
    
    @contextmanager
    def get_db_context():
        db = SessionLocal()
        try:
            yield db
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    
    with get_db_context() as db:
        task_record = None
        try:
            logger.info("Task started", task_id=task_id, repo_url=repo_url, pr_number=pr_number, user_id=user_id)
            
            # Get task record
            task_record = db.query(AnalysisTask).filter(
                AnalysisTask.task_id == task_id
            ).first()
            
            if not task_record:
                logger.error("Task record not found", task_id=task_id)
                return {"error": "Task record not found"}
            
            # Get user and GitHub token
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.error("User not found", user_id=user_id)
                task_record.status = TaskStatus.FAILED
                task_record.error_message = "User not found"
                db.commit()
                return {"error": "User not found"}
            
            if not user.access_token:
                logger.error("User access token not found", user_id=user_id, username=user.github_username)
                task_record.status = TaskStatus.FAILED
                task_record.error_message = "User access token not available"
                db.commit()
                return {"error": "Authentication failed - no GitHub token"}
            
            # Log token info for debugging (without exposing the token)
            logger.info("Using stored GitHub token", 
                       user_id=user_id, 
                       username=user.github_username,
                       token_length=len(user.access_token))
            
            # Update task status to processing
            task_record.status = TaskStatus.PROCESSING
            task_record.started_at = datetime.now(timezone.utc)
            task_record.progress = 10
            db.commit()
            
            logger.info("Starting PR analysis", task_id=task_id, repo=repo_url, pr=pr_number)
            
            # Perform the analysis using the synchronous wrapper
            result = run_async_analysis(
                repo_url=repo_url,
                pr_number=pr_number,
                github_token=user.access_token
            )
            
            # Update task record with results
            task_record.status = TaskStatus.COMPLETED
            task_record.completed_at = datetime.now(timezone.utc)
            task_record.progress = 100
            task_record.results = result["results"]
            task_record.commit_sha = result["metadata"]["commit_sha"]
            
            db.commit()
            
            logger.info("PR analysis completed", task_id=task_id)
            ANALYSIS_COUNT.labels(status="completed").inc()
            return result
                
        except Exception as e:
            # Enhanced error logging
            import traceback
            import sys
            
            tb_str = traceback.format_exc()
            print(f"\n{'='*60}\nFULL TRACEBACK:\n{tb_str}\n{'='*60}\n", file=sys.stderr)
            logger.error("Task execution failed", 
                        task_id=task_id, 
                        error=str(e),
                        traceback=tb_str)
            
            # Update task with error
            if task_record:
                task_record.status = TaskStatus.FAILED
                task_record.error_message = str(e)
                task_record.completed_at = datetime.now(timezone.utc)
                db.commit()
            
            ERROR_COUNT.labels(error_type="task_failure").inc()
            return {"error": str(e)}

# Additional utility tasks
@celery_app.task
def cleanup_old_tasks():
    """Clean up old completed tasks."""
    db: Session = next(get_db())
    
    try:
        # Delete tasks older than 30 days
        from datetime import timedelta
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
        
        deleted_count = db.query(AnalysisTask).filter(
            AnalysisTask.completed_at < cutoff_date
        ).delete()
        
        db.commit()
        logger.info("Cleaned up old tasks", count=deleted_count)
        
    except Exception as e:
        logger.error("Task cleanup failed", error=str(e))
    finally:
        db.close()

@celery_app.task
def health_check():
    """Health check task for monitoring."""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

@celery_app.task
def test_github_token(user_id: int):
    """Test task to verify GitHub token is working."""
    from contextlib import contextmanager
    
    @contextmanager
    def get_db_context():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
    
    with get_db_context() as db:
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user or not user.access_token:
                return {"error": "No user or token found"}
            
            # Test the token with a simple GitHub API call
            from app.services.github_service import github_service
            result = asyncio.run(github_service.get_user_info(user.access_token))
            
            if result:
                return {
                    "success": True,
                    "github_user": result.get("login"),
                    "token_valid": True
                }
            else:
                return {"error": "GitHub token invalid or expired"}
                
        except Exception as e:
            return {"error": str(e)}