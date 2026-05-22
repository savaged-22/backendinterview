FROM python:3.11-slim

WORKDIR /app

# Install system dependencies needed for Prisma engines
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    openssl \
    ca-certificates \
    libatomic1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and prisma schema first for caching
COPY worker/requirements.txt ./worker/requirements.txt
COPY db/prisma/schema.prisma ./db/prisma/schema.prisma

# Install Python packages
RUN pip install --no-cache-dir -r worker/requirements.txt

# Generate Prisma client
RUN prisma generate --schema=db/prisma/schema.prisma

# Copy source code
COPY db/ ./db/
COPY worker/app/ ./worker/app/

# Set working directory to worker for running the script
WORKDIR /app/worker

ENV PYTHONPATH=/app

CMD ["python", "app/main.py"]
