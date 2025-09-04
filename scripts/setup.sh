#!/bin/bash

# Setup script for Code Review Agent
set -e

echo "🚀 Setting up Code Review Agent..."

# Check if Python 3.11+ is installed
if command -v python3 &> /dev/null; then
    python_version=$(python3 --version 2>&1 | grep -o '[0-9]\+\.[0-9]\+' | head -1)
    required_version="3.11"
    
    if [[ $(echo "$python_version >= $required_version" | bc -l 2>/dev/null || echo "0") -eq 0 ]]; then
        echo "❌ Python 3.11 or higher is required. Current version: $python_version"
        exit 1
    fi
else
    echo "❌ Python 3 is not installed"
    exit 1
fi

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Copy environment file
if [ ! -f .env ]; then
    echo "📋 Creating environment file..."
    cp .env.example .env
    echo "⚠️  Please edit .env file with your API keys and configuration"
else
    echo "✅ .env file already exists"
fi

# Check if PostgreSQL is available
if command -v psql &> /dev/null; then
    echo "✅ PostgreSQL found"
else
    echo "⚠️  PostgreSQL not found. Please install PostgreSQL or use Docker"
fi

# Check if Redis is available
if command -v redis-cli &> /dev/null; then
    echo "✅ Redis found"
else
    echo "⚠️  Redis not found. Please install Redis or use Docker"
fi

# Initialize database (if DATABASE_URL is set)
if [ -f .env ]; then
    source .env
    if [ ! -z "$DATABASE_URL" ]; then
        echo "🗄️  Setting up database..."
        alembic upgrade head
    else
        echo "⚠️  DATABASE_URL not set in .env file"
    fi
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your API keys:"
echo "   - GROQ_API_KEY (from https://console.groq.com)"
echo "   - GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET"
echo "   - DATABASE_URL and REDIS_URL"
echo ""
echo "2. Start the services:"
echo "   • FastAPI: uvicorn app.main:app --reload"
echo "   • Worker:  celery -A app.tasks.analysis_tasks worker --loglevel=info"
echo ""
echo "3. Or use Docker: docker-compose up -d"
echo ""
echo "4. Visit http://localhost:8000/docs for API documentation"