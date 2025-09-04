#!/bin/bash

# Production deployment script for Code Review Agent
set -e

echo "🚀 Deploying Code Review Agent to Production..."

# Configuration
REGISTRY=${REGISTRY:-"ghcr.io/youruser"}
IMAGE_NAME="code-review-agent"
TAG=${TAG:-"latest"}
FULL_IMAGE="$REGISTRY/$IMAGE_NAME:$TAG"

# Check if required environment variables are set
required_vars=("GROQ_API_KEY" "GITHUB_CLIENT_ID" "GITHUB_CLIENT_SECRET" "DATABASE_URL" "REDIS_URL")
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ Required environment variable $var is not set"
        exit 1
    fi
done

# Build Docker image
echo "🐳 Building Docker image: $FULL_IMAGE"
docker build -t $IMAGE_NAME:$TAG .
docker tag $IMAGE_NAME:$TAG $FULL_IMAGE

# Push to registry (if registry is provided)
if [ "$REGISTRY" != "local" ]; then
    echo "📤 Pushing to registry: $REGISTRY"
    docker push $FULL_IMAGE
fi

# Deploy with Docker Compose
echo "🎯 Deploying services..."
if [ -f "deploy/docker-compose.prod.yml" ]; then
    export REGISTRY
    export TAG
    docker-compose -f deploy/docker-compose.prod.yml up -d
else
    docker-compose up -d
fi

# Wait for services to be healthy
echo "⏳ Waiting for services to be ready..."
timeout=120
counter=0

while [ $counter -lt $timeout ]; do
    if curl -f http://localhost/health &>/dev/null || curl -f http://localhost:8000/health &>/dev/null; then
        echo "✅ Services are healthy!"
        break
    fi
    sleep 5
    counter=$((counter + 5))
    echo "Waiting... ($counter/$timeout seconds)"
done

if [ $counter -ge $timeout ]; then
    echo "⚠️  Timeout waiting for services to be healthy"
    echo "Check logs with: docker-compose logs"
    exit 1
fi

# Show deployment info
echo ""
echo "✅ Deployment complete!"
echo "🔗 Application available at: http://localhost"
echo "📚 API docs: http://localhost/docs"
echo "📊 Health check: http://localhost/health"
echo ""
echo "Useful commands:"
echo "• View logs: docker-compose logs -f"
echo "• Scale workers: docker-compose up -d --scale worker=4"
echo "• Stop services: docker-compose down"