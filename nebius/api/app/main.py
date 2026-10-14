"""FastAPI application: REST + SSE under /api/v1, OpenAPI docs at /api/docs."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from api.app import errors
from api.app.routes_agents import router as agents_router
from api.app.routes_autopilot import router as autopilot_router
from api.app.routes_core import router as core_router
from api.app.routes_places import router as places_router
from api.app.routes_plan import router as plan_router
from api.app.routes_projects import router as projects_router
from api.app.routes_runs import router as runs_router
from api.app.state import AppState, build_state
from api.core.settings import Settings, get_settings

log = logging.getLogger("showtime.api")


class JsonFormatter(logging.Formatter):
    """One JSON object per line (request id and session id when present)."""

    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("request_id", "session_id", "path", "status", "ms"):
            if hasattr(record, key):
                data[key] = getattr(record, key)
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)[-2000:]
        return json.dumps(data)


def setup_logging(settings: Settings) -> None:
    """JSON logs to stderr and logs/api.log (rotated at 20 MB)."""
    root = logging.getLogger()
    if any(getattr(h, "_showtime", False) for h in root.handlers):
        return
    root.setLevel(settings.log_level)
    fmt = JsonFormatter()
    logs = settings.root_dir / "logs"
    logs.mkdir(exist_ok=True)
    fh = RotatingFileHandler(logs / "api.log", maxBytes=20_000_000, backupCount=2)
    fh.setFormatter(fmt)
    fh._showtime = True  # type: ignore[attr-defined]
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    sh._showtime = True  # type: ignore[attr-defined]
    root.addHandler(fh)
    root.addHandler(sh)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def create_app(state: AppState | None = None, settings: Settings | None = None) -> FastAPI:
    """Build the app. Tests pass a prepared state."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        setup_logging(settings)
        if state is None:
            app.state.showtime = build_state(settings)
        else:
            app.state.showtime = state
        st: AppState = app.state.showtime
        _mount_plugin_routes(app, st)
        if st.sessions is None:
            from api.orchestrator.session import SessionManager

            st.sessions = SessionManager(st)
        log.info("Showtime API ready", extra={"path": str(settings.root_dir)})
        yield
        await st.runner.close()

    app = FastAPI(
        title="Showtime API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.add_middleware(GZipMiddleware, minimum_size=2048, compresslevel=5)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin, "http://127.0.0.1:5173", "http://localhost:4173"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )

    @app.middleware("http")
    async def request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        t0 = time.perf_counter()
        response = await call_next(request)
        ms = round((time.perf_counter() - t0) * 1000, 1)
        response.headers["x-request-id"] = rid
        if request.url.path.startswith("/api/") and not request.url.path.endswith("/events"):
            log.info(
                "%s %s",
                request.method,
                request.url.path,
                extra={
                    "request_id": rid,
                    "path": request.url.path,
                    "status": response.status_code,
                    "ms": ms,
                },
            )
        return response

    errors.install(app)
    app.include_router(core_router)
    app.include_router(projects_router)
    app.include_router(plan_router)
    app.include_router(runs_router)
    app.include_router(agents_router)
    app.include_router(places_router)
    app.include_router(autopilot_router)
    return app


def _mount_plugin_routes(app: FastAPI, st: AppState) -> None:
    for pid, status in st.host.statuses.items():
        if not (status.enabled and status.healthy):
            continue
        plugin = st.host.pm.get_plugin(pid)
        fn = getattr(plugin, "register_routes", None) if plugin else None
        if fn is None:
            continue
        try:
            router = fn(plugin_id=pid)
            if router is not None:
                app.include_router(router, prefix=f"/api/v1/plugins/{pid}")
        except Exception as exc:
            st.host.mark_unhealthy(pid, f"routes: {exc}")


app = create_app()
