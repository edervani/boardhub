"""RF-034 (CA-034): limite diário de tempo das contas supervisionadas; RF-007: notação de lances.

O relógio é injetado (`clock.now`) e fixado em instantes absolutos para testar a virada do dia
de America/Sao_Paulo (UTC-3, sem horário de verão). Só dados sintéticos (`@example.test`).
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.models import DailyUsage
from tests.conftest import MemoryMailer
from tests.helpers import API, conta_logada, csrf, login, novo_cliente, register
from tests.online_helpers import criar_convite, duas_contas, entrar_por_codigo, lance, partida
from tests.ws_helpers import abrir, ate, entrar, enviar

# 12:00 em Brasília (15:00 UTC) de 14/10/2026.
MEIO_DIA = datetime(2026, 10, 14, 15, 0, tzinfo=UTC)


class RelogioManual:
    def __init__(self, inicio: datetime) -> None:
        self.t = inicio

    def avancar(self, **kw: float) -> None:
        self.t += timedelta(**kw)

    def now(self) -> datetime:
        return self.t


@pytest.fixture
def relogio(monkeypatch: pytest.MonkeyPatch) -> Iterator[RelogioManual]:
    r = RelogioManual(MEIO_DIA)
    monkeypatch.setattr(clock, "now", r.now)
    yield r


def _vincular(client: TestClient, mailer: MemoryMailer, band: str = "12_15",
              ) -> tuple[TestClient, TestClient, str]:
    """Devolve (menor logado, responsável logado, id do menor)."""
    resp = conta_logada(novo_cliente(client), mailer, 2)
    register(client, 1, age_band=band, guardian_email="jogador2@example.test")
    token = mailer.last_token("jogador2@example.test")
    ok = resp.post(f"{API}/guardian/links/confirm", headers=csrf(resp), json={"token": token})
    assert ok.status_code == 200
    # A fila exige conta verificada (RF-002): o menor confirma o próprio e-mail.
    verificar = client.post(f"{API}/auth/verify-email",
                            json={"token": mailer.last_token("jogador1@example.test")})
    assert verificar.status_code == 204
    assert login(client, 1).status_code == 200
    return client, resp, str(ok.json()["id"])


def _configurar(resp: TestClient, child_id: str, **settings: Any) -> None:
    r = resp.put(f"{API}/guardian/children/{child_id}/settings", headers=csrf(resp),
                 json=settings)
    assert r.status_code == 200, r.text


def _usado(resp: TestClient, child_id: str) -> dict[str, Any]:
    r = resp.get(f"{API}/guardian/children/{child_id}")
    assert r.status_code == 200, r.text
    return dict(r.json()["usage_today"])


def _nova_local(c: TestClient, game: str = "chess") -> Any:
    return c.post(f"{API}/matches", headers=csrf(c), json={"game_id": game, "mode": "local"})


LANCES = ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6", "d2d3", "f8c5"]


def _jogar(c: TestClient, match_id: str, ply: int) -> Any:
    return lance(c, match_id, LANCES[ply], ply)


def _esgotar(c: TestClient, resp: TestClient, child_id: str, relogio: RelogioManual) -> str:
    """Limite de 15 min; 3 lances com 5 min entre eles; devolve o id da partida (ply 3)."""
    _configurar(resp, child_id, daily_minutes_limit=15, allow_open_matchmaking=True)
    criada = _nova_local(c)
    assert criada.status_code == 201
    mid = str(criada.json()["id"])
    for ply in range(3):
        relogio.avancar(minutes=5)
        assert _jogar(c, mid, ply).status_code == 200
    assert _usado(resp, child_id)["used_seconds"] == 900
    return mid


# ---------- contagem de tempo ----------

def test_tempo_soma_intervalos_curtos_e_ignora_pausas_longas(
        client: TestClient, mailer: MemoryMailer, relogio: RelogioManual) -> None:
    c, resp, child_id = _vincular(client, mailer)
    mid = str(_nova_local(c).json()["id"])
    assert _usado(resp, child_id)["used_seconds"] == 0  # a primeira atividade vale zero
    relogio.avancar(seconds=60)
    assert _jogar(c, mid, 0).status_code == 200
    relogio.avancar(seconds=120)
    assert _jogar(c, mid, 1).status_code == 200
    assert _usado(resp, child_id)["used_seconds"] == 180
    relogio.avancar(minutes=20)  # pausa longa: a pessoa saiu, não conta
    assert _jogar(c, mid, 2).status_code == 200
    assert _usado(resp, child_id)["used_seconds"] == 180
    relogio.avancar(seconds=30)
    assert _jogar(c, mid, 3).status_code == 200
    assert _usado(resp, child_id)["used_seconds"] == 210


def test_varias_partidas_contam_uma_vez_so(client: TestClient, mailer: MemoryMailer,
                                           relogio: RelogioManual) -> None:
    c, resp, child_id = _vincular(client, mailer)
    a = str(_nova_local(c).json()["id"])
    relogio.avancar(seconds=100)
    b = str(_nova_local(c).json()["id"])  # a segunda partida não duplica o tempo
    relogio.avancar(seconds=100)
    assert _jogar(c, a, 0).status_code == 200
    relogio.avancar(seconds=50)
    assert _jogar(c, b, 0).status_code == 200
    relogio.avancar(seconds=50)
    assert _jogar(c, a, 1).status_code == 200
    assert _usado(resp, child_id)["used_seconds"] == 300  # 100 + 100 + 50 + 50, não o dobro


def test_dia_civil_e_o_de_sao_paulo_e_nao_herda_tempo_do_dia_anterior(
        client: TestClient, mailer: MemoryMailer, relogio: RelogioManual) -> None:
    relogio.t = datetime(2026, 10, 14, 2, 30, tzinfo=UTC)  # 23:30 de 13/10 em Brasília
    c, resp, child_id = _vincular(client, mailer)
    mid = _esgotar(c, resp, child_id, relogio)  # 23:45: 900 s usados
    bloqueada = _nova_local(c)
    assert bloqueada.status_code == 429
    assert bloqueada.headers["Retry-After"] == "900"  # faltam 15 min para a meia-noite
    relogio.t = datetime(2026, 10, 14, 3, 0, 1, tzinfo=UTC)  # 00:00:01 de 14/10 em Brasília
    assert _usado(resp, child_id)["used_seconds"] == 0
    assert _nova_local(c).status_code == 201  # o limite é diário: volta a valer do zero
    assert _usado(resp, child_id)["used_seconds"] == 0  # a pausa atravessou a meia-noite
    relogio.avancar(seconds=10)
    assert _jogar(c, mid, 3).status_code == 200
    assert _usado(resp, child_id)["used_seconds"] == 10


def test_usado_hoje_nao_inclui_o_dia_seguinte_nem_o_anterior(
        client: TestClient, mailer: MemoryMailer, relogio: RelogioManual) -> None:
    c, resp, child_id = _vincular(client, mailer)
    mid = str(_nova_local(c).json()["id"])
    relogio.avancar(seconds=200)
    assert _jogar(c, mid, 0).status_code == 200
    assert _usado(resp, child_id)["used_seconds"] == 200
    relogio.avancar(days=1)
    assert _usado(resp, child_id)["used_seconds"] == 0
    relogio.avancar(days=-2)
    assert _usado(resp, child_id)["used_seconds"] == 0


def test_adulto_nao_gera_registro_de_tempo(client: TestClient, mailer: MemoryMailer,
                                           relogio: RelogioManual, db: Session) -> None:
    adulto = conta_logada(client, mailer, 1)
    mid = str(_nova_local(adulto).json()["id"])
    relogio.avancar(seconds=60)
    assert _jogar(adulto, mid, 0).status_code == 200
    assert db.scalar(select(func.count()).select_from(DailyUsage)) == 0


def test_academy_tambem_conta(client: TestClient, mailer: MemoryMailer,
                              relogio: RelogioManual) -> None:
    c, resp, child_id = _vincular(client, mailer)
    url = f"{API}/academy/exercises/tt-win-1/attempts"
    assert c.post(url, headers=csrf(c), json={"answer": "0"}).status_code == 200
    relogio.avancar(seconds=90)
    assert c.post(url, headers=csrf(c), json={"answer": "2"}).status_code == 200
    assert _usado(resp, child_id)["used_seconds"] == 90


# ---------- bloqueio ----------

def test_limite_esgotado_bloqueia_partida_convite_e_fila_com_retry(
        client: TestClient, mailer: MemoryMailer, relogio: RelogioManual) -> None:
    c, resp, child_id = _vincular(client, mailer)
    adulto = conta_logada(novo_cliente(client), mailer, 3)
    sala = criar_convite(adulto)
    mid = _esgotar(c, resp, child_id, relogio)  # 12:15 em Brasília
    esperado = "42300"  # 11 h 45 min até a meia-noite de Brasília

    for r in (
        _nova_local(c),
        c.post(f"{API}/matches", headers=csrf(c),
               json={"game_id": "tictactoe", "mode": "ai", "ai_level": 1}),
        c.post(f"{API}/matches", headers=csrf(c),
               json={"game_id": "tictactoe", "mode": "online_casual"}),
        entrar_por_codigo(c, sala["invite_code"]),
        c.post(f"{API}/matchmaking/queue", headers=csrf(c), json={"game_id": "tictactoe"}),
    ):
        assert r.status_code == 429, r.text
        corpo = r.json()
        assert corpo["type"] == "daily_limit_reached"
        assert corpo["title"] == "Limite diário de tempo atingido"
        assert "tempo de jogo de hoje" in corpo["detail"]
        assert r.headers["Retry-After"] == esperado

    # RF-034: a partida em andamento pode terminar.
    seguinte = _jogar(c, mid, 3)
    assert seguinte.status_code == 200
    assert seguinte.json()["ply"] == 4


def test_limite_atingido_so_vale_para_quem_tem_limite(client: TestClient, mailer: MemoryMailer,
                                                      relogio: RelogioManual) -> None:
    c, resp, child_id = _vincular(client, mailer)
    mid = str(_nova_local(c).json()["id"])
    for ply in range(4):
        relogio.avancar(minutes=5)
        assert _jogar(c, mid, ply).status_code == 200
    assert _usado(resp, child_id) == {
        "used_seconds": 1200, "limit_seconds": None, "resets_at": "2026-10-15T03:00:00Z"}
    assert _nova_local(c).status_code == 201  # sem limite definido, nada é bloqueado


def test_responsavel_aumenta_o_limite_e_libera_na_hora(
        client: TestClient, mailer: MemoryMailer, relogio: RelogioManual) -> None:
    c, resp, child_id = _vincular(client, mailer)
    _esgotar(c, resp, child_id, relogio)
    assert _nova_local(c).status_code == 429
    _configurar(resp, child_id, daily_minutes_limit=30)
    assert _nova_local(c).status_code == 201


def test_lance_em_partida_em_andamento_passa_por_padrao_no_http(
        client: TestClient, mailer: MemoryMailer, relogio: RelogioManual) -> None:
    c, resp, child_id = _vincular(client, mailer)
    adulto = conta_logada(novo_cliente(client), mailer, 3)
    sala = criar_convite(adulto, preferred_seat=2)
    assert entrar_por_codigo(c, sala["invite_code"]).status_code == 200
    _esgotar(c, resp, child_id, relogio)
    assert lance(c, sala["id"], "4", 0).status_code == 200


def test_chave_bloqueia_tambem_o_lance_no_http(client: TestClient, mailer: MemoryMailer,
                                               relogio: RelogioManual,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    c, resp, child_id = _vincular(client, mailer)
    adulto = conta_logada(novo_cliente(client), mailer, 3)
    sala = criar_convite(adulto, preferred_seat=2)
    assert entrar_por_codigo(c, sala["invite_code"]).status_code == 200
    _esgotar(c, resp, child_id, relogio)
    monkeypatch.setattr(get_settings(), "daily_limit_blocks_moves", True)
    r = lance(c, sala["id"], "4", 0)
    assert r.status_code == 429
    assert r.json()["type"] == "daily_limit_reached"
    assert c.get(f"{API}/matches/{sala['id']}").json()["ply"] == 0
    assert adulto.get(f"{API}/matches/{sala['id']}").json()["ply"] == 0


def test_websocket_lance_passa_por_padrao_com_limite_esgotado(
        client: TestClient, mailer: MemoryMailer, relogio: RelogioManual) -> None:
    c, resp, child_id = _vincular(client, mailer)
    adulto = conta_logada(novo_cliente(client), mailer, 3)
    sala = criar_convite(adulto, preferred_seat=2)
    assert entrar_por_codigo(c, sala["invite_code"]).status_code == 200
    _esgotar(c, resp, child_id, relogio)
    with abrir(c) as w:
        entrar(w, sala["id"])
        req = enviar(w, "submit_move", {"match_id": sala["id"], "expected_ply": 0, "move": "4",
                                        "client_move_id": str(uuid.uuid4())})
        assert ate(w, "move_applied", reply_to=req)["payload"]["ply"] == 1


def test_websocket_chave_devolve_erro_com_retry_after(
        client: TestClient, mailer: MemoryMailer, relogio: RelogioManual,
        monkeypatch: pytest.MonkeyPatch) -> None:
    c, resp, child_id = _vincular(client, mailer)
    adulto = conta_logada(novo_cliente(client), mailer, 3)
    sala = criar_convite(adulto, preferred_seat=2)
    assert entrar_por_codigo(c, sala["invite_code"]).status_code == 200
    _esgotar(c, resp, child_id, relogio)
    monkeypatch.setattr(get_settings(), "daily_limit_blocks_moves", True)
    with abrir(c) as w:
        entrar(w, sala["id"])
        req = enviar(w, "submit_move", {"match_id": sala["id"], "expected_ply": 0, "move": "4",
                                        "client_move_id": str(uuid.uuid4())})
        erro = ate(w, "error", reply_to=req)["payload"]
    assert erro["code"] == "daily_limit_reached"
    assert erro["status"] == 429
    assert erro["retry_after"] == 42300
    assert "tempo de jogo" in erro["detail"]
    assert c.get(f"{API}/matches/{sala['id']}").json()["ply"] == 0


def _na_fila_e_esgota(c: TestClient, resp: TestClient, child_id: str,
                      relogio: RelogioManual) -> None:
    _configurar(resp, child_id, daily_minutes_limit=15, allow_open_matchmaking=True)
    fila = f"{API}/matchmaking/queue"
    assert c.post(fila, headers=csrf(c), json={"game_id": "tictactoe"}).json()["state"] == "queued"
    mid = str(_nova_local(c).json()["id"])
    for ply in range(3):
        relogio.avancar(minutes=5)
        c.get(fila)  # mantém a entrada "fresca" (consultas recentes) até o último lance
        assert _jogar(c, mid, ply).status_code == 200
    assert _usado(resp, child_id)["used_seconds"] == 900


def test_consulta_da_fila_com_limite_esgotado_sai_da_fila_e_avisa(
        client: TestClient, mailer: MemoryMailer, relogio: RelogioManual) -> None:
    c, resp, child_id = _vincular(client, mailer)
    _na_fila_e_esgota(c, resp, child_id, relogio)
    fila = f"{API}/matchmaking/queue"
    aviso = c.get(fila)
    assert aviso.status_code == 429
    assert aviso.json()["type"] == "daily_limit_reached"
    assert c.get(fila).json()["state"] == "idle"


def test_fila_nao_pareia_quem_esgotou_o_limite(client: TestClient, mailer: MemoryMailer,
                                               relogio: RelogioManual) -> None:
    c, resp, child_id = _vincular(client, mailer)
    adulto = conta_logada(novo_cliente(client), mailer, 3)
    _na_fila_e_esgota(c, resp, child_id, relogio)
    fila = f"{API}/matchmaking/queue"
    entrada = adulto.post(fila, headers=csrf(adulto), json={"game_id": "tictactoe"})
    assert entrada.json()["state"] == "queued"  # não pareou com o menor que esgotou o tempo
    assert c.get(fila).json()["state"] == "idle"  # e a entrada dele foi descartada
    assert adulto.get(fila).json()["state"] == "queued"


# ---------- painel do responsável (API) e IDOR ----------

def test_painel_lista_filhos_com_tempo_usado_e_limite(client: TestClient, mailer: MemoryMailer,
                                                      relogio: RelogioManual) -> None:
    c, resp, child_id = _vincular(client, mailer)
    _configurar(resp, child_id, daily_minutes_limit=60)
    mid = str(_nova_local(c).json()["id"])
    relogio.avancar(seconds=120)
    assert _jogar(c, mid, 0).status_code == 200
    filhos = resp.get(f"{API}/guardian/children").json()
    assert [f["id"] for f in filhos] == [child_id]
    uso = filhos[0]["usage_today"]
    assert uso["used_seconds"] == 120
    assert uso["limit_seconds"] == 3600
    assert uso["resets_at"] == "2026-10-15T03:00:00Z"
    assert filhos[0]["settings"]["daily_minutes_limit"] == 60


def test_exportacao_do_menor_inclui_o_tempo_de_uso(client: TestClient, mailer: MemoryMailer,
                                                   relogio: RelogioManual) -> None:
    c, resp, child_id = _vincular(client, mailer)
    mid = str(_nova_local(c).json()["id"])
    relogio.avancar(seconds=120)
    assert _jogar(c, mid, 0).status_code == 200
    pedido = resp.post(f"{API}/guardian/children/{child_id}/export", headers=csrf(resp))
    assert pedido.status_code == 202
    arquivo = resp.get(f"{API}/guardian/children/{child_id}/export/{pedido.json()['id']}")
    assert arquivo.status_code == 200
    assert arquivo.json()["daily_usage"] == [{"day": "2026-10-14", "seconds": 120}]


def test_detalhe_do_filho_de_outro_responsavel_e_404_igual_ao_inexistente(
        client: TestClient, mailer: MemoryMailer) -> None:
    """SEC-05 / IDOR: não vinculado e inexistente respondem exatamente igual."""
    _, _, child_id = _vincular(client, mailer)
    outro = conta_logada(novo_cliente(client), mailer, 3)
    real = outro.get(f"{API}/guardian/children/{child_id}")
    falso = outro.get(f"{API}/guardian/children/{uuid.uuid4()}")
    assert real.status_code == falso.status_code == 404
    assert real.json()["type"] == falso.json()["type"] == "not_found"
    assert real.json()["title"] == falso.json()["title"]


def test_menor_nao_le_o_painel_do_responsavel(client: TestClient, mailer: MemoryMailer) -> None:
    c, _, child_id = _vincular(client, mailer)
    assert c.get(f"{API}/guardian/children/{child_id}").status_code in (403, 422)


# ---------- RF-007: notação de lances ----------

def test_notacao_padrao_persiste_e_rejeita_valor_desconhecido(client: TestClient,
                                                              mailer: MemoryMailer) -> None:
    c = conta_logada(client, mailer, 1)
    assert c.get(f"{API}/me/preferences").json()["move_notation"] == "algebraic_pt"
    for valor in ("san", "uci", "algebraic_pt"):
        r = c.put(f"{API}/me/preferences", headers=csrf(c), json={"move_notation": valor})
        assert r.status_code == 200
        assert c.get(f"{API}/me/preferences").json()["move_notation"] == valor
    r = c.put(f"{API}/me/preferences", headers=csrf(c), json={"move_notation": "pgn"})
    assert r.status_code == 422


def test_visao_do_xadrez_traz_san_e_o_servidor_segue_em_uci(client: TestClient,
                                                            mailer: MemoryMailer) -> None:
    c = conta_logada(client, mailer, 1)
    mid = str(_nova_local(c).json()["id"])
    view: dict[str, Any] = {}
    for ply in range(3):
        resp = _jogar(c, mid, ply)
        assert resp.status_code == 200
        view = resp.json()
    assert view["san_moves"] == ["e4", "e5", "Nf3"]
    assert view["state"]["moves"] == ["e2e4", "e7e5", "g1f3"]  # o contrato do servidor é UCI
    assert _jogar(c, mid, 3).status_code == 200
    velha = _nova_local(c, "tictactoe").json()
    assert velha["san_moves"] == []


def test_evento_move_applied_do_xadrez_traz_o_lance_em_san(client: TestClient,
                                                           mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = str(partida(a, b, "chess")["id"])
    with abrir(a) as w:
        entrar(w, mid)
        req = enviar(w, "submit_move", {"match_id": mid, "expected_ply": 0, "move": "g1f3",
                                        "client_move_id": str(uuid.uuid4())})
        evento = ate(w, "move_applied", reply_to=req)["payload"]
    assert evento["move"] == "g1f3"  # o contrato continua UCI
    assert evento["san"] == "Nf3"
    assert a.get(f"{API}/matches/{mid}").json()["san_moves"] == ["Nf3"]
