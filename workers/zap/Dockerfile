# Multi-stage build for ZAP worker
FROM owasp/zap2docker-stable:latest as zap-base

# Final stage
FROM python:3.11-slim

# Install dependencies
RUN apt-get update && apt-get install -y \
    openjdk-17-jre-headless \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy ZAP from base image
COPY --from=zap-base /zap /zap

# Create non-root user
RUN groupadd -r zapworker && useradd -r -g zapworker zapworker

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ app/
COPY ../base/ /app/base/

# Set environment
ENV PYTHONUNBUFFERED=1
ENV ZAP_PATH=/zap/zap.sh

# Change ownership
RUN chown -R zapworker:zapworker /app

# Switch to non-root user
USER zapworker

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD celery -A app.tasks inspect ping -d celery@$HOSTNAME || exit 1

# Run celery worker
CMD ["celery", "-A", "app.tasks", "worker", "--loglevel=info", "--concurrency=2"]
