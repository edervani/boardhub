"""Auxiliares do ranking: partidas ranqueadas por REST, ratings semeados e usuários sintéticos."""

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import clock
from app.db.session import get_engine
from app.models import Rating, User, UserPreferences, UserProfile
from app.models.base import new_id
from tests.helpers import API, csrf
from tests.online_helpers import criar_convite, entrar_por_codigo, lance

# 1.e4 e5 2.Nf3 Nc6: quatro meios-lances legais (o mínimo para a partida ranqueada valer).
ABERTURA = ["e2e4", "e7e5", "g1f3", "b8c6"]


def post(c: TestClient, caminho: str, corpo: dict[str, object] | None = None) -> Any:
    return c.post(f"{API}{caminho}", headers=csrf(c), json=corpo)


def partida_ranqueada(a: TestClient, b: TestClient, game: str = "chess") -> str:
    """`a` cria o convite ranqueado (assento 1 = brancas), `b` entra. Devolve o id."""
    sala = criar_convite(a, game, mode="online_ranked", preferred_seat=1)
    resp = entrar_por_codigo(b, sala["invite_code"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["mode"] == "online_ranked"
    return str(sala["id"])


def jogar_abertura(a: TestClient, b: TestClient, match_id: str, plies: int = 4) -> None:
    for i in range(plies):
        autor = a if i % 2 == 0 else b
        resp = lance(autor, match_id, ABERTURA[i], i)
        assert resp.status_code == 200, resp.text


def id_de(n: int) -> uuid.UUID:
    with get_engine().connect() as conn:
        found = conn.execute(text("SELECT id FROM users WHERE email = :e"),
                             {"e": f"jogador{n}@example.test"}).scalar_one()
    return uuid.UUID(str(found))


def definir_rating(n: int, rating: int, jogadas: int = 0, game: str = "chess") -> None:
    """Semeia o rating da conta `jogadorN` (só em teste; o servidor é quem grava em produção)."""
    with get_engine().begin() as conn:
        conn.execute(text(
            "INSERT INTO ratings (user_id, game_id, rating, games_played, updated_at) "
            "VALUES (:u, :g, :r, :p, now()) ON CONFLICT (user_id, game_id) "
            "DO UPDATE SET rating = :r, games_played = :p"),
            {"u": id_de(n), "g": game, "r": rating, "p": jogadas})


def ratings_por_conta(game: str = "chess") -> dict[str, tuple[int, int]]:
    """E-mail -> (rating, partidas) de todas as linhas de `ratings`."""
    with get_engine().connect() as conn:
        rows = conn.execute(text(
            "SELECT u.email, r.rating, r.games_played FROM ratings r "
            "JOIN users u ON u.id = r.user_id WHERE r.game_id = :g"), {"g": game}).all()
    return {r.email: (r.rating, r.games_played) for r in rows}


def contar(tabela: str) -> int:
    with get_engine().connect() as conn:
        return int(conn.execute(text(f"SELECT count(*) FROM {tabela}")).scalar_one())  # noqa: S608


def semear_usuario(n: int, *, publico: bool = True, no_ranking: bool = True,
                   status: str = "active", faixa: str = "18_plus") -> uuid.UUID:
    """Cria usuário sintético direto no banco (sem passar pelo limite de cadastro por IP)."""
    uid = new_id()
    with Session(get_engine()) as db:
        db.add(User(id=uid, email=f"semente{n:03d}@example.test", password_hash="x",
                    age_band=faixa, terms_version="2026-10-13", status=status,
                    email_verified_at=clock.now()))
        db.flush()
        db.add(UserProfile(user_id=uid, display_name=f"semente_{n:03d}", avatar_key="default",
                           is_public=publico, show_in_ranking=no_ranking))
        db.add(UserPreferences(user_id=uid))
        db.commit()
    return uid


def semear_rating(uid: uuid.UUID, rating: int, jogadas: int, game: str = "chess") -> None:
    with Session(get_engine()) as db:
        db.add(Rating(user_id=uid, game_id=game, rating=rating, games_played=jogadas))
        db.commit()
