# Showtime API image. Build context: repository root (see docker-compose.yml).
FROM python:3.12-slim AS base
ARG TARGETARCH
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv UV_LINK_MODE=copy PYTHONPATH=/app MPLBACKEND=Agg
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
 && case "$TARGETARCH" in amd64) docker_arch=x86_64 ;; arm64) docker_arch=aarch64 ;; *) exit 1 ;; esac \
 && curl -fsSL "https://download.docker.com/linux/static/stable/${docker_arch}/docker-27.3.1.tgz" \
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
COPY sim /app/sim
# the entrypoint drops to the owner of the mounted runs/ folder (the host user) with the Docker
# socket's group; logs/ is written by that user
COPY api/entrypoint.sh /usr/local/bin/showtime-entrypoint
RUN mkdir -p /app/logs && chmod 1777 /app/logs && chmod 755 /usr/local/bin/showtime-entrypoint
ENV PATH=/opt/venv/bin:$PATH
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=12 CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/v1/templates',timeout=4)"
ENTRYPOINT ["/usr/local/bin/showtime-entrypoint"]
CMD ["uvicorn", "api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
