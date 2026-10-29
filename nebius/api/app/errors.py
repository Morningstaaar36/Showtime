"""Consistent error bodies: {code, message, hint, details}."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.adapters.llm import BudgetExceeded
from api.core.plan import PlanConflict, PlanError
from api.core.venue_ops import PatchError
from api.orchestrator.projects import NotFound
from api.orchestrator.session import TooManySessions

log = logging.getLogger("showtime.api")
_HTTP_CODES = {404: "not_found", 405: "method_not_allowed", 413: "too_large"}


class ApiException(Exception):
    """Raise from routes to return a designed error."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        hint: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.hint = hint
        self.details = details or {}


def _body(
    code: str, message: str, hint: str | None = None, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {"code": code, "message": message, "hint": hint, "details": details or {}}


def response(status: int, code: str, message: str, hint: str | None = None) -> JSONResponse:
    """A designed error response, for code that answers before a route runs (middleware)."""
    return JSONResponse(_body(code, message, hint), status)


def install(app: FastAPI) -> None:
    """Register exception handlers."""

    @app.exception_handler(ApiException)
    async def _api(_: Request, exc: ApiException) -> JSONResponse:
        return JSONResponse(_body(exc.code, exc.message, exc.hint, exc.details), exc.status)

    @app.exception_handler(NotFound)
    async def _nf(_: Request, exc: NotFound) -> JSONResponse:
        return JSONResponse(_body("not_found", str(exc)), 404)

    @app.exception_handler(PatchError)
    async def _patch(_: Request, exc: PatchError) -> JSONResponse:
        return JSONResponse(
            _body(
                "invalid_edit",
                exc.problems[0] if exc.problems else str(exc),
                "Change the edit and try again.",
                {"problems": exc.problems, "op_index": exc.op_index},
            ),
            422,
        )

    @app.exception_handler(PlanError)
    async def _plan(_: Request, exc: PlanError) -> JSONResponse:
        return JSONResponse(
            _body(
                "invalid_plan",
                str(exc),
                "Correct the reported constraints, actions, or resources and retry.",
                {"issues": [i.model_dump(mode="json") for i in exc.issues]},
            ),
            422,
        )

    @app.exception_handler(PlanConflict)
    async def _conflict(_: Request, exc: PlanConflict) -> JSONResponse:
        return JSONResponse(_body("plan_version_conflict", str(exc)), 409)

    @app.exception_handler(TooManySessions)
    async def _busy(_: Request, exc: TooManySessions) -> JSONResponse:
        return JSONResponse(_body("too_many_sessions", str(exc), exc.hint), 429)

    @app.exception_handler(BudgetExceeded)
    async def _budget(_: Request, exc: BudgetExceeded) -> JSONResponse:
        # a model call refused by a budget that no route turned into its own message
        return JSONResponse(_body("budget", str(exc), "Try again when the budget allows."), 429)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        # unknown routes and wrong methods: same body shape as every other error
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        message = exc.detail if isinstance(exc.detail, str) else "The request failed."
        return JSONResponse(
            _body(code, message), exc.status_code, headers=getattr(exc, "headers", None)
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # a bug must still answer in the designed shape, without internals (logged instead)
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            _body(
                "internal_error",
                "Something went wrong on the server.",
                "Try again; if it keeps happening, check logs/api.log.",
            ),
            500,
        )

    @app.exception_handler(RequestValidationError)
    async def _val(_: Request, exc: RequestValidationError) -> JSONResponse:
        errs = [
            {"loc": [str(x) for x in e.get("loc", [])], "msg": e.get("msg", "")}
            for e in exc.errors()
        ]
        first = errs[0] if errs else {"loc": [], "msg": "invalid request"}
        return JSONResponse(
            _body(
                "invalid_request",
                f"{'.'.join(first['loc'][1:]) or 'request'}: {first['msg']}",
                details={"errors": errs},
            ),
            422,
        )


def llm_unavailable(llm: Any, message: str = "The language model isn't answering.") -> ApiException:
    """503 for a model that did not answer, with what to do for this provider and its state
    (a paused hosted model, a local model that is not running, a missing key)."""
    hint = getattr(llm, "unavailable_hint", None)
    return ApiException(503, "llm_unavailable", message, hint() if callable(hint) else None)
