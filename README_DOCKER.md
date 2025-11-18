<div align="right" style="margin-bottom: 20px; margin-top: 10px;">
  <button onclick="switchLanguage('en')" id="lang-en" style="padding: 8px 16px; margin: 0 4px; border: 2px solid #14b8a6; background: #14b8a6; color: white; border-radius: 6px; cursor: pointer; font-weight: 600; transition: all 0.3s ease;">🇺🇸 English</button>
  <button onclick="switchLanguage('zh')" id="lang-zh" style="padding: 8px 16px; margin: 0 4px; border: 2px solid #e2e8f0; background: white; color: #64748b; border-radius: 6px; cursor: pointer; font-weight: 600; transition: all 0.3s ease;">🇨🇳 中文</button>
</div>

<script>
function switchLanguage(lang) {
    localStorage.setItem('preferredLanguage', lang);
    if (lang === 'en') {
        window.location.href = window.location.pathname.replace('.zh.md', '.md');
    } else {
        window.location.href = window.location.pathname.replace('.md', '.zh.md');
    }
}
document.addEventListener('DOMContentLoaded', function() {
    const savedLang = localStorage.getItem('preferredLanguage') || 'en';
    if (savedLang === 'zh' && !window.location.pathname.includes('.zh.md')) {
        window.location.href = window.location.pathname.replace('.md', '.zh.md');
    }
});
</script>

<style>
button:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}
</style>

# Docker Deployment Guide

## Quick Start

### 1. Prepare Environment Variables

Create `.env` file:

```bash
OPENAI_API_KEY=your_api_key_here
API_PORT=8000
```

### 2. Build and Start

```bash
# Build image
docker-compose build

# Start service
docker-compose up -d

# View logs
docker-compose logs -f api
```

### 3. Access Service

- API Documentation: http://localhost:8000/docs
- Health Check: http://localhost:8000/health
- Frontend Interface: Open `frontend/index.html` (need to configure API address)

## Directory Structure

```
.
├── Dockerfile              # Docker image definition
├── docker-compose.yml      # Docker Compose configuration
├── .dockerignore          # Docker ignore file
├── requirements.txt       # Python dependencies
├── api_server.py         # FastAPI server
├── .env                  # Environment variables (not committed to Git)
├── exp/                  # Generated results (mounted as Volume)
├── catalog/              # Catalog files (mounted as Volume)
└── eval/                 # Evaluation results (mounted as Volume)
```

## Data Persistence

The following directories are mounted as volumes, data will persist on the host:

- `./exp` → `/app/exp`: Generated course materials
- `./catalog` → `/app/catalog`: Catalog files
- `./eval` → `/app/eval`: Evaluation results

## Common Commands

```bash
# Start service
docker-compose up -d

# Stop service
docker-compose down

# Restart service
docker-compose restart

# View logs
docker-compose logs -f

# Enter container
docker-compose exec api bash

# Rebuild image (after code updates)
docker-compose build --no-cache
docker-compose up -d

# Clean up (remove containers and images)
docker-compose down --rmi all
```

## Configuration

### docker-compose.yml

```yaml
services:
  api:
    build: .                    # Use Dockerfile in current directory
    ports:
      - "${API_PORT:-8000}:8000"  # Port mapping
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}  # Read from .env
    volumes:
      - ./exp:/app/exp          # Data persistence
    restart: unless-stopped     # Auto restart
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| OPENAI_API_KEY | OpenAI API key | Required |
| API_PORT | API service port | 8000 |

## Production Deployment

### 1. Security Configuration

Modify `docker-compose.yml`:

```yaml
services:
  api:
    # ... other configurations
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    # Resource limits
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
```

### 2. Use Reverse Proxy

Recommended to use Nginx as reverse proxy:

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

### 3. Use HTTPS

Configure SSL certificate using Let's Encrypt or similar service.

## Troubleshooting

### Check Container Status

```bash
docker-compose ps
```

### View Container Logs

```bash
docker-compose logs api
docker-compose logs -f api  # Real-time tracking
```

### Check Container Resource Usage

```bash
docker stats instructional_agents_api
```

### Enter Container for Debugging

```bash
docker-compose exec api bash
# Inside container
python -c "import os; print(os.environ.get('OPENAI_API_KEY'))"
```

### Common Issues

1. **Port Already in Use**
   ```bash
   # Modify API_PORT in .env
   API_PORT=8001
   ```

2. **Permission Issues**
   ```bash
   # Ensure directories have write permissions
   chmod -R 755 exp catalog eval
   ```

3. **LaTeX Compilation Failed**
   - Check if pdflatex exists in container: `docker-compose exec api which pdflatex`
   - View compilation logs: `exp/{exp_name}/.cache/`

4. **Insufficient Memory**
   - LaTeX compilation requires more memory
   - Increase Docker memory limit or use larger instance

## Updates and Maintenance

### Update Code

```bash
# 1. Pull latest code
git pull

# 2. Rebuild image
docker-compose build

# 3. Restart service
docker-compose up -d
```

### Backup Data

```bash
# Backup generated results
tar -czf exp_backup_$(date +%Y%m%d).tar.gz exp/

# Backup Catalog
tar -czf catalog_backup_$(date +%Y%m%d).tar.gz catalog/
```

### Clean Old Data

```bash
# Clean old experiment results (use with caution)
find exp/ -type d -mtime +30 -exec rm -rf {} \;
```

## Performance Optimization

1. **Use Multi-stage Build**: Reduce image size
2. **Cache Dependencies**: Optimize Dockerfile layer order
3. **Resource Limits**: Prevent single task from consuming too many resources
4. **Concurrency Control**: Limit number of concurrent tasks

## Monitoring

### Health Check

```bash
curl http://localhost:8000/health
```

### Task Status

Query task status through API or view logs.

## Migration to Another Server

1. **Export Data**
   ```bash
   tar -czf data_backup.tar.gz exp/ catalog/ eval/
   ```

2. **On New Server**
   ```bash
   # Copy files
   scp data_backup.tar.gz user@new-server:/path/
   scp docker-compose.yml .env user@new-server:/path/
   
   # Extract data
   tar -xzf data_backup.tar.gz
   
   # Start service
   docker-compose up -d
   ```

## Support

For issues, please check:
- API Documentation: `API_DOCUMENTATION.md`
- Main README: `README.md`
- Project Issues

