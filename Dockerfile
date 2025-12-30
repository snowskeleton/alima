# Use Python 3.11 slim image for smaller size
FROM python:3.14.2

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY cli.py .

# Create data directories
RUN mkdir -p /app/data/audiobooks/unassigned \
    /app/data/covers \
    /app/data/audible_auth \
    /app/data/temp \
    /app/data/db

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Run the application with Gunicorn + Uvicorn workers for production
# 4 workers is a good default for most single-server deployments
# Formula: (2 × CPU cores) + 1, adjust based on your server
CMD ["gunicorn", "app.main:app", "--workers", "4", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--access-logfile", "-", "--error-logfile", "-"]
