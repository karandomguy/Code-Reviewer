from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.models import get_db, User
from app.services.auth_service import auth_service
from app.services.github_service import github_service
from app.utils.logging import logger
import httpx
import os
from dotenv import load_dotenv
load_dotenv()


router = APIRouter(prefix="/auth", tags=["authentication"])
security = HTTPBearer()

class GitHubCallbackRequest(BaseModel):
    code: str
    state: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

@router.get("/login")
async def github_login():
    """Initiate GitHub OAuth login."""
    import secrets
    state = secrets.token_urlsafe(32)
    
    # Get GitHub OAuth config from environment variables
    github_client_id = os.getenv('GITHUB_CLIENT_ID')
    github_redirect_uri = os.getenv('GITHUB_OAUTH_REDIRECT_URI') or 'http://localhost:8000/auth/callback'
    
    # Debug logging
    logger.info(f"GitHub Client ID: {github_client_id}")
    logger.info(f"GitHub Redirect URI: {github_redirect_uri}")
    
    if not github_client_id or not github_redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Missing GitHub OAuth configuration. Client ID: {github_client_id}, Redirect URI: {github_redirect_uri}"
        )
    
    oauth_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={github_client_id}"
        f"&scope=repo,read:user"
        f"&state={state}"
        f"&redirect_uri={github_redirect_uri}"
    )
    
    return {
        "oauth_url": oauth_url,
        "state": state
    }

@router.get("/callback")
async def github_callback_get(
    code: str,
    state: str,
    db: Session = Depends(get_db)
):
    """Handle GitHub OAuth callback (GET redirect)."""
    request = GitHubCallbackRequest(code=code, state=state)
    return await github_callback_post(request, db)

@router.post("/callback", response_model=TokenResponse)
async def github_callback_post(
    request: GitHubCallbackRequest,
    db: Session = Depends(get_db)
):
    """Handle GitHub OAuth callback."""
    try:
        logger.info(f"Starting OAuth callback with code: {request.code[:10]}...")

        github_client_id = os.getenv('GITHUB_CLIENT_ID')
        github_client_secret = os.getenv('GITHUB_CLIENT_SECRET')

        logger.info(f"Using GitHub Client ID: {github_client_id}")
        logger.info(f"Using GitHub Client Secret: {github_client_secret[:8]}..." if github_client_secret else "No client secret")
        
        # Exchange code for access token - do it directly instead of using github_service
        async with httpx.AsyncClient() as client:
            # Get GitHub token directly
            token_data = {
                "client_id": github_client_id,
                "client_secret": github_client_secret,
                "code": request.code,
            }
            
            logger.info(f"Making request to GitHub with code: {request.code[:10]}...")
            
            token_response = await client.post(
                "https://github.com/login/oauth/access_token",
                data=token_data,
                headers={"Accept": "application/json"}
            )
            
            logger.info(f"GitHub response status: {token_response.status_code}")
            logger.info(f"GitHub response text: {token_response.text}")
            
            if token_response.status_code != 200:
                logger.error(f"GitHub API returned status {token_response.status_code}: {token_response.text}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"GitHub API error: {token_response.status_code} - {token_response.text}"
                )
            
            token_response_data = token_response.json()
            github_token = token_response_data.get("access_token")
            
            if not github_token:
                logger.error(f"No access token in GitHub response: {token_response_data}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"GitHub response missing access_token: {token_response_data}"
                )
        
        logger.info("Successfully got GitHub token")
        
        # Get user information from GitHub - directly
        async with httpx.AsyncClient() as client:
            user_response = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"token {github_token}"}
            )
            
            logger.info(f"GitHub user API response status: {user_response.status_code}")
            
            if user_response.status_code != 200:
                logger.error(f"Failed to get user info - status: {user_response.status_code}, text: {user_response.text}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to get user information from GitHub: {user_response.status_code}"
                )
            
            github_user = user_response.json()
        
        logger.info(f"Got GitHub user: {github_user.get('login', 'unknown')}")
        
        # Check if user exists, create if not
        user = db.query(User).filter(
            User.github_id == github_user["id"]
        ).first()
        
        if not user:
            logger.info("Creating new user")
            user = User(
                github_id=github_user["id"],
                github_username=github_user["login"],
                email=github_user.get("email"),
                avatar_url=github_user.get("avatar_url"),
                access_token=github_token,  # In production, encrypt this
            )
            db.add(user)
        else:
            logger.info("Updating existing user")
            # Update existing user
            user.github_username = github_user["login"]
            user.email = github_user.get("email")
            user.avatar_url = github_user.get("avatar_url")
            user.access_token = github_token  # In production, encrypt this
        
        db.commit()
        db.refresh(user)
        logger.info(f"User saved with ID: {user.id}")
        
        # Create JWT token
        access_token = auth_service.create_access_token(
            user_id=user.id,
            github_id=user.github_id
        )
        
        logger.info("User authenticated successfully", 
                   user_id=user.id, 
                   github_username=user.github_username)
        
        return TokenResponse(
            access_token=access_token,
            user={
                "id": user.id,
                "github_id": user.github_id,
                "username": user.github_username,
                "email": user.email,
                "avatar_url": user.avatar_url
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication failed with error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication failed: {str(e)}"
        )

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Get current authenticated user."""
    try:
        token = credentials.credentials
        user = auth_service.get_current_user(db, token)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials"
            )
        
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication verification failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication verification failed"
        )

@router.get("/me")
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """Get current user information."""
    return {
        "id": current_user.id,
        "github_id": current_user.github_id,
        "username": current_user.github_username,
        "email": current_user.email,
        "avatar_url": current_user.avatar_url,
        "is_active": current_user.is_active
    }