from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.templating import Jinja2Templates

_log = logging.getLogger(__name__)


def _prefer_html_response(request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    if "text/html" in accept:
        return True
    if "application/json" in accept:
        return False
    return True


def _detail_string(detail: Any) -> str:
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list | tuple) and detail and isinstance(detail[0], dict):
        err = detail[0].get("msg") or detail[0].get("type")
        return str(err) if err is not None else "Request could not be processed."
    try:
        return str(detail)
    except Exception:  # noqa: BLE001
        return "Request could not be processed."


async def _http_exc_response(
    request: Request,
    exc: StarletteHTTPException,
    *,
    templates: Jinja2Templates,
    get_settings_fn: Callable[[], Any],
) -> HTMLResponse | JSONResponse:
    settings = get_settings_fn()
    detail = _detail_string(exc.detail)
    if _prefer_html_response(request):
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "settings": settings,
                "status_code": exc.status_code,
                "title": _http_error_title(exc.status_code),
                "message": detail,
                "debug_detail": None,
                "request_path": request.url.path,
            },
            status_code=exc.status_code,
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": jsonable_encoder(exc.detail)})


def register_exception_handlers(
    app: FastAPI,
    *,
    templates: Jinja2Templates,
    get_settings_fn: Callable[[], Any],
) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException) -> HTMLResponse | JSONResponse:
        return await _http_exc_response(request, exc, templates=templates, get_settings_fn=get_settings_fn)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> HTMLResponse | JSONResponse:
        settings = get_settings_fn()
        _log.exception("Unhandled error for %s %s", request.method, request.url.path)
        if _prefer_html_response(request):
            debug_detail: str | None = None
            if getattr(settings, "debug", False):
                debug_detail = f"{type(exc).__name__}: {exc}"
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "settings": settings,
                    "status_code": 500,
                    "title": "Something went wrong",
                    "message": "An unexpected error occurred. Please try again later or use the links below.",
                    "debug_detail": debug_detail,
                    "request_path": request.url.path,
                },
                status_code=500,
            )
        return JSONResponse(status_code=500, content={"detail": "Internal server error."})


def _http_error_title(status_code: int) -> str:
    if status_code == 404:
        return "Page not found"
    if status_code == 403:
        return "Access denied"
    if status_code == 502:
        return "Upstream service error"
    if status_code == 503:
        return "Service unavailable"
    return "Request error"
