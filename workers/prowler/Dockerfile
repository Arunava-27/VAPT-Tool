# Production Dockerfile for Prowler worker
# Prowler is a pure Python tool — no system packages needed
FROM python:3.11-slim

# Create non-root user
RUN groupadd -r prowlerworker && useradd -r -g prowlerworker prowlerworker

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ app/
# base/ is provided at runtime via volume mount (./workers/base:/app/base)

# Set environment
ENV PYTHONUNBUFFERED=1
ENV AWS_DEFAULT_REGION=us-east-1

# Change ownership
RUN chown -R prowlerworker:prowlerworker /app

# Switch to non-root user
USER prowlerworker

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD celery -A app.tasks inspect ping -d celery@$HOSTNAME || exit 1

# Run celery worker
CMD ["celery", "-A", "app.tasks", "worker", "--loglevel=info", "--concurrency=1", "-Q", "prowler"]
