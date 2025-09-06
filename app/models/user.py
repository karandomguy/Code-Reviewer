from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.sql import func
from app.models.database import Base
from app.models.encrypted_field import EncryptedType

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    github_id = Column(Integer, unique=True, index=True, nullable=False)
    github_username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, index=True)
    avatar_url = Column(String)
    access_token = Column(EncryptedType, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def get_decrypted_token(self) -> str:
        """Get the decrypted access token.
        
        Note: The EncryptedType field automatically handles decryption,
        so this method is primarily for explicit clarity in code.
        """
        return self.access_token
    
    def set_access_token(self, token: str):
        """Set the access token (will be automatically encrypted).
        
        Note: The EncryptedType field automatically handles encryption,
        so this method is primarily for explicit clarity in code.
        """
        self.access_token = token