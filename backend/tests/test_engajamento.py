"""RF-026 (conquistas), RF-027 (desafio diário), RF-028 (notificações). CA-026/027/028.

Relógio injetado em instantes absolutos; fuso America/Sao_Paulo (UTC-3). Só dados sintéticos.
"""

import json
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.academy import grading
from app.academy.content import ExerciseRef
from app.core import clock
from app.engagement import achievements as definitions
from app.engagement import daily
from app.models import (
    DailyChallengeResult,
    Notification,
    User,
    UserAchievement,
)
from app.services import achievement_service, domain_events, privacy_service
from tests.conftest import MemoryMailer
from tests.helpers import API, csrf, novo_cliente
from tests.online_helpers import duas_contas, lance, partida
from tests.ws_helpers import abrir, ate, entrar

# 12:00 em Brasília de 14/10/2026.
MEIO_DIA = datetime(2026, 10, 14, 15, 0, tzinfo=UTC)
HOJE = date(2026, 10, 14)


class Relogio:
    def __init__(self, t: datetime) -> None:
        self.t = t

    def now(self) -> datetime:
        return self.t


@pytest.fixture
def relogio(monkeypatch: pytest.MonkeyPatch) -> Relogio:
    r = Relogio(MEIO_DIA)
    monkeypatch.setattr(clock, "now", r.now)
    return r


def _vitoria_de_a(a: TestClient, b: TestClient) -> str:
    mid = str(partida(a, b)["id"])
    for autor, mv, ply in ((a, "0", 0), (b, "3", 1), (a, "1", 2), (b, "4", 3), (a, "2", 4)):
        assert lance(autor, mid, mv, ply).status_code == 200
    return mid


def _chaves(c: TestClient) -> set[str]:
    itens = c.get(f"{API}/me/achievements").json()["items"]
    return {i["key"] for i in itens if i["earned"]}


def _avisos(c: TestClient, **q: str) -> dict[str, Any]:
    return dict(c.get(f"{API}/me/notifications", params=q).json())


def _tipos(c: TestClient) -> list[str]:
    return [str(i["kind"]) for i in _avisos(c)["items"]]


def _resposta_certa(ref: ExerciseRef) -> str:
    ex = ref.exercise
    if ex.type == "rule_quiz":
        assert ex.correct_option
        return ex.correct_option
    return grading.correct_moves(ref)[0]


# ---------------------------------------------------------------- definições

def test_definicoes_validas_sem_valor_monetario() -> None:
    defs = definitions.load()
    assert defs.version and len(defs.achievements) >= 10
    texto = json.dumps(defs.model_dump(mode="json")).lower()
    for proibido in ("moeda", "dinheiro", "r$", "prêmio", "premio", "saque", "sorteio"):
        assert proibido not in texto


def test_nao_ha_endpoint_de_troca(client: TestClient, mailer: MemoryMailer) -> None:
    a, _ = duas_contas(client, mailer)
    for caminho in ("redeem", "exchange", "me/achievements/first_match/claim"):
        assert a.post(f"{API}/{caminho}", headers=csrf(a)).status_code in (404, 405)


# ---------------------------------------------------------------- conquistas (CA-026)

def test_vitoria_concede_conquistas_uma_vez(client: TestClient, mailer: MemoryMailer,
                                            db: Session) -> None:
    a, b = duas_contas(client, mailer)
    _vitoria_de_a(a, b)
    assert {"first_match", "ttt_first_win", "online_first_win"} <= _chaves(a)
    assert _chaves(b) == {"first_match"}  # derrota não concede vitória
    uid = db.scalars(select(User.id).where(User.email == "jogador1@example.test")).one()
    antes = len(_chaves(a))
    for _ in range(3):  # eventos repetidos não duplicam (idempotência)
        assert achievement_service.evaluate(db, uid, domain_events.MATCH_FINISHED) == []
    db.commit()
    total = db.scalar(select(func.count()).select_from(UserAchievement)
                      .where(UserAchievement.user_id == uid))
    assert total == antes
    avisos = db.scalars(select(Notification).where(
        Notification.user_id == uid, Notification.kind == "achievement_earned")).all()
    assert len(avisos) == antes  # um aviso por conquista, nunca repetido


def test_progresso_de_conquista_nao_obtida(client: TestClient, mailer: MemoryMailer) -> None:
    a, _ = duas_contas(client, mailer)
    dados = a.get(f"{API}/me/achievements").json()
    assert dados["earned_count"] == 0 and dados["definition_version"]
    item = next(i for i in dados["items"] if i["key"] == "matches_10")
    assert item["earned"] is False and item["progress"] == 0 and item["target"] == 10


def test_conquista_da_academy_e_vitrine_publica(client: TestClient,
                                                mailer: MemoryMailer) -> None:
    a, _ = duas_contas(client, mailer)
    ok = a.post(f"{API}/academy/exercises/tt-win-1/attempts", headers=csrf(a),
                json={"answer": "2"})
    assert ok.json()["correct"] is True
    assert "academy_first_exercise" in _chaves(a)
    nome = a.get(f"{API}/me/profile").json()["display_name"]
    pub = novo_cliente(client).get(f"{API}/users/{nome}").json()
    assert [i["key"] for i in pub["achievements"]] == ["academy_first_exercise"]
    a.patch(f"{API}/me/profile", headers=csrf(a), json={"is_public": False})
    assert novo_cliente(client).get(f"{API}/users/{nome}").status_code == 404


def test_cliente_nao_concede_conquista(client: TestClient, mailer: MemoryMailer) -> None:
    a, _ = duas_contas(client, mailer)
    resp = a.post(f"{API}/academy/exercises/tt-win-1/attempts", headers=csrf(a),
                  json={"answer": "2", "achievement": "matches_50"})
    assert resp.status_code == 422
    assert _chaves(a) == set()


# ---------------------------------------------------------------- desafio diário (CA-027)

def test_escolha_deterministica_e_varia_com_o_dia() -> None:
    for jogo in ("tictactoe", "checkers", "chess"):
        assert daily.pick(jogo, HOJE) == daily.pick(jogo, HOJE)
        assert daily.pick(jogo, HOJE) is not None
    ids = {r.exercise.id for i in range(30)
           if (r := daily.pick("chess", HOJE + timedelta(days=i))) is not None}
    assert len(ids) > 1


def test_mesmo_desafio_para_todos_e_virada_em_sao_paulo(
        client: TestClient, mailer: MemoryMailer, relogio: Relogio) -> None:
    a, b = duas_contas(client, mailer)
    relogio.t = datetime(2026, 10, 15, 2, 30, tzinfo=UTC)  # 23:30 de 14/10 em Brasília
    ca, cb = a.get(f"{API}/daily-challenge").json(), b.get(f"{API}/daily-challenge").json()
    assert ca["day"] == "2026-10-14"
    assert [c["exercise"]["id"] for c in ca["challenges"]] == \
        [c["exercise"]["id"] for c in cb["challenges"]]
    assert {c["game_id"] for c in ca["challenges"]} == {"tictactoe", "checkers", "chess"}
    relogio.t = datetime(2026, 10, 15, 3, 30, tzinfo=UTC)  # 00:30 de 15/10
    assert a.get(f"{API}/daily-challenge").json()["day"] == "2026-10-15"


def _status(c: TestClient, jogo: str) -> str:
    dados = c.get(f"{API}/daily-challenge").json()
    return str(next(x for x in dados["challenges"] if x["game_id"] == jogo)["status"])


def test_uma_tentativa_valida_por_dia_e_sem_perda_por_faltar(
        client: TestClient, mailer: MemoryMailer, relogio: Relogio, db: Session) -> None:
    a, _ = duas_contas(client, mailer)
    assert _status(a, "tictactoe") == "pending"
    url = f"{API}/daily-challenge/tictactoe/attempt"
    assert a.post(url, headers=csrf(a), json={"answer": "zz-invalida"}).status_code == 422
    assert _status(a, "tictactoe") == "pending"  # inválida não gasta a tentativa
    ref = daily.pick("tictactoe", HOJE)
    assert ref is not None
    resp = a.post(url, headers=csrf(a), json={"answer": _resposta_certa(ref)})
    assert resp.status_code == 200 and resp.json()["correct"] is True
    assert resp.json()["completed_total"] == 1
    again = a.post(url, headers=csrf(a), json={"answer": _resposta_certa(ref)})
    assert again.status_code == 409
    assert _status(a, "tictactoe") == "answered"
    assert db.scalar(select(func.count()).select_from(DailyChallengeResult)) == 1
    relogio.t += timedelta(days=3)  # faltou: nada se perde e o desafio novo está disponível
    assert a.get(f"{API}/daily-challenge").json()["completed_total"] == 1
    assert _status(a, "tictactoe") == "pending"
    assert "daily_first" in _chaves(a)


def test_desafio_exige_login(client: TestClient) -> None:
    assert client.get(f"{API}/daily-challenge").status_code == 401


# ---------------------------------------------------------------- notificações (CA-028)

def test_vez_de_jogar_chega_por_websocket_e_na_lista(client: TestClient,
                                                     mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = str(partida(a, b)["id"])
    with abrir(b) as w:
        entrar(w, mid)
        assert lance(a, mid, "0", 0).status_code == 200
        msg = ate(w, "notification")
    assert msg["payload"]["kind"] == "your_turn"
    lista = _avisos(b)
    assert lista["unread_count"] == 1
    assert lista["items"][0]["title"] == "Sua vez de jogar"
    assert "your_turn" not in _tipos(a)  # quem jogou não recebe aviso da própria jogada


def test_avisos_repetidos_viram_um_e_somem_ao_jogar(client: TestClient,
                                                    mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = str(partida(a, b)["id"])
    assert lance(a, mid, "0", 0).status_code == 200
    assert _avisos(b)["unread_count"] == 1
    assert lance(b, mid, "3", 1).status_code == 200  # b agiu: o aviso dele some
    assert _avisos(b)["unread_count"] == 0
    assert _avisos(a)["unread_count"] == 1


def test_fim_de_partida_avisa_o_oponente(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    _vitoria_de_a(a, b)
    item = next(i for i in _avisos(b)["items"] if i["kind"] == "match_ended")
    assert "perdeu" in item["body"]
    assert "match_ended" not in _tipos(a)


def test_marcar_como_lida_e_isolamento(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = str(partida(a, b)["id"])
    lance(a, mid, "0", 0)
    nid = _avisos(b)["items"][0]["id"]
    assert a.post(f"{API}/me/notifications/{nid}/read", headers=csrf(a)).status_code == 404
    assert b.post(f"{API}/me/notifications/{nid}/read", headers=csrf(b)).status_code == 204
    assert _avisos(b)["unread_count"] == 0
    other = uuid.uuid4()
    assert b.post(f"{API}/me/notifications/{other}/read", headers=csrf(b)).status_code == 404
    lance(b, mid, "3", 1)
    assert a.post(f"{API}/me/notifications/read-all", headers=csrf(a)).status_code == 204
    assert _avisos(a)["unread_count"] == 0
    assert _avisos(a, unread_only="true")["items"] == []


def test_preferencias_desativam_tipos(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    padrao = b.get(f"{API}/me/notification-preferences").json()["kinds"]
    assert all(k["enabled"] for k in padrao) and len(padrao) == 4
    ok = b.put(f"{API}/me/notification-preferences", headers=csrf(b),
               json={"kinds": {"your_turn": False}})
    assert ok.status_code == 200
    assert next(k for k in ok.json()["kinds"] if k["kind"] == "your_turn")["enabled"] is False
    mid = str(partida(a, b)["id"])
    lance(a, mid, "0", 0)
    assert _avisos(b)["unread_count"] == 0
    bad = b.put(f"{API}/me/notification-preferences", headers=csrf(b),
                json={"kinds": {"marketing": True}})
    assert bad.status_code == 422


def test_desconexao_avisa_o_oponente_e_nao_ha_email(client: TestClient,
                                                    mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = str(partida(a, b)["id"])
    enviados = len(mailer.sent)
    with abrir(a) as w:
        entrar(w, mid)
    assert "opponent_disconnected" in _tipos(b)
    assert len(mailer.sent) == enviados  # RF-028: nenhum e-mail de aviso


def test_falha_de_consumidor_nao_quebra_o_lance(client: TestClient, mailer: MemoryMailer,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    def quebra(*_: object) -> None:
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(domain_events, "_handlers", [quebra])
    a, b = duas_contas(client, mailer)
    mid = str(partida(a, b)["id"])
    assert lance(a, mid, "0", 0).status_code == 200


# ---------------------------------------------------------------- privacidade (RF-029/030)

def test_exportacao_inclui_engajamento_e_exclusao_apaga(
        client: TestClient, mailer: MemoryMailer, db: Session) -> None:
    a, b = duas_contas(client, mailer)
    _vitoria_de_a(a, b)
    a.put(f"{API}/me/notification-preferences", headers=csrf(a),
          json={"kinds": {"match_ended": False}})
    user = db.scalars(select(User).where(User.email == "jogador1@example.test")).one()
    dados = privacy_service.build_export(db, user)["engagement"]
    assert {x["key"] for x in dados["achievements"]} >= {"first_match", "ttt_first_win"}
    assert dados["notification_preferences"] == [{"kind": "match_ended", "enabled": False}]
    uid = user.id
    db.delete(user)
    db.commit()
    for modelo in (UserAchievement, Notification, DailyChallengeResult):
        n = db.scalar(select(func.count()).select_from(modelo).where(modelo.user_id == uid))
        assert n == 0
