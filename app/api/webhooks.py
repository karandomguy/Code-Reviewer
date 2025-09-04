from fastapi import APIRouter, Request, HTTPException, status, Depends
from sqlalchemy.orm import Session
import hashlib
import hmac
import json
from app.models import get_db, User, AnalysisTask, TaskStatus
from app.tasks.analysis_tasks import analyze_pr_task
from app.services.github_service import github_service
from app.config import settings
from app.utils.logging import logger

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook signature."""
    if not signature.startswith('sha256='):
        return False
    
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    received_signature = signature[7:]  # Remove 'sha256=' prefix
    return hmac.compare_digest(expected_signature, received_signature)

@router.post("/github")
async def github_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """Handle GitHub webhook events."""
    try:
        # Get request data
        payload = await request.body()
        headers = request.headers
        
        # Verify signature if webhook secret is configured
        github_signature = headers.get('X-Hub-Signature-256', '')
        webhook_secret = settings.github_webhook_secret
        
        if webhook_secret and not verify_github_signature(payload, github_signature, webhook_secret):
            logger.warning("Invalid GitHub webhook signature")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid signature"
            )
        
        # Parse event data
        event_type = headers.get('X-GitHub-Event', '')
        try:
            event_data = json.loads(payload.decode('utf-8'))
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload"
            )
        
        logger.info("GitHub webhook received", event_type=event_type)
        
        # Handle pull request events
        if event_type == "pull_request":
            return await handle_pull_request_event(event_data, db)
        
        # Handle push events (for auto-analysis)
        elif event_type == "push":
            return await handle_push_event(event_data, db)
        
        # Handle installation events
        elif event_type == "installation":
            return await handle_installation_event(event_data, db)
        
        else:
            logger.info("Unhandled webhook event type", event_type=event_type)
            return {"message": f"Event type {event_type} not handled"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Webhook processing failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook processing failed"
        )

async def handle_pull_request_event(event_data: dict, db: Session):
    """Handle pull request webhook events."""
    action = event_data.get('action')
    pull_request = event_data.get('pull_request', {})
    repository = event_data.get('repository', {})
    
    # Only process opened, reopened, or synchronize events
    if action not in ['opened', 'reopened', 'synchronize']:
        return {"message": f"PR action {action} ignored"}
    
    repo_full_name = repository.get('full_name')
    pr_number = pull_request.get('number')
    
    if not repo_full_name or not pr_number:
        logger.error("Missing repo or PR number in webhook")
        return {"error": "Invalid webhook data"}
    
    # Check if auto-analysis is enabled for this repo
    # This would require a repository configuration table
    # For now, we'll skip auto-analysis and just log the event
    
    logger.info("PR event processed", 
               repo=repo_full_name, 
               pr=pr_number, 
               action=action)
    
    return {
        "message": "PR event processed",
        "repo": repo_full_name,
        "pr_number": pr_number,
        "action": action
    }

async def handle_push_event(event_data: dict, db: Session):
    """Handle push webhook events."""
    repository = event_data.get('repository', {})
    ref = event_data.get('ref', '')
    commits = event_data.get('commits', [])
    
    repo_full_name = repository.get('full_name')
    branch = ref.replace('refs/heads/', '') if ref.startswith('refs/heads/') else ref
    
    logger.info("Push event received", 
               repo=repo_full_name, 
               branch=branch, 
               commits_count=len(commits))
    
    # Could trigger analysis of recent commits or related PRs
    return {
        "message": "Push event processed",
        "repo": repo_full_name,
        "branch": branch,
        "commits": len(commits)
    }

async def handle_installation_event(event_data: dict, db: Session):
    """Handle GitHub App installation events."""
    action = event_data.get('action')
    installation = event_data.get('installation', {})
    
    logger.info("Installation event", action=action, installation_id=installation.get('id'))
    
    # Handle app installation/uninstallation
    return {
        "message": f"Installation {action} processed",
        "installation_id": installation.get('id')
    }