import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Settings:
    def __init__(self):
        # Database
        self.database_url = os.getenv('DATABASE_URL', 'postgresql://postgres:password@localhost:5432/code_review_db')
        
        # Redis
        self.redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
        self.redis_results_url = os.getenv('REDIS_RESULTS_URL', 'redis://localhost:6379/1')
        
        # GitHub OAuth
        self.github_client_id = os.getenv('GITHUB_CLIENT_ID')
        self.github_client_secret = os.getenv('GITHUB_CLIENT_SECRET')
        self.github_webhook_secret = os.getenv('GITHUB_WEBHOOK_SECRET')
        self.github_oauth_redirect_uri = os.getenv('GITHUB_OAUTH_REDIRECT_URI', 'http://localhost:8000/auth/callback')
        
        # JWT
        self.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-in-production')
        self.algorithm = os.getenv('ALGORITHM', 'HS256')
        self.access_token_expire_minutes = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', str(30 * 24 * 60)))  # 30 days
        
        # Groq API
        self.groq_api_key = os.getenv('GROQ_API_KEY')
        self.groq_model = os.getenv('GROQ_MODEL', 'mixtral-8x7b-32768')
        
        # Rate Limiting
        self.rate_limit_requests = int(os.getenv('RATE_LIMIT_REQUESTS', '100'))
        self.rate_limit_window = int(os.getenv('RATE_LIMIT_WINDOW', '3600'))  # 1 hour
        
        # Monitoring
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
        self.enable_metrics = os.getenv('ENABLE_METRICS', 'True').lower() == 'true'
        
        # Celery
        self.celery_broker_url = os.getenv('CELERY_BROKER_URL') or self.redis_url
        self.celery_result_backend = os.getenv('CELERY_RESULT_BACKEND') or self.redis_results_url

settings = Settings()