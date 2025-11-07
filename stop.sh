#!/bin/bash

# Instructional Agents 停止脚本

echo "🛑 Stopping Instructional Agents..."

# 检查 docker-compose (支持 v1 和 v2)
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
elif docker-compose version &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
else
    echo "❌ docker-compose is not installed."
    exit 1
fi

$DOCKER_COMPOSE down

echo "✅ Service stopped"

