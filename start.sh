#!/bin/bash

# Instructional Agents 启动脚本

echo "🚀 Starting Instructional Agents..."

# 检查 .env 文件
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from .env.example..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "✅ Please edit .env and add your OPENAI_API_KEY"
        exit 1
    else
        echo "OPENAI_API_KEY=your_key_here" > .env
        echo "API_PORT=8000" >> .env
        echo "✅ Created .env file. Please edit it and add your OPENAI_API_KEY"
        exit 1
    fi
fi

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# 检查 docker-compose (支持 v1 和 v2)
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
elif docker-compose version &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
else
    echo "❌ docker-compose is not installed. Please install docker-compose first."
    exit 1
fi

# 创建必要的目录
mkdir -p exp catalog eval

# 启动服务
echo "📦 Building and starting Docker containers..."
$DOCKER_COMPOSE up -d --build

# 等待服务启动
echo "⏳ Waiting for service to start..."
sleep 5

# 检查健康状态
echo "🔍 Checking service health..."
for i in {1..10}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "✅ Service is healthy!"
        echo ""
        echo "🌐 API Server: http://localhost:8000"
        echo "📚 API Docs: http://localhost:8000/docs"
        echo "💚 Health Check: http://localhost:8000/health"
        echo ""
echo "📝 To view logs: $DOCKER_COMPOSE logs -f"
echo "🛑 To stop: $DOCKER_COMPOSE down"
        exit 0
    fi
    sleep 2
done

echo "⚠️  Service may not be ready yet. Check logs with: $DOCKER_COMPOSE logs -f"
exit 1

