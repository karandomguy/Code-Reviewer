from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, ForeignKey, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum
from app.models.database import Base

class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class AnalysisTask(Base):
    __tablename__ = "analysis_tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # GitHub PR info
    repo_url = Column(String, nullable=False)
    pr_number = Column(Integer, nullable=False)
    commit_sha = Column(String)
    
    # Task info
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, index=True)
    progress = Column(Integer, default=0)  # 0-100
    error_message = Column(Text)
    
    # Results
    results = Column(JSON)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    
    # Relationships
    user = relationship("User")