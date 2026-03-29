# Multi-stage build for production
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and build wheels
WORKDIR /wheels
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir=/wheels -r requirements.txt

# Final stage
FROM python:3.11-slim

# Install nmap and minimal dependencies
RUN apt-get update && apt-get install -y \
    nmap \
    libpq5 \
    iproute2 \
    libcap2-bin \
    && rm -rf /var/lib/apt/lists/*

# Grant nmap raw-socket capability so non-root workers can run ICMP/raw probes
RUN setcap cap_net_raw,cap_net_admin+eip /usr/bin/nmap

# Create non-root user
RUN groupadd -r nmapworker && useradd -r -g nmapworker nmapworker

WORKDIR /app

# Copy wheels from builder
COPY --from=builder /wheels /wheels

# Install Python packages from wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/*.whl \
    && rm -rf /wheels

# Copy application code
COPY app/ app/
# base/ is provided at runtime via volume mount (./workers/base:/app/base)

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Change ownership
RUN chown -R nmapworker:nmapworker /app

# Run as root so nmap can use raw sockets (ICMP, ARP, OS detection) for VAPT scanning.
# The container is already isolated; Docker cap_add controls network access.

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD celery -A app.tasks inspect ping -d celery@$HOSTNAME || exit 1

CMD ["celery", "-A", "app.tasks", "worker", "--loglevel=info", "--concurrency=4", "-Q", "nmap"]
