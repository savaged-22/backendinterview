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
COPY gateway-service/requirements.txt ./gateway-service/requirements.txt
COPY db/prisma/schema.prisma ./db/prisma/schema.prisma

# Install Python packages
RUN pip install --no-cache-dir -r gateway-service/requirements.txt

# Generate Prisma client
RUN prisma generate --schema=db/prisma/schema.prisma

# Copy source code
COPY db/ ./db/
COPY gateway-service/app/ ./gateway-service/app/

# Set working directory to gateway-service for running the app
WORKDIR /app/gateway-service

EXPOSE 8000

ENV PYTHONPATH=/app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]