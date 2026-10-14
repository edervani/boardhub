"""Conexões e salas em memória (ADR-0001, doc 04 §14, DT-009).

v1 tem uma instância; o fan-out é por processo. A interface `Broadcaster` isola o resto do
código para trocar por um barramento (Redis/LISTEN-NOTIFY) quando houver várias instâncias.

É seguro chamar `publish` de qualquer thread ou laço de eventos: cada conexão entrega por
uma fila própria, consumida por um único escritor no laço onde a conexão vive. Isso mantém a
ordem das mensagens e evita escritas concorrentes no mesmo socket.
"""

import asyncio
import contextlib
import threading
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.realtime.protocol import to_message
from app.services.events import Event

QUEUE_LIMIT = 256


@dataclass(eq=False)
class Connection:
    user_id: uuid.UUID
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[dict[str, Any]] = field(
        default_factory=lambda: asyncio.Queue(maxsize=QUEUE_LIMIT))
    rooms: set[uuid.UUID] = field(default_factory=set)
    overflowed: bool = False
    last_seen: float = 0.0

    def send(self, message: dict[str, Any]) -> None:
        """Enfileira uma mensagem para o escritor da conexão; seguro entre threads."""
        with contextlib.suppress(RuntimeError):  # laço já fechado: a conexão acabou
            self.loop.call_soon_threadsafe(self._put, message)

    def _put(self, message: dict[str, Any]) -> None:
        try:
            self.queue.put_nowait(message)
        except asyncio.QueueFull:
            self.overflowed = True  # consumidor lento demais; o escritor encerra a conexão


class Broadcaster(Protocol):
    def publish(self, event: Event, exclude: Connection | None = None) -> None: ...


class InMemoryHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rooms: dict[uuid.UUID, set[Connection]] = defaultdict(set)
        self._users: dict[uuid.UUID, set[Connection]] = defaultdict(set)

    def register(self, conn: Connection) -> None:
        with self._lock:
            self._users[conn.user_id].add(conn)

    def join_room(self, conn: Connection, match_id: uuid.UUID) -> None:
        with self._lock:
            self._rooms[match_id].add(conn)
            conn.rooms.add(match_id)

    def _user_left_room(self, conn: Connection, match_id: uuid.UUID) -> bool:
        room = self._rooms.get(match_id, set())
        room.discard(conn)
        conn.rooms.discard(match_id)
        if not room:
            self._rooms.pop(match_id, None)
        return not any(c.user_id == conn.user_id for c in room)

    def leave_room(self, conn: Connection, match_id: uuid.UUID) -> bool:
        """Sai da sala; True se o usuário ficou sem nenhuma conexão nela."""
        with self._lock:
            return self._user_left_room(conn, match_id)

    def unregister(self, conn: Connection) -> list[uuid.UUID]:
        """Remove a conexão; devolve as partidas em que o usuário ficou sem conexões."""
        with self._lock:
            gone = [m for m in list(conn.rooms) if self._user_left_room(conn, m)]
            peers = self._users.get(conn.user_id, set())
            peers.discard(conn)
            if not peers:
                self._users.pop(conn.user_id, None)
            return gone

    def publish(self, event: Event, exclude: Connection | None = None) -> None:
        """Entrega aos usuários nomeados no evento ou, sem eles, à sala da partida."""
        with self._lock:
            if event.user_ids:
                targets = {c for uid in event.user_ids for c in self._users.get(uid, set())}
            elif event.match_id is not None:
                targets = set(self._rooms.get(event.match_id, set()))
            else:
                targets = set()
        message = to_message(event)
        for conn in targets:
            if conn is not exclude:
                conn.send(message)

    def publish_all(self, events: list[Event], exclude: Connection | None = None) -> None:
        for event in events:
            self.publish(event, exclude)

    def connection_count(self, user_id: uuid.UUID) -> int:
        with self._lock:
            return len(self._users.get(user_id, set()))

    def clear(self) -> None:
        with self._lock:
            self._rooms.clear()
            self._users.clear()


hub = InMemoryHub()
