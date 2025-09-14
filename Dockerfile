# Multi-stage build for production deployment
FROM python:3.12-slim AS builder

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

# Set working directory
WORKDIR /app

# Copy dependency files and source code
COPY pyproject.toml README.md ./
COPY evently_booking_platform/ ./evently_booking_platform/
COPY main.py ./

# Create virtual environment and install dependencies
RUN uv venv /app/.venv
RUN uv pip install --python /app/.venv/bin/python -e .

# Production stage
FROM python:3.12-slim AS production

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set working directory
WORKDIR /app

# Copy virtual environment and application code from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/evently_booking_platform/ ./evently_booking_platform/
COPY --from=builder /app/main.py ./

# Change ownership to non-root user
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Expose port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1

# Run the application
CMD ["python", "-m", "uvicorn", "evently_booking_platform.main:app", "--host", "0.0.0.0", "--port", "3000"]