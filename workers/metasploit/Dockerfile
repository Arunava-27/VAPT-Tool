# Production Dockerfile for Metasploit worker
FROM metasploitframework/metasploit-framework:latest as msf-base

# Build stage
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user (but Metasploit may need elevated permissions)
RUN groupadd -r msfworker && useradd -r -g msfworker msfworker

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ app/
COPY ../base/ /app/base/

# Set environment
ENV PYTHONUNBUFFERED=1
ENV MSF_RPC_HOST=127.0.0.1
ENV MSF_RPC_PORT=55553

# Change ownership
RUN chown -R msfworker:msfworker /app

# Note: May need to run as root or with elevated permissions for some exploits
USER msfworker

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD celery -A app.tasks inspect ping -d celery@$HOSTNAME || exit 1

# Run celery worker
CMD ["celery", "-A", "app.tasks", "worker", "--loglevel=info", "--concurrency=1"]
