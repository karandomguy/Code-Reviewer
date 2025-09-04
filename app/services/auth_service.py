import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from app.models import User
from app.utils.logging import logger

# Load environment variables
load_dotenv()

class AuthService:
    def __init__(self):
        self.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-in-production')
        self.algorithm = os.getenv('ALGORITHM', 'HS256')
        self.expire_minutes = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', str(30 * 24 * 60)))  # 30 days default
    
    def create_access_token(self, user_id: int, github_id: int) -> str:
        """Create JWT access token for user."""
        expire = datetime.now(timezone.utc) + timedelta(minutes=self.expire_minutes)
        to_encode = {
            "sub": str(user_id),
            "github_id": github_id,
            "exp": expire,
            "type": "access"
        }
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt
    
    def verify_token(self, token: str) -> Optional[dict]:
        """Verify and decode JWT token."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            user_id: str = payload.get("sub")
            github_id: int = payload.get("github_id")
            
            if user_id is None or github_id is None:
                return None
                
            return {"user_id": int(user_id), "github_id": github_id}
        except JWTError as e:
            logger.error("Token verification failed", error=str(e))
            return None
    
    def get_current_user(self, db: Session, token: str) -> Optional[User]:
        """Get current user from token."""
        payload = self.verify_token(token)
        if not payload:
            return None
        
        user = db.query(User).filter(User.id == payload["user_id"]).first()
        return user

auth_service = AuthService()