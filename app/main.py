import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time
import uvicorn

from app.config import settings
from app.api import auth, analysis
from app.utils.logging import logger, setup_logging
from app.utils.monitoring import start_metrics_server, REQUEST_COUNT, REQUEST_DURATION
from app.models import Base, engine

# Setup logging
setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Code Review Agent API")
    
    # Create database tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created")
    
    # Only start metrics server on first worker to avoid port conflicts
    import os
    import multiprocessing
    
    # Check if we're the first worker or running in single-process mode
    current_process = multiprocessing.current_process()
    worker_id = os.getenv('GUNICORN_WORKER_ID')
    
    # Start metrics only on main process or first worker
    should_start_metrics = (
        current_process.name == 'MainProcess' or 
        worker_id is None or 
        worker_id == '1'
    )
    
    if should_start_metrics:
        try:
            start_metrics_server()
            logger.info("Metrics server started on primary worker")
        except Exception as e:
            logger.warning(f"Could not start metrics server: {e}")
    else:
        logger.info(f"Skipping metrics server on worker process {worker_id}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Code Review Agent API")

# Create FastAPI application
app = FastAPI(
    title="Code Review Agent API",
    description="AI-powered GitHub PR analysis system",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    # Process request
    response = await call_next(request)
    
    # Log metrics
    process_time = time.time() - start_time
    REQUEST_DURATION.observe(process_time)
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()
    
    # Log request details
    logger.info("Request processed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                process_time=process_time)
    
    return response

# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception", 
                path=request.url.path,
                method=request.method,
                error=str(exc))
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred"
        }
    )

# Include routers
app.include_router(auth.router)
app.include_router(analysis.router)

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "code-review-agent",
        "version": "1.0.0"
    }

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Code Review Agent API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.log_level == "DEBUG"
    )