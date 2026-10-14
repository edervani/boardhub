"""RF-019, RF-021 (CA-019, CA-021): ranking público paginado e estatísticas do usuário.

Privacidade (LGPD/ECA): o ranking só mostra apelido público; perfil privado, quem escolheu não
aparecer, menores sem decisão do responsável e contas não ativas ficam de fora. Dados sintéticos.
"""

import random
import re
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.models import Match, MatchPlayer
from app.models.base import new_id
from tests.conftest import FakeClock, MemoryMailer
from tests.helpers import API, conta_logada, csrf, novo_cliente
from tests.online_helpers import duas_contas
from tests.ranking_helpers import (
    definir_rating,
    id_de,
    jogar_abertura,
    partida_ranqueada,
    post,
    semear_rating,
    semear_usuario,
)

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def ranking(c: TestClient, game: str = "chess", **params: object):
    return c.get(f"{API}/ranking/{game}", params=params)


def nomes(resp_json: dict[str, object]) -> list[str]:
    return [i["display_name"] for i in resp_json["items"]]  # type: ignore[attr-defined]


def semear_ranking() -> None:
    """Cinco elegíveis (n=1..5) e vários que devem ficar de fora, todos com rating alto."""
    for n, rating in ((1, 1500), (2, 1400), (3, 1400), (4, 1300), (5, 1200)):
        semear_rating(semear_usuario(n), rating, 12)
    semear_rating(semear_usuario(10, publico=False, no_ranking=False), 2000, 20)  # perfil privado
    semear_rating(semear_usuario(11, no_ranking=False), 2000, 20)  # não quer aparecer
    semear_rating(semear_usuario(12), 2000, 9)  # menos de 10 partidas
    semear_rating(semear_usuario(13, status="suspended"), 2000, 20)
    semear_rating(semear_usuario(14, status="pending_deletion"), 2000, 20)
    semear_rating(semear_usuario(15, publico=False, no_ranking=False, faixa="12_15"), 2000, 20)
    semear_rating(semear_usuario(16, faixa="12_15"), 1250, 20)  # responsável liberou


# ---------- ranking público (RF-019) ----------

def test_ranking_lista_so_perfis_publicos_ativos_e_com_10_partidas(client: TestClient) -> None:
    semear_ranking()
    r = ranking(client, limit=100)  # sem login: o ranking é público
    assert r.status_code == 200
    corpo = r.json()
    assert nomes(corpo) == ["semente_001", "semente_002", "semente_003", "semente_004",
                            "semente_016", "semente_005"]
    assert [i["rank"] for i in corpo["items"]] == [1, 2, 3, 4, 5, 6]
    assert [i["rating"] for i in corpo["items"]] == [1500, 1400, 1400, 1300, 1250, 1200]
    assert corpo["min_games"] == 10 and corpo["next_cursor"] is None


def test_ranking_nao_expoe_ids_nem_e_mail(client: TestClient) -> None:
    semear_ranking()
    r = ranking(client, limit=100)
    for item in r.json()["items"]:
        assert set(item) == {"rank", "display_name", "avatar_key", "rating", "games_played"}
    assert "example.test" not in r.text and not UUID_RE.search(r.text)
    assert "@" not in r.text


def test_ranking_paginado_sem_repeticao_e_com_desempate_estavel(client: TestClient) -> None:
    semear_ranking()
    vistos: list[str] = []
    ranks: list[int] = []
    cursor: str | None = None
    paginas = 0
    while True:
        params = {"limit": 2, **({"cursor": cursor} if cursor else {})}
        corpo = ranking(client, **params).json()
        vistos += nomes(corpo)
        ranks += [i["rank"] for i in corpo["items"]]
        paginas += 1
        cursor = corpo["next_cursor"]
        if cursor is None:
            break
    assert paginas == 3
    assert vistos == ["semente_001", "semente_002", "semente_003", "semente_004",
                      "semente_016", "semente_005"]
    assert ranks == [1, 2, 3, 4, 5, 6]


def test_ranking_cursor_e_limite_invalidos_sao_recusados(client: TestClient) -> None:
    semear_ranking()
    for cursor in ("@@@", "bm90LW51bWJlcg", "LTU", "x" * 65):
        assert ranking(client, cursor=cursor).status_code == 422
    assert ranking(client, limit=0).status_code == 422
    assert ranking(client, limit=101).status_code == 422
    assert ranking(client, limit="abc").status_code == 422


def test_ranking_so_existe_para_jogo_ranqueado(client: TestClient) -> None:
    semear_ranking()
    for jogo in ("tictactoe", "checkers", "go", "x" * 40):  # velha sem ranking; damas: P-21
        r = ranking(client, jogo)
        assert r.status_code == 404, jogo


def test_ranking_vazio_e_valido(client: TestClient) -> None:
    r = ranking(client)
    assert r.status_code == 200 and r.json()["items"] == [] and r.json()["next_cursor"] is None


def test_ranking_tem_limite_de_taxa_por_ip(client: TestClient) -> None:
    for _ in range(120):
        assert ranking(client, limit=1).status_code == 200
    assert ranking(client, limit=1).status_code == 429


def test_escolha_de_visibilidade_do_adulto_vale_no_ranking(client: TestClient,
                                                           mailer: MemoryMailer) -> None:
    a = conta_logada(client, mailer, 1)
    definir_rating(1, 1300, jogadas=12)
    h = csrf(a)
    url = f"{API}/me/profile"
    assert nomes(ranking(client).json()) == ["jogador_teste_01"]
    assert a.patch(url, headers=h, json={"show_in_ranking": False}).status_code == 200
    assert nomes(ranking(client).json()) == []
    assert a.patch(url, headers=h, json={"show_in_ranking": True}).status_code == 200
    assert nomes(ranking(client).json()) == ["jogador_teste_01"]
    # Perfil privado tira do ranking e não dá para reentrar sem tornar o perfil público.
    assert a.patch(url, headers=h, json={"is_public": False}).status_code == 200
    assert nomes(ranking(client).json()) == []
    r = a.patch(url, headers=h, json={"show_in_ranking": True})
    assert r.status_code == 422 and r.json()["type"] == "ranking_requires_public_profile"
    r = a.patch(url, headers=h, json={"is_public": False, "show_in_ranking": True})
    assert r.status_code == 422
    ok = a.patch(url, headers=h, json={"is_public": True, "show_in_ranking": True})
    assert ok.status_code == 200 and ok.json()["show_in_ranking"] is True
    assert nomes(ranking(client).json()) == ["jogador_teste_01"]


def test_menor_so_entra_no_ranking_por_decisao_do_responsavel(client: TestClient,
                                                              mailer: MemoryMailer) -> None:
    resp = conta_logada(novo_cliente(client), mailer, 2)
    crianca = conta_logada(client, mailer, 1, age_band="12_15",
                           guardian_email="jogador2@example.test")
    ok = resp.post(f"{API}/guardian/links/confirm", headers=csrf(resp),
                   json={"token": mailer.last_token("jogador2@example.test")})
    assert ok.status_code == 200
    definir_rating(1, 1400, jogadas=15)
    assert nomes(ranking(client).json()) == []  # padrão protetivo: fora do ranking
    r = crianca.patch(f"{API}/me/profile", headers=csrf(crianca), json={"show_in_ranking": True})
    assert r.status_code == 403 and r.json()["type"] == "supervision_required"
    assert nomes(ranking(client).json()) == []
    url = f"{API}/guardian/children/{ok.json()['id']}/settings"
    on = resp.put(url, headers=csrf(resp), json={"profile_public": True, "show_in_ranking": True})
    assert on.status_code == 200
    assert nomes(ranking(client).json()) == ["jogador_teste_01"]
    # O próprio menor pode sair (reduzir exposição); o responsável pode tirá-lo de novo.
    off = crianca.patch(f"{API}/me/profile", headers=csrf(crianca),
                        json={"show_in_ranking": False})
    assert off.status_code == 200
    assert nomes(ranking(client).json()) == []


def test_conta_suspensa_some_do_ranking(client: TestClient,
                                                      mailer: MemoryMailer) -> None:
    conta_logada(client, mailer, 1)
    definir_rating(1, 1300, jogadas=12)
    assert nomes(ranking(client).json()) == ["jogador_teste_01"]
    with get_engine().begin() as conn:
        conn.exec_driver_sql("UPDATE users SET status = 'suspended'")
    assert nomes(ranking(client).json()) == []


def test_ranking_aparece_depois_de_dez_partidas_ranqueadas(
        client: TestClient, mailer: MemoryMailer, fake_clock: FakeClock) -> None:
    """Fluxo completo: 10 partidas ranqueadas (limite de 3 por hora contra o mesmo oponente)."""
    a, b = duas_contas(client, mailer)
    for i in range(10):
        if i and i % 3 == 0:
            fake_clock.advance(hours=1, minutes=1)
        mid = partida_ranqueada(a, b)
        jogar_abertura(a, b, mid)
        assert post(b, f"/matches/{mid}/resign").status_code == 200
    corpo = ranking(client).json()
    assert [(i["display_name"], i["games_played"]) for i in corpo["items"]] == [
        ("jogador_teste_01", 10), ("jogador_teste_02", 10)]
    assert corpo["items"][0]["rating"] > 1200 > corpo["items"][1]["rating"]
    stats = a.get(f"{API}/me/stats", params={"game_id": "chess"}).json()["games"][0]
    assert stats["rating"]["listed"] is True and stats["rating"]["games_until_listed"] == 0


# ---------- estatísticas (RF-021 / CA-021) ----------

def _semear_partidas(user_a: uuid.UUID, user_b: uuid.UUID, total: int = 500
                     ) -> list[tuple[str, str, str, datetime]]:
    """Partidas sintéticas de `user_a`; devolve (jogo, modo, resultado, fim) das que contam."""
    rng = random.Random(20261014)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    esperado: list[tuple[str, str, str, datetime]] = []
    with Session(get_engine()) as db:
        for i in range(total):
            jogo = rng.choice(["tictactoe", "checkers", "chess"])
            modo = rng.choice(["ai", "local", "online_casual", "online_ranked"])
            status = rng.choices(["finished", "annulled", "aborted", "in_progress"],
                                 weights=[80, 8, 6, 6])[0]
            assento = rng.choice([1, 2])
            resultado = rng.choice(["p1_win", "p2_win", "draw"]) if status == "finished" else None
            fim = base + timedelta(minutes=i) if status != "in_progress" else None
            razao = {"finished": "normal", "annulled": "annulled"}.get(status)
            mid = new_id()
            db.add(Match(id=mid, game_id=jogo, mode=modo, status=status, state={}, ply=4,
                         result=resultado, end_reason=razao, rules_version="teste-1",
                         started_at=base + timedelta(minutes=i), finished_at=fim))
            db.flush()
            if modo == "ai":
                db.add_all([MatchPlayer(match_id=mid, seat=assento, user_id=user_a),
                            MatchPlayer(match_id=mid, seat=3 - assento, user_id=None, is_ai=True)])
            elif modo == "local":
                db.add_all([MatchPlayer(match_id=mid, seat=s, user_id=user_a) for s in (1, 2)])
            else:
                db.add_all([MatchPlayer(match_id=mid, seat=assento, user_id=user_a),
                            MatchPlayer(match_id=mid, seat=3 - assento, user_id=user_b)])
            if status == "finished" and modo != "local" and resultado and fim:
                if resultado == "draw":
                    saida = "draw"
                else:
                    saida = "win" if (resultado == "p1_win") == (assento == 1) else "loss"
                esperado.append((jogo, modo, saida, fim))
        db.commit()
    return esperado


def test_ca_021_estatisticas_batem_com_a_contagem_direta_de_500_partidas(
        client: TestClient, mailer: MemoryMailer) -> None:
    a = conta_logada(client, mailer, 1)
    esperado = _semear_partidas(id_de(1), semear_usuario(1))
    assert len(esperado) > 250  # a base sintética tem volume suficiente
    r = a.get(f"{API}/me/stats")
    assert r.status_code == 200
    por_jogo = {g["game_id"]: g for g in r.json()["games"]}
    assert set(por_jogo) == {"tictactoe", "checkers", "chess"}
    for jogo, g in por_jogo.items():
        proprias = [e for e in esperado if e[0] == jogo]
        contagem = {s: sum(1 for e in proprias if e[2] == s) for s in ("win", "loss", "draw")}
        assert (g["wins"], g["losses"], g["draws"]) == (
            contagem["win"], contagem["loss"], contagem["draw"])
        assert g["played"] == len(proprias)
        for modo in g["by_mode"]:
            do_modo = [e for e in proprias if e[1] == modo["mode"]]
            assert modo["played"] == len(do_modo) > 0
            assert modo["wins"] == sum(1 for e in do_modo if e[2] == "win")
            assert modo["losses"] == sum(1 for e in do_modo if e[2] == "loss")
            assert modo["draws"] == sum(1 for e in do_modo if e[2] == "draw")
            assert modo["win_rate"] == round(modo["wins"] / modo["played"], 4)
        assert {m["mode"] for m in g["by_mode"]} == {e[1] for e in proprias}  # local nunca entra
        recentes = [e[2] for e in sorted(proprias, key=lambda e: e[3], reverse=True)]
        tamanho = 1
        while tamanho < len(recentes) and recentes[tamanho] == recentes[0]:
            tamanho += 1
        assert g["streak"] == {"kind": recentes[0], "length": tamanho}
    # Só o xadrez tem rating (velha: sem ranking; damas: P-21). Sem partidas ranqueadas reais
    # no servidor, o rating segue no valor inicial.
    assert por_jogo["tictactoe"]["rating"] is None and por_jogo["checkers"]["rating"] is None
    assert por_jogo["chess"]["rating"]["rating"] == 1200
    assert por_jogo["chess"]["rating"]["provisional"] is True


def test_estatisticas_filtram_por_jogo_e_recusam_jogo_desconhecido(
        client: TestClient, mailer: MemoryMailer) -> None:
    a = conta_logada(client, mailer, 1)
    r = a.get(f"{API}/me/stats", params={"game_id": "chess"})
    assert [g["game_id"] for g in r.json()["games"]] == ["chess"]
    zerado = r.json()["games"][0]
    assert zerado["played"] == 0 and zerado["win_rate"] is None
    assert zerado["streak"] == {"kind": "none", "length": 0} and zerado["by_mode"] == []
    assert a.get(f"{API}/me/stats", params={"game_id": "go"}).status_code == 404


def test_estatisticas_sao_so_do_proprio_usuario(client: TestClient, mailer: MemoryMailer) -> None:
    """SEC-05 / IDOR: não há como pedir as estatísticas de outra conta."""
    a, b = duas_contas(client, mailer)
    _semear_partidas(id_de(1), semear_usuario(1), total=60)
    total_a = sum(g["played"] for g in a.get(f"{API}/me/stats").json()["games"])
    assert total_a > 0
    tentativas = [{"user_id": str(id_de(1))}, {"user": "jogador_teste_01"},
                  {"game_id": "chess", "user_id": "x"}]
    for params in tentativas:
        r = b.get(f"{API}/me/stats", params=params)
        assert r.status_code == 200
        assert sum(g["played"] for g in r.json()["games"]) == 0  # sempre as de B
    anon = novo_cliente(client)
    assert anon.get(f"{API}/me/stats").status_code == 401


def test_estatisticas_mostram_rating_e_historico_da_partida_ranqueada(
        client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida_ranqueada(a, b)
    jogar_abertura(a, b, mid)
    post(b, f"/matches/{mid}/resign")
    xadrez = a.get(f"{API}/me/stats", params={"game_id": "chess"}).json()["games"][0]
    assert (xadrez["played"], xadrez["wins"], xadrez["losses"], xadrez["draws"]) == (1, 1, 0, 0)
    assert xadrez["by_mode"] == [{"mode": "online_ranked", "played": 1, "wins": 1, "losses": 0,
                                  "draws": 0, "win_rate": 1.0}]
    assert xadrez["streak"] == {"kind": "win", "length": 1}
    rating = xadrez["rating"]
    assert (rating["rating"], rating["games_played"]) == (1220, 1)
    assert rating["provisional"] is True and rating["listed"] is False
    assert rating["games_until_listed"] == 9
    assert [(h["before"], h["after"], h["delta"]) for h in rating["history"]] == [(1200, 1220, 20)]
    assert rating["history"][0]["match_id"] == mid
    do_b = b.get(f"{API}/me/stats", params={"game_id": "chess"}).json()["games"][0]
    assert do_b["streak"] == {"kind": "loss", "length": 1}
    assert [(h["before"], h["after"]) for h in do_b["rating"]["history"]] == [(1200, 1180)]


def test_estatisticas_ignoram_partida_anulada_local_e_em_andamento(
        client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida_ranqueada(a, b)
    jogar_abertura(a, b, mid, plies=2)
    assert post(b, f"/matches/{mid}/resign").json()["status"] == "annulled"
    local = post(a, "/matches", {"game_id": "chess", "mode": "local"}).json()
    post(a, f"/matches/{local['id']}/resign")
    post(a, "/matches", {"game_id": "chess", "mode": "online_casual"})  # sala aguardando
    xadrez = a.get(f"{API}/me/stats", params={"game_id": "chess"}).json()["games"][0]
    assert xadrez["played"] == 0 and xadrez["rating"]["games_played"] == 0
