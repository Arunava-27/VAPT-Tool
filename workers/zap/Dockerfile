# Multi-stage build for ZAP worker
FROM ghcr.io/zaproxy/zaproxy:stable as zap-base

# Final stage
FROM python:3.11-slim

# Copy ZAP and its bundled Java runtime from the ZAP image (avoids apt-get)
COPY --from=zap-base /zap /zap
COPY --from=zap-base /usr/lib/jvm /usr/lib/jvm
COPY --from=zap-base /usr/bin/java /usr/bin/java
COPY --from=zap-base /usr/bin/java /usr/local/bin/java

# Create non-root user
RUN groupadd -r zapworker && useradd -r -g zapworker zapworker

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ app/
# base/ is provided at runtime via volume mount (./workers/base:/app/base)

# Set environment
ENV PYTHONUNBUFFERED=1
ENV ZAP_PATH=/zap/zap.sh
ENV JAVA_HOME=/usr/lib/jvm/temurin-21-jdk-amd64
ENV PATH=$PATH:/usr/lib/jvm/temurin-21-jdk-amd64/bin

# Change ownership
RUN chown -R zapworker:zapworker /app

# Switch to non-root user
USER zapworker

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD celery -A app.tasks inspect ping -d celery@$HOSTNAME || exit 1

# Run celery worker
CMD ["celery", "-A", "app.tasks", "worker", "--loglevel=info", "--concurrency=2"]
