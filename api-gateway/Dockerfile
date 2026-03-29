# Production Dockerfile for API Gateway
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Create wheels
WORKDIR /wheels
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir=/wheels -r requirements.txt

# Final stage
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r apigateway && useradd -r -g apigateway apigateway

WORKDIR /app

# Copy wheels and install
COPY --from=builder /wheels /wheels
COPY --from=builder /wheels/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r /tmp/requirements.txt \
    && rm -rf /wheels /tmp/requirements.txt

# Copy application and migration scripts
COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini alembic.ini
COPY init_db.py init_db.py
COPY entrypoint.sh entrypoint.sh

# Set environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Change ownership
RUN chown -R apigateway:apigateway /app \
    && chmod +x /app/entrypoint.sh

# Switch to non-root user
USER apigateway

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run entrypoint (runs init_db + alembic, then starts uvicorn)
CMD ["/app/entrypoint.sh"]
