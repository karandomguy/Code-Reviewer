"""Database models."""
from .database import Base, engine, get_db
from .user import User
from .task import AnalysisTask, TaskStatus

# Create all tables
import os
if os.getenv('CREATE_TABLES', 'false').lower() == 'true':
    Base.metadata.create_all(bind=engine)
__all__ = ["Base", "User", "AnalysisTask", "TaskStatus", "get_db"]