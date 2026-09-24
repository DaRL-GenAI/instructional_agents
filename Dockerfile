# Multi-stage build for Instructional Agents API
FROM python:3.11-slim as base

# Install system dependencies including LaTeX and Node.js
RUN apt-get update && apt-get install -y \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-latex-recommended \
    texlive-fonts-extra \
    ffmpeg \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 20 LTS (for pptxgenjs PPTX generation)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js global dependencies for PPTX generation
RUN npm install -g pptxgenjs react-icons react react-dom sharp

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p exp catalog eval

# Expose port
EXPOSE 8000

# Health check (using curl or wget)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run the API server
CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000"]

