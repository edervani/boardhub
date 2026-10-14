"""RF-024 (CA-024) e T-024: análise pós-partida do Mentor pela API."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.llm.provider import Facts, Style
from app.models import MatchAnalysis
from app.services import analysis_service
from tests.conftest import MemoryMailer
from tests.helpers import API, conta_logada, csrf, novo_cliente


@pytest.fixture
def jogador(client: TestClient, mailer: MemoryMailer) -> TestClient:
    return conta_logada(client, mailer)


def jogar_local(c: TestClient, game_id: str, moves: list[str]) -> dict[str, Any]:
    resp = c.post(f"{API}/matches", headers=csrf(c), json={"game_id": game_id, "mode": "local"})
    assert resp.status_code == 201, resp.text
    match = dict(resp.json())
    for move in moves:
        resp = c.post(f"{API}/matches/{match['id']}/moves", headers=csrf(c), json={
            "expected_ply": match["ply"], "move": move, "client_move_id": str(uuid.uuid4())})
        assert resp.status_code == 200, resp.text
        match = dict(resp.json())
    return match


def analise(c: TestClient, match_id: str) -> Response:
    return c.get(f"{API}/matches/{match_id}/analysis")


BLUNDER = ["0", "4", "1", "6", "2"]  # O não bloqueia a casa 2 e X vence


def test_analise_exige_login(client: TestClient) -> None:
    assert analise(client, str(uuid.uuid4())).status_code == 401


def test_partida_em_andamento_nao_tem_analise(jogador: TestClient) -> None:
    match = jogar_local(jogador, "tictactoe", ["0", "4"])
    resp = analise(jogador, match["id"])
    assert resp.status_code == 409
    assert resp.json()["type"] == "analysis_unavailable"


def test_analise_de_partida_finalizada_aponta_o_momento_critico(jogador: TestClient,
                                                                db: Session) -> None:
    match = jogar_local(jogador, "tictactoe", BLUNDER)
    assert match["status"] == "finished"
    resp = analise(jogador, match["id"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Partida local: o usuário joga pelos dois lados, então os dois são analisados.
    assert body["user_moves"] == 5 and body["analyzed_moves"] == 5
    assert body["counts"] == {"inaccuracy": 0, "mistake": 0, "blunder": 1}
    assert len(body["moments"]) == 1
    m = body["moments"][0]
    assert (m["ply"], m["move_number"], m["severity"]) == (3, 4, "blunder")
    assert (m["played"], m["best"], m["reply"]) == ("6", "2", "2")
    assert m["explanation_source"] == "template"
    assert m["explanation"].startswith("No lance 4, você jogou linha 3, coluna 1.")
    assert m["concept_key"] == "tt.block" and m["lesson_id"] == "tt-l3"
    assert m["position"] == {"board": "XX__O____", "to_move": "O"}
    assert body["caveat"]
    user_id = uuid.UUID(jogador.get(f"{API}/me").json()["id"])
    assert db.get(MatchAnalysis, (uuid.UUID(match["id"]), user_id)) is not None


def test_analise_e_cacheada_e_nao_conta_no_limite(jogador: TestClient, db: Session) -> None:
    match = jogar_local(jogador, "tictactoe", BLUNDER)
    first = analise(jogador, match["id"])
    for _ in range(12):  # o limite de 10/h só vale para análises calculadas
        assert analise(jogador, match["id"]).json() == first.json()
    assert len(db.scalars(select(MatchAnalysis)).all()) == 1


def test_limite_de_10_analises_por_hora(jogador: TestClient) -> None:
    ids = [jogar_local(jogador, "tictactoe", BLUNDER)["id"] for _ in range(11)]
    for match_id in ids[:10]:
        assert analise(jogador, match_id).status_code == 200
    assert analise(jogador, ids[10]).status_code == 429


def test_nao_participante_e_partida_inexistente_recebem_404(client: TestClient,
                                                            mailer: MemoryMailer) -> None:
    dono = conta_logada(client, mailer)
    match = jogar_local(dono, "tictactoe", BLUNDER)
    intruso = conta_logada(novo_cliente(client), mailer, 2)
    assert analise(intruso, match["id"]).status_code == 404
    assert analise(dono, str(uuid.uuid4())).status_code == 404
    assert analise(dono, match["id"]).status_code == 200


def test_partida_contra_a_ia_so_analisa_os_lances_do_usuario(jogador: TestClient) -> None:
    resp = jogador.post(f"{API}/matches", headers=csrf(jogador),
                        json={"game_id": "tictactoe", "mode": "ai", "ai_level": 1})
    match = resp.json()
    assert jogador.post(f"{API}/matches/{match['id']}/resign",
                        headers=csrf(jogador)).status_code == 200
    body = analise(jogador, match["id"]).json()
    assert body["user_moves"] == 0 and body["moments"] == []


def test_damas_partida_finalizada_por_desistencia_e_analisada(jogador: TestClient) -> None:
    match = jogar_local(jogador, "checkers", ["21-17", "9-14", "22-18"])
    assert jogador.post(f"{API}/matches/{match['id']}/resign",
                        headers=csrf(jogador)).status_code == 200
    body = analise(jogador, match["id"]).json()
    assert body["game_id"] == "checkers" and body["user_moves"] == 3
    assert [m["played"] for m in body["moments"]] == ["22-18"]
    assert body["moments"][0]["severity"] == "mistake"
    assert "capturar 1 peça" in body["moments"][0]["explanation"]
    assert body["moments"][0]["position"]["squares"] and body["moments"][0]["lesson_id"]


def test_xadrez_mate_do_louco(jogador: TestClient) -> None:
    match = jogar_local(jogador, "chess", ["f2f3", "e7e5", "g2g4", "d8h4"])
    assert match["status"] == "finished"
    body = analise(jogador, match["id"]).json()
    assert [(m["ply"], m["severity"], m["kind"]) for m in body["moments"]] == [
        (2, "blunder", "allowed_loss")]
    assert "Dh4#" in body["moments"][0]["explanation"]
    assert body["moments"][0]["position"]["fen"]
    assert body["moments"][0]["concept_key"] == "ch.mate_in_one"


class ReescritaFiel:
    """Dublê de provedor generativo que reformula usando só os fatos recebidos."""

    def rephrase(self, facts: Facts, style: Style) -> str | None:
        return "Resumo: " + facts.text


class ReescritaInventada:
    def rephrase(self, facts: Facts, style: Style) -> str | None:
        return facts.text + " Havia também Bb5."


class ReescritaComHtml:
    def rephrase(self, facts: Facts, style: Style) -> str | None:
        return "<script>alert(1)</script> " + facts.text


@pytest.mark.parametrize(("provider", "source"), [
    (ReescritaFiel, "llm"), (ReescritaInventada, "template"), (ReescritaComHtml, "template")])
def test_reformulacao_so_vale_se_nao_acrescentar_fatos(
        jogador: TestClient, monkeypatch: pytest.MonkeyPatch, provider: type, source: str) -> None:
    monkeypatch.setattr(analysis_service, "get_provider", lambda: provider())
    match = jogar_local(jogador, "tictactoe", BLUNDER)
    moment = analise(jogador, match["id"]).json()["moments"][0]
    assert moment["explanation_source"] == source
    assert "<script>" not in moment["explanation"]
    if source == "template":
        assert moment["explanation"].startswith("No lance 4, você jogou")
        assert "Bb5" not in moment["explanation"]
