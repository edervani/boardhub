"""Auxiliares das partidas online: duas contas, convites e lances por REST (dados sintéticos)."""

import random
import uuid
from typing import Any

from fastapi.testclient import TestClient
from httpx import Response

from tests.conftest import MemoryMailer
from tests.helpers import API, conta_logada, csrf, novo_cliente


def duas_contas(client: TestClient, mailer: MemoryMailer) -> tuple[TestClient, TestClient]:
    a = conta_logada(client, mailer, 1)
    b = conta_logada(novo_cliente(client), mailer, 2)
    return a, b


def criar_convite(c: TestClient, game: str = "tictactoe", **extra: object) -> dict[str, Any]:
    body: dict[str, object] = {"game_id": game, "mode": "online_casual", **extra}
    resp = c.post(f"{API}/matches", headers=csrf(c), json=body)
    assert resp.status_code == 201, resp.text
    return dict(resp.json())


def entrar_por_codigo(c: TestClient, codigo: str) -> Response:
    return c.post(f"{API}/matches/join", headers=csrf(c), json={"invite_code": codigo})


def partida(a: TestClient, b: TestClient, game: str = "tictactoe",
            seat: int = 1) -> dict[str, Any]:
    """`a` cria o convite (assento `seat`), `b` entra; devolve a visão de `a`."""
    sala = criar_convite(a, game, preferred_seat=seat)
    resp = entrar_por_codigo(b, sala["invite_code"])
    assert resp.status_code == 200, resp.text
    return dict(a.get(f"{API}/matches/{sala['id']}").json())


def lance(c: TestClient, match_id: str, move: str, ply: int,
          cid: str | None = None) -> Response:
    return c.post(f"{API}/matches/{match_id}/moves", headers=csrf(c), json={
        "expected_ply": ply, "move": move, "client_move_id": cid or str(uuid.uuid4())})


def jogar_aleatorio(a: TestClient, b: TestClient, match_id: str, ate_ply: int,
                    semente: int = 20261014) -> dict[str, Any]:
    """Alterna lances legais sorteados (semente fixa) até `ate_ply`; devolve a visão final."""
    rng = random.Random(semente)
    view = dict(a.get(f"{API}/matches/{match_id}").json())
    seat_a = int(next(s["seat"] for s in view["seats"] if s["is_you"]))
    for _ in range(ate_ply + 20):
        if view["ply"] >= ate_ply:
            break
        assert view["status"] == "in_progress", view
        autor = a if view["to_move_seat"] == seat_a else b
        resp = lance(autor, match_id, rng.choice(view["legal_moves"]), view["ply"])
        assert resp.status_code == 200, resp.text
        view = dict(resp.json())
    assert view["ply"] >= ate_ply
    return view
