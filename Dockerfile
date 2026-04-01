FROM python:3.12-slim

# Install system dependencies needed for bcrypt compilation
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --create-home appuser

WORKDIR /app

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and install the package
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir .

# Create data directory for SQLite database
RUN mkdir -p /data && chown appuser:appuser /data

# Environment variables
ENV DATABASE_URL=sqlite+aiosqlite:////data/jira.db \
    PORT=8080 \
    HOST=0.0.0.0

EXPOSE 8080

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/rest/api/2/priority')" || exit 1

CMD ["python", "-m", "jira_emulator", "serve", "--host", "0.0.0.0", "--port", "8080"]
