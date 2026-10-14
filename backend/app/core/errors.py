"""Erros de domínio e resposta padronizada (doc 06 §1, RFC 9457 simplificado)."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import current_request_id, get_logger

log = get_logger(__name__)


class ProblemError(Exception):
    def __init__(
        self, status: int, type_: str, title: str, detail: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(title)
        self.status, self.type, self.title, self.detail = status, type_, title, detail
        self.headers = headers or {}


def _body(status: int, type_: str, title: str, detail: str | None) -> dict[str, object]:
    body: dict[str, object] = {"type": type_, "title": title, "status": status}
    if detail:
        body["detail"] = detail
    body["request_id"] = current_request_id()
    return body


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemError)
    async def _problem(_: Request, exc: ProblemError) -> JSONResponse:
        return JSONResponse(
            _body(exc.status, exc.type, exc.title, exc.detail), exc.status, headers=exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Só campo e mensagem; nunca o valor recebido (pode conter senha).
        fields = [
            {"field": ".".join(str(p) for p in e.get("loc", ())[1:]), "message": e.get("msg", "")}
            for e in exc.errors()
        ]
        body = _body(422, "validation_error", "Dados inválidos", None)
        body["errors"] = fields
        return JSONResponse(body, 422)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.error("erro inesperado", extra={"error_type": type(exc).__name__})
        return JSONResponse(_body(500, "internal_error", "Erro interno", None), 500)
