FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project source
COPY pyproject.toml .
COPY server/ ./server/
COPY dashboard/ ./dashboard/
COPY advanced_multimarket_env.py .
COPY advanced_baseline_agents.py .
COPY advanced_evaluation_framework.py .
COPY bloomberg_adapter.py .
COPY inference.py .
COPY openenv.yaml .

# Install the package in editable mode so openev.server.* imports work
RUN pip install --no-cache-dir -e .

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=5 \
    CMD curl -f http://localhost:7860/health || exit 1

# Run server — entry point is server/app.py
CMD ["python", "-m", "uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860"]
