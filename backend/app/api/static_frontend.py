"""Serve o build do frontend (SPA) pelo próprio backend — só no modo nativo de teste (DT-022).

Desligado por padrão (`SERVE_FRONTEND_DIR` vazio). Mantém a mesma origem de `/api`, dispensando
nginx. Caminhos de `/api` nunca caem no fallback do SPA, e nada fora do diretório é entregue.
"""

import mimetypes
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response

# O Windows lê tipos MIME do registro, onde .js pode estar como text/plain (navegadores recusam
# módulos assim). Fixamos os tipos que o build do Vite usa.
_TYPES = {".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
          ".svg": "image/svg+xml", ".json": "application/json", ".map": "application/json",
          ".woff2": "font/woff2", ".ico": "image/x-icon", ".html": "text/html"}


def install_frontend(app: FastAPI, directory: str) -> None:
    root = Path(directory).resolve()
    index = root / "index.html"
    if not index.is_file():
        raise RuntimeError("SERVE_FRONTEND_DIR não contém index.html (construa o frontend antes)")
    for ext, mime in _TYPES.items():
        mimetypes.add_type(mime, ext)

    def not_found() -> Response:
        return JSONResponse({"type": "not_found", "title": "Não encontrado", "status": 404}, 404)

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def spa(path: str) -> Response:
        if path == "api" or path.startswith("api/"):
            return not_found()
        try:
            candidate = (root / path).resolve()
            if path and candidate.is_relative_to(root) and candidate.is_file():
                return FileResponse(candidate)
        except (OSError, ValueError):
            return not_found()
        if Path(path).suffix:  # arquivo estático inexistente não vira HTML
            return not_found()
        return FileResponse(index)
