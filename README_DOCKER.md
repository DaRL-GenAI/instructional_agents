# Docker 部署指南

## 快速开始

### 1. 准备环境变量

创建 `.env` 文件：

```bash
OPENAI_API_KEY=your_api_key_here
API_PORT=8000
```

### 2. 构建和启动

```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f api
```

### 3. 访问服务

- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health
- 前端界面：打开 `frontend/index.html`（需要配置 API 地址）

## 目录结构

```
.
├── Dockerfile              # Docker 镜像定义
├── docker-compose.yml      # Docker Compose 配置
├── .dockerignore          # Docker 忽略文件
├── requirements.txt       # Python 依赖
├── api_server.py         # FastAPI 服务器
├── .env                  # 环境变量（不提交到 Git）
├── exp/                  # 生成的结果（挂载为 Volume）
├── catalog/              # Catalog 文件（挂载为 Volume）
└── eval/                 # 评估结果（挂载为 Volume）
```

## 数据持久化

以下目录通过 Volume 挂载，数据会持久化到宿主机：

- `./exp` → `/app/exp`：生成的课程材料
- `./catalog` → `/app/catalog`：Catalog 文件
- `./eval` → `/app/eval`：评估结果

## 常用命令

```bash
# 启动服务
docker-compose up -d

# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 查看日志
docker-compose logs -f

# 进入容器
docker-compose exec api bash

# 重建镜像（代码更新后）
docker-compose build --no-cache
docker-compose up -d

# 清理（删除容器和镜像）
docker-compose down --rmi all
```

## 配置说明

### docker-compose.yml

```yaml
services:
  api:
    build: .                    # 使用当前目录的 Dockerfile
    ports:
      - "${API_PORT:-8000}:8000"  # 端口映射
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}  # 从 .env 读取
    volumes:
      - ./exp:/app/exp          # 数据持久化
    restart: unless-stopped     # 自动重启
```

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| OPENAI_API_KEY | OpenAI API 密钥 | 必填 |
| API_PORT | API 服务端口 | 8000 |

## 生产环境部署

### 1. 安全配置

修改 `docker-compose.yml`：

```yaml
services:
  api:
    # ... 其他配置
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    # 限制资源
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
```

### 2. 使用反向代理

推荐使用 Nginx 作为反向代理：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 3. 使用 HTTPS

使用 Let's Encrypt 或类似服务配置 SSL 证书。

## 故障排查

### 查看容器状态

```bash
docker-compose ps
```

### 查看容器日志

```bash
docker-compose logs api
docker-compose logs -f api  # 实时跟踪
```

### 检查容器资源使用

```bash
docker stats instructional_agents_api
```

### 进入容器调试

```bash
docker-compose exec api bash
# 在容器内
python -c "import os; print(os.environ.get('OPENAI_API_KEY'))"
```

### 常见问题

1. **端口被占用**
   ```bash
   # 修改 .env 中的 API_PORT
   API_PORT=8001
   ```

2. **权限问题**
   ```bash
   # 确保目录有写权限
   chmod -R 755 exp catalog eval
   ```

3. **LaTeX 编译失败**
   - 检查容器内是否有 pdflatex：`docker-compose exec api which pdflatex`
   - 查看编译日志：`exp/{exp_name}/.cache/`

4. **内存不足**
   - LaTeX 编译需要较多内存
   - 增加 Docker 内存限制或使用更大的实例

## 更新和维护

### 更新代码

```bash
# 1. 拉取最新代码
git pull

# 2. 重建镜像
docker-compose build

# 3. 重启服务
docker-compose up -d
```

### 备份数据

```bash
# 备份生成的结果
tar -czf exp_backup_$(date +%Y%m%d).tar.gz exp/

# 备份 Catalog
tar -czf catalog_backup_$(date +%Y%m%d).tar.gz catalog/
```

### 清理旧数据

```bash
# 清理旧的实验结果（谨慎操作）
find exp/ -type d -mtime +30 -exec rm -rf {} \;
```

## 性能优化

1. **使用多阶段构建**：减少镜像大小
2. **缓存依赖**：优化 Dockerfile 层顺序
3. **资源限制**：防止单个任务占用过多资源
4. **并发控制**：限制同时运行的任务数

## 监控

### 健康检查

```bash
curl http://localhost:8000/health
```

### 任务状态

通过 API 查询任务状态，或查看日志。

## 迁移到其他服务器

1. **导出数据**
   ```bash
   tar -czf data_backup.tar.gz exp/ catalog/ eval/
   ```

2. **在新服务器上**
   ```bash
   # 复制文件
   scp data_backup.tar.gz user@new-server:/path/
   scp docker-compose.yml .env user@new-server:/path/
   
   # 解压数据
   tar -xzf data_backup.tar.gz
   
   # 启动服务
   docker-compose up -d
   ```

## 支持

如有问题，请查看：
- API 文档：`API_DOCUMENTATION.md`
- 主 README：`README.md`
- 项目 Issues

