"""WebSocket `/api/v1/ws` (doc 06 §3, SEC-06): partidas online com retomada.

Autenticação no handshake pelo cookie de sessão e verificação de `Origin`. Toda mensagem é
validada por Pydantic estrito e revalida a participação no serviço. O servidor é a
autoridade: o cliente envia só intenção (lance, desistência, resposta de empate).
"""

import asyncio
import contextlib
import json
import time
import uuid
from collections import deque
from collections.abc import Callable

import anyio
from fastapi import APIRouter, WebSocket
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.websockets import WebSocketDisconnect

from app.api.deps import SESSION_COOKIE
from app.core.config import get_settings
from app.core.errors import ProblemError
from app.core.logging import get_logger
from app.db.session import get_engine
from app.models import User
from app.realtime.hub import Connection, hub
from app.realtime.protocol import (
    ClaimAbandon,
    ClientMessage,
    JoinMatch,
    LeaveMatch,
    OfferDraw,
    Pong,
    Resign,
    RespondDraw,
    SubmitMove,
    error_message,
    parse_client_message,
    reply_message,
    to_message,
)
from app.services import auth_service, match_service, online_service
from app.services.events import Event

log = get_logger(__name__)
router = APIRouter(tags=["tempo-real"])

# Doc 06 §3.1. Lidos em tempo de execução para que os testes possam reduzi-los.
PING_INTERVAL = 20.0
PONG_TIMEOUT = 40.0
MAX_MESSAGE_BYTES = 4096
MAX_MESSAGES_PER_SECOND = 20

CLOSE_TOO_BIG = 1009
CLOSE_OVERFLOW = 1013
CLOSE_UNAUTHENTICATED = 4401
CLOSE_BAD_ORIGIN = 4403
CLOSE_TIMEOUT = 4408
CLOSE_RATE_LIMITED = 4429
SOCKET_ERRORS = (WebSocketDisconnect, RuntimeError, OSError)


def _authenticate(raw_cookie: str | None) -> uuid.UUID | None:
    """Usuário dono de uma sessão válida (síncrono; roda em thread)."""
    with Session(get_engine(), expire_on_commit=False) as db:
        sess = auth_service.session_from_cookie(db, raw_cookie)
        if sess is None:
            return None
        user = db.get(User, sess.user_id)
        return None if user is None or user.status == "suspended" else user.id


def _in_session[T](user_id: uuid.UUID, work: Callable[[Session, User], T]) -> T:
    with Session(get_engine(), expire_on_commit=False) as db:
        user = db.get(User, user_id)
        if user is None or user.status == "suspended":
            raise ProblemError(401, "not_authenticated", "Sessão encerrada")
        return work(db, user)


async def _run[T](user_id: uuid.UUID, work: Callable[[Session, User], T]) -> T:
    return await run_in_threadpool(_in_session, user_id, work)


def _reply_id(text: str) -> str | None:
    """`id` da mensagem inválida, se houver, para o erro poder citar `reply_to`."""
    try:
        data = json.loads(text)
        return str(uuid.UUID(str(data["id"]))) if isinstance(data, dict) else None
    except (ValueError, KeyError, TypeError):
        return None


def _only_online(match_id: uuid.UUID) -> Callable[[Session, User], None]:
    def check(db: Session, user: User) -> None:
        match, _ = match_service.load_for_participant(db, user, match_id)
        if not match_service.is_online(match):
            raise ProblemError(422, "not_online_match", "Esta ação vale só para partidas online")
    return check


class _Handler:
    """Executa os comandos de uma conexão. Falhas viram mensagens `error` com `reply_to`."""

    def __init__(self, conn: Connection) -> None:
        self.conn = conn
        self.uid = conn.user_id

    async def handle_raw(self, text: str) -> None:
        try:
            msg = parse_client_message(text)
        except ValidationError as exc:
            fields = ", ".join(sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()}))
            self.conn.send(error_message("validation_error", "Mensagem inválida",
                                         reply_to=_reply_id(text), status=422, detail=fields))
            return
        reply_to = str(msg.id) if msg.id else None
        try:
            await self._dispatch(msg)
        except ProblemError as exc:
            current = exc.current_ply if isinstance(exc, match_service.StaleStateError) else None
            self.conn.send(error_message(exc.type, exc.title, reply_to=reply_to, status=exc.status,
                                         detail=exc.detail, current_ply=current))
        except Exception as exc:
            log.error("erro inesperado no WebSocket", extra={"error_type": type(exc).__name__})
            self.conn.send(error_message("internal_error", "Erro interno", reply_to=reply_to,
                                         status=500))

    def _deliver(self, events: list[Event], reply_to: str, duplicate: Event | None = None) -> None:
        """Difunde à sala (menos a esta conexão) e responde a quem enviou o comando."""
        hub.publish_all(events, exclude=self.conn)
        for event in [*events, *([duplicate] if duplicate else [])]:
            self.conn.send(to_message(event, reply_to))

    async def _dispatch(self, msg: ClientMessage) -> None:
        if isinstance(msg, Pong):
            return
        reply_to = str(msg.id)
        mid = msg.payload.match_id
        if isinstance(msg, JoinMatch):
            await self._join(msg)
        elif isinstance(msg, LeaveMatch):
            await self._leave(mid, reply_to)
        elif isinstance(msg, SubmitMove):
            p = msg.payload
            await _run(self.uid, _only_online(mid))
            result = await _run(self.uid, lambda db, user: match_service.submit_move_result(
                db, user, mid, p.expected_ply, p.move, p.client_move_id))
            self._deliver(result.events, reply_to, result.duplicate)
        elif isinstance(msg, Resign):
            await _run(self.uid, _only_online(mid))
            _, events = await _run(self.uid, lambda db, user: match_service.resign_result(
                db, user, mid))
            self._deliver(events, reply_to)
        elif isinstance(msg, OfferDraw):
            _, events = await _run(self.uid, lambda db, user: online_service.offer_draw(
                db, user, mid))
            self._deliver(events, reply_to)
        elif isinstance(msg, RespondDraw):
            accept = msg.payload.accept
            _, events = await _run(self.uid, lambda db, user: online_service.respond_draw(
                db, user, mid, accept))
            self._deliver(events, reply_to)
        elif isinstance(msg, ClaimAbandon):
            _, events = await _run(self.uid, lambda db, user: online_service.claim_abandon(
                db, user, mid))
            self._deliver(events, reply_to)

    async def _join(self, msg: JoinMatch) -> None:
        mid, last_known = msg.payload.match_id, msg.payload.last_known_ply
        reply_to = str(msg.id)
        # 1) autoriza e marca presença; 2) entra na sala; 3) lê o estado oficial. Assim nenhum
        # lance se perde entre o snapshot e a entrada na sala (o cliente ignora ply repetido).
        events = await _run(self.uid, lambda db, user: online_service.mark_connected(
            db, user, mid))
        hub.join_room(self.conn, mid)
        hub.publish_all(events, exclude=self.conn)
        snap = await _run(self.uid, lambda db, user: online_service.snapshot(
            db, user, mid, last_known))
        if snap.missed_moves:
            self.conn.send(reply_message("moves_since", {
                "match_id": str(mid), "since_ply": last_known, "moves": snap.missed_moves},
                reply_to))
        payload = snap.view.model_dump(mode="json")
        payload["your_seat"] = snap.your_seat
        self.conn.send(reply_message("match_snapshot", payload, reply_to))

    async def _leave(self, match_id: uuid.UUID, reply_to: str) -> None:
        if hub.leave_room(self.conn, match_id):
            events = await _run(self.uid, _disconnect_work(match_id))
            hub.publish_all(events)
        self.conn.send(reply_message("ack", {"match_id": str(match_id)}, reply_to))


def _disconnect_work(match_id: uuid.UUID) -> Callable[[Session, User], list[Event]]:
    def work(db: Session, user: User) -> list[Event]:
        return online_service.mark_disconnected(db, user.id, match_id)
    return work


async def _close(ws: WebSocket, code: int) -> None:
    with contextlib.suppress(*SOCKET_ERRORS):
        await ws.close(code=code)


async def _read_loop(ws: WebSocket, conn: Connection, handler: _Handler) -> None:
    stamps: deque[float] = deque()
    while True:
        try:
            message = await ws.receive()
        except SOCKET_ERRORS:
            return
        if message["type"] == "websocket.disconnect":
            return
        now = time.monotonic()
        conn.last_seen = now
        stamps.append(now)
        while stamps and stamps[0] <= now - 1.0:
            stamps.popleft()
        if len(stamps) > MAX_MESSAGES_PER_SECOND:
            await _close(ws, CLOSE_RATE_LIMITED)
            return
        text = message.get("text")
        if text is None:
            conn.send(error_message("invalid_message", "Envie mensagens de texto JSON", status=400))
            continue
        if len(text.encode()) > MAX_MESSAGE_BYTES:
            await _close(ws, CLOSE_TOO_BIG)
            return
        await handler.handle_raw(text)


async def _serve(ws: WebSocket, conn: Connection, raw_cookie: str | None) -> None:
    async with anyio.create_task_group() as tg:
        async def writer() -> None:
            with contextlib.suppress(*SOCKET_ERRORS):
                while True:
                    message = await conn.queue.get()
                    if conn.overflowed:  # perdeu mensagens: reconectar é mais seguro
                        await _close(ws, CLOSE_OVERFLOW)
                        break
                    await ws.send_json(message)
            tg.cancel_scope.cancel()

        async def heartbeat() -> None:
            while True:
                await anyio.sleep(PING_INTERVAL)
                if time.monotonic() - conn.last_seen > PONG_TIMEOUT:
                    await _close(ws, CLOSE_TIMEOUT)
                    break
                # Sessão revogada (logout, troca de senha) fecha a conexão em até um intervalo.
                if await run_in_threadpool(_authenticate, raw_cookie) != conn.user_id:
                    await _close(ws, CLOSE_UNAUTHENTICATED)
                    break
                conn.send({"type": "ping"})
            tg.cancel_scope.cancel()

        tg.start_soon(writer)
        tg.start_soon(heartbeat)
        await _read_loop(ws, conn, _Handler(conn))
        tg.cancel_scope.cancel()


async def _cleanup(conn: Connection) -> None:
    """Marca desconexão nas partidas em que o usuário ficou sem conexões e avisa o oponente."""
    for match_id in hub.unregister(conn):
        try:
            events = await _run(conn.user_id, _disconnect_work(match_id))
            hub.publish_all(events)
        except Exception as exc:
            log.error("falha ao registrar desconexão", extra={"error_type": type(exc).__name__})


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    # Aceita antes de recusar para que o navegador receba o código 4401/4403 (e não 1006).
    await websocket.accept()
    if websocket.headers.get("origin") != get_settings().frontend_origin:
        await _close(websocket, CLOSE_BAD_ORIGIN)
        return
    raw_cookie = websocket.cookies.get(SESSION_COOKIE)
    user_id = await run_in_threadpool(_authenticate, raw_cookie)
    if user_id is None:
        await _close(websocket, CLOSE_UNAUTHENTICATED)
        return
    conn = Connection(user_id=user_id, loop=asyncio.get_running_loop(), last_seen=time.monotonic())
    hub.register(conn)
    try:
        await _serve(websocket, conn, raw_cookie)
    finally:
        with anyio.CancelScope(shield=True):
            await _cleanup(conn)
