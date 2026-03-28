# Production Dockerfile for Trivy worker
FROM ghcr.io/aquasecurity/trivy:latest as trivy-bin

# Build stage - python:3.11-slim already includes ca-certificates
FROM python:3.11-slim

# Copy Trivy binary (self-contained, no additional OS deps needed)
COPY --from=trivy-bin /usr/local/bin/trivy /usr/local/bin/trivy

# Create non-root user
RUN groupadd -r trivyworker && useradd -r -g trivyworker trivyworker

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ app/
# base/ is provided at runtime via volume mount (./workers/base:/app/base)

# Create cache directory
RUN mkdir -p /tmp/trivy-cache && chown -R trivyworker:trivyworker /tmp/trivy-cache

# Set environment
ENV PYTHONUNBUFFERED=1
ENV TRIVY_CACHE_DIR=/tmp/trivy-cache

# Change ownership
RUN chown -R trivyworker:trivyworker /app

# Switch to non-root user
USER trivyworker

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD celery -A app.tasks inspect ping -d celery@$HOSTNAME || exit 1

# Run celery worker
CMD ["celery", "-A", "app.tasks", "worker", "--loglevel=info", "--concurrency=2", "-Q", "trivy"]
