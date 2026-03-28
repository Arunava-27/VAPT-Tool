# Production Dockerfile for Metasploit worker
FROM metasploitframework/metasploit-framework:latest as msf-base

# Build stage — python:3.11-slim already has ca-certificates
FROM python:3.11-slim

# Copy Metasploit framework from base image (msfconsole lives inside the framework dir)
COPY --from=msf-base /usr/src/metasploit-framework /usr/src/metasploit-framework

# Create non-root user
RUN groupadd -r msfworker && useradd -r -g msfworker msfworker

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
ENV MSF_RPC_HOST=127.0.0.1
ENV MSF_RPC_PORT=55553
ENV MSF_PATH=/usr/src/metasploit-framework

# Change ownership
RUN chown -R msfworker:msfworker /app

# Note: May need to run as root or with elevated permissions for some exploits
USER msfworker

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD celery -A app.tasks inspect ping -d celery@$HOSTNAME || exit 1

# Run celery worker
CMD ["celery", "-A", "app.tasks", "worker", "--loglevel=info", "--concurrency=1"]
