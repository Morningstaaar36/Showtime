# Showtime API image. Build context: repository root (see docker-compose.yml).
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv UV_LINK_MODE=copy PYTHONPATH=/app MPLBACKEND=Agg
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
 && curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-27.3.1.tgz \
    | tar -xz --strip-components=1 -C /usr/local/bin docker/docker \
 && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/uv
WORKDIR /app/api
COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
WORKDIR /app
COPY api /app/api
COPY plugins /app/plugins
COPY config /app/config
COPY sim/plugins/registry.json /app/sim/plugins/registry.json
ENV PATH=/opt/venv/bin:$PATH
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health',timeout=4)"
CMD ["uvicorn", "api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
