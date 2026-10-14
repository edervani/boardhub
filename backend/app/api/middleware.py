"""Middlewares: request_id, CSRF (SEC-07) e cabeçalhos de segurança (SEC-16)."""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.api.deps import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from app.core.logging import new_request_id
from app.core.security import tokens_equal

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cache-Control": "no-store",
}

Next = Callable[[Request], Awaitable[Response]]


def install_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def csrf_and_headers(request: Request, call_next: Next) -> Response:
        rid = new_request_id()
        if request.method not in SAFE_METHODS and request.cookies.get(SESSION_COOKIE):
            cookie = request.cookies.get(CSRF_COOKIE, "")
            header = request.headers.get(CSRF_HEADER, "")
            if not cookie or not header or not tokens_equal(cookie, header):
                response: Response = JSONResponse(
                    {"type": "csrf_failed", "title": "Requisição recusada",
                     "detail": "Recarregue a página e tente de novo.", "status": 403,
                     "request_id": rid},
                    403,
                )
            else:
                response = await call_next(request)
        else:
            response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        response.headers["X-Request-ID"] = rid
        return response
