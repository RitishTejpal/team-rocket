FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir uv
COPY pyproject.toml ./
COPY uv.lock ./

RUN uv pip install --system --no-cache -r pyproject.toml 2>/dev/null || \
    pip install --no-cache-dir \
        "beautifulsoup4>=4.14.3" \
        "fastapi>=0.135.2" \
        "groq>=1.1.2" \
        "lxml>=6.0.2" \
        "openai>=2.30.0" \
        "openenv-core>=0.2.2" \
        "pydantic>=2.12.5" \
        "pydantic-settings>=2.13.1" \
        "uvicorn>=0.42.0" \
        "requests>=2.33.0"

COPY . .

RUN mkdir -p SciCheck/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
 
CMD ["uvicorn", "server.main:scicheck_app", "--host", "0.0.0.0", "--port", "8000"]