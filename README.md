# AI-Powered Code Review Agent

An intelligent GitHub pull request analysis system that provides comprehensive code reviews using large language models. Built with FastAPI, Celery, and LangGraph for production deployment.

## Features

- **Multi-Agent AI Analysis**: Security, performance, style, and logic review specialists
- **GitHub OAuth Integration**: Seamless authentication with automatic token management
- **Asynchronous Processing**: Celery task queue handles large repositories efficiently
- **Language Support**: Python, JavaScript, TypeScript, Java, Go, Rust, C++, and more
- **Production Ready**: Deployed on Railway with monitoring and scaling

## Architecture

```
FastAPI API ──→ Celery Workers ──→ AI Agents (Groq LLM)
    │                │                    │
    │                │                    │
    └── PostgreSQL   └── Redis       LangGraph Workflow
```

**Core Components:**
- **FastAPI**: REST API with GitHub OAuth
- **Celery**: Async task processing  
- **PostgreSQL**: User data and analysis results
- **Redis**: Task queue and caching
- **Groq LLM**: AI analysis via llama-3.3-70b-versatile

## Quick Start

### Prerequisites
- Python 3.11+, PostgreSQL, Redis
- GitHub OAuth App ([setup guide](https://docs.github.com/en/developers/apps/building-oauth-apps/creating-an-oauth-app))
- Groq API key from [console.groq.com](https://console.groq.com)

### Local Development

```bash
# Clone and setup
git clone https://github.com/yourusername/code-review-agent.git
cd code-review-agent
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Initialize database
alembic upgrade head

# Start services
uvicorn app.main:app --reload              # Terminal 1: API
celery -A app.tasks.analysis_tasks worker  # Terminal 2: Worker
```

### Docker Development

```bash
docker-compose up -d
```

## API Usage

### Authentication Flow

1. **Get OAuth URL**
```bash
curl https://your-app.railway.app/auth/login
```

2. **Complete GitHub OAuth** (follow returned URL)

3. **Use JWT token** for all subsequent requests:
```bash
curl -X POST "https://your-app.railway.app/api/v1/analyze-pr" \
     -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"repo_url": "https://github.com/owner/repo", "pr_number": 123}'
```

### Analysis Results

The system returns detailed analysis with:
- **Issue types**: security, performance, style, logic
- **Severity levels**: critical, high, medium, low
- **Actionable suggestions**: Specific fix recommendations
- **Impact assessment**: Potential consequences

Example response:
```json
{
  "analysis_summary": {
    "total_files": 1,
    "total_issues": 20,
    "critical_issues": 17,
    "high_issues": 1
  },
  "recommendations": [
    "🚨 CRITICAL: Address critical security vulnerabilities immediately",
    "🔐 Security: Run additional security scans"
  ]
}
```

## Deployment

### Railway (Recommended)

1. **Connect repository** to Railway
2. **Set environment variables**:
```
GROQ_API_KEY=your_groq_key
GITHUB_CLIENT_ID=your_oauth_client_id  
GITHUB_CLIENT_SECRET=your_oauth_secret
SECRET_KEY=your_jwt_secret
GITHUB_OAUTH_REDIRECT_URI=https://your-app.railway.app/auth/callback
```
3. **Update GitHub OAuth app** callback URL to your Railway domain
4. **Deploy automatically** via git push

**Cost**: ~$5-15/month (fits within Railway's free tier for light usage)

### Other Platforms

Compatible with any platform supporting:
- Docker containers
- PostgreSQL database  
- Redis instance
- Environment variables

## Configuration

| Variable | Description | Required |
|----------|-------------|----------|
| `GROQ_API_KEY` | Groq API key for LLM | Yes |
| `GITHUB_CLIENT_ID` | OAuth app client ID | Yes |
| `GITHUB_CLIENT_SECRET` | OAuth app secret | Yes |
| `SECRET_KEY` | JWT signing key | Yes |
| `DATABASE_URL` | PostgreSQL connection | Yes |
| `REDIS_URL` | Redis connection | Yes |

## Design Decisions

**Dual Authentication System**
- Users authenticate once via GitHub OAuth
- JWT tokens provide stateless API access (30-day expiry)
- GitHub tokens stored securely for automatic API access

**Multi-Agent Architecture** 
- Specialized AI agents instead of monolithic analysis
- Parallel processing for faster results
- Easier to maintain and improve individual analyzers

**Asynchronous Processing**
- Prevents API timeouts for large repositories
- Horizontal scaling capability
- Real-time progress monitoring

**Event Loop Management**
- Custom asyncio.run() wrapper for Celery compatibility
- Resolved worker conflicts in multi-process deployment

## Development

### Project Structure
```
app/
├── api/           # FastAPI routes (auth, analysis)
├── agents/        # AI analyzers and LangGraph workflow  
├── models/        # Database models (User, AnalysisTask)
├── services/      # Business logic (GitHub, auth, cache)
├── tasks/         # Celery task definitions
└── utils/         # Logging and monitoring
```

### Adding New Analyzers

1. Extend `BaseAnalyzer` in `app/agents/analyzer.py`
2. Add to LangGraph workflow in `app/agents/workflow.py`
3. Update smart routing logic

## Testing

### Prerequisites for Testing
```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov httpx

# Set up test environment
cp .env.example .env.test
# Edit .env.test with test database settings
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=app --cov-report=html

# Run specific test categories
pytest tests/test_api.py -v           # API endpoint tests
pytest tests/test_auth.py -v          # Authentication tests  
pytest tests/test_analyzers.py -v     # AI analyzer tests

# Run integration tests (requires running Redis/PostgreSQL)
pytest tests/integration/ -v
```

### Manual API Testing

**Test complete authentication flow:**
```bash
# 1. Get OAuth URL
curl https://code-review-api-production.up.railway.app/auth/login

# 2. Visit the oauth_url in browser, complete GitHub auth

# 3. Test authenticated endpoint
curl -X POST "https://code-review-api-production.up.railway.app/api/v1/analyze-pr" \
     -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"repo_url": "https://github.com/octocat/Hello-World", "pr_number": 1}'
```

### Test Environment Setup

```bash
# For local testing, start dependencies
docker-compose -f docker-compose.test.yml up -d redis postgres

# Run tests against local environment
TEST_DATABASE_URL=postgresql://test:test@localhost:5433/test_db pytest
```

## Future Improvements

**Near Term**
- **Enhanced line number detection**: Improve AI agents' ability to map issues to specific line numbers in code
- Enhanced prompt engineering based on usage feedback
- WebSocket real-time progress updates
- Configuration file support (ESLint, Prettier, etc.)

**Medium Term**  
- Custom rule engine for organization standards
- IDE plugins (VS Code, JetBrains)
- CI/CD pipeline integration

The system is production-ready and actively handles PR analysis workloads.

## Contributing

1. Fork repository and create feature branch
2. Follow existing code patterns and add tests
3. Submit PR with clear description

## License

MIT License - see [LICENSE](LICENSE) file.
