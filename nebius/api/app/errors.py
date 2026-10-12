"""Consistent error bodies: {code, message, hint, details}."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.core.plan import PlanConflict, PlanError
from api.core.venue_ops import PatchError
from api.orchestrator.projects import NotFound


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
