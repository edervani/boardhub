"""Utilitários de teste do WebSocket (dados sintéticos; nenhuma conta real)."""

import queue
import threading
import uuid
from typing import Any

from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from app.core.config import get_settings
from tests.helpers import API

AUTO = "auto"


def abrir(c: TestClient, *, origem: str | None = AUTO, cookie: bool = True,
          token: str | None = None) -> WebSocketTestSession:
    """Abre `/api/v1/ws` com o cookie de sessão e a origem permitida (ou as indicadas).

    O cookie vai explícito no cabeçalho: o jarro de cookies do cliente não envia cookies
    `Secure` em URLs `ws://`.
    """
    headers: dict[str, str] = {}
    if origem == AUTO:
        origem = get_settings().frontend_origin
    if origem:
        headers["origin"] = origem
    token = token or c.cookies.get("bh_session")
    if cookie and token:
        headers["cookie"] = f"bh_session={token}"
    return c.websocket_connect(f"{API}/ws", headers=headers)


def receber(sessao: WebSocketTestSession, timeout: float = 10.0) -> dict[str, Any]:
    """Próxima mensagem JSON; falha (em vez de travar o CI) se nada chegar a tempo."""
    caixa: queue.Queue[tuple[str, Any]] = queue.Queue()

    def alvo() -> None:
        try:
            caixa.put(("ok", sessao.receive_json()))
        except BaseException as exc:
            caixa.put(("erro", exc))

    threading.Thread(target=alvo, daemon=True).start()
    try:
        tipo, valor = caixa.get(timeout=timeout)
    except queue.Empty:
        raise AssertionError(f"nenhuma mensagem em {timeout}s") from None
    if tipo == "erro":
        raise valor
    return dict(valor)


def enviar(sessao: WebSocketTestSession, tipo: str, payload: dict[str, Any]) -> str:
    mid = str(uuid.uuid4())
    sessao.send_json({"type": tipo, "id": mid, "payload": payload})
    return mid


def ate(sessao: WebSocketTestSession, tipo: str, reply_to: str | None = None,
        limite: int = 40) -> dict[str, Any]:
    """Lê mensagens até uma do tipo pedido (descarta as anteriores, como `ping`)."""
    for _ in range(limite):
        msg = receber(sessao)
        if msg["type"] == tipo and (reply_to is None or msg.get("reply_to") == reply_to):
            return msg
    raise AssertionError(f"a mensagem {tipo} não chegou")


def entrar(sessao: WebSocketTestSession, match_id: str, last: int = 0) -> list[dict[str, Any]]:
    """`join_match`; devolve as mensagens recebidas até o `match_snapshot` (inclusive)."""
    mid = enviar(sessao, "join_match", {"match_id": match_id, "last_known_ply": last})
    vistas: list[dict[str, Any]] = []
    for _ in range(40):
        msg = receber(sessao)
        vistas.append(msg)
        if msg["type"] == "match_snapshot" and msg.get("reply_to") == mid:
            return vistas
    raise AssertionError("o snapshot não chegou")


def codigo_de_fechamento(sessao: WebSocketTestSession) -> int:
    """Lê (ignorando mensagens) até o servidor fechar; devolve o código de fechamento."""
    for _ in range(300):
        try:
            receber(sessao)
        except WebSocketDisconnect as exc:
            return int(exc.code)
    raise AssertionError("a conexão não foi fechada")
