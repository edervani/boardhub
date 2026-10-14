"""RF-012, RF-015, RF-019 (CA-012, CA-015, CA-019): partidas ranqueadas e rating Elo.

Contas e e-mails sintéticos (`@example.test`). O rating só muda no servidor, na transação que
encerra a partida ranqueada; partidas contra a IA, locais, casuais e anuladas não contam.
"""

import threading
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.models import Match, MatchPlayer, QueueEntry, RatingHistory
from app.services import match_service, online_service, rating_service
from tests.conftest import FakeClock, MemoryMailer
from tests.helpers import API, conta_logada, login, novo_cliente, register
from tests.online_helpers import criar_convite, duas_contas, entrar_por_codigo, lance, partida
from tests.ranking_helpers import (
    contar,
    definir_rating,
    jogar_abertura,
    partida_ranqueada,
    post,
    ratings_por_conta,
)
from tests.ws_helpers import abrir, ate, entrar, enviar

A, B = "jogador1@example.test", "jogador2@example.test"


def fila(c: TestClient, game: str = "chess", ranked: bool = True):
    return post(c, "/matchmaking/queue", {"game_id": game, "ranked": ranked})


def consulta(c: TestClient) -> dict[str, object]:
    return dict(c.get(f"{API}/matchmaking/queue").json())


# ---------- convite ranqueado: quem pode (RF-011, RF-002, DT-008, P-21) ----------

def test_convite_ranqueado_so_para_jogo_com_ranking(client: TestClient,
                                                    mailer: MemoryMailer) -> None:
    a, _ = duas_contas(client, mailer)
    corpo = {"mode": "online_ranked"}
    r = post(a, "/matches", {"game_id": "tictactoe", **corpo})
    assert r.status_code == 422 and r.json()["type"] == "ranked_not_available"
    # P-21: damas só entram no ranking depois de conferidas as regras (P-16).
    r = post(a, "/matches", {"game_id": "checkers", **corpo})
    assert r.status_code == 422 and r.json()["type"] == "ranked_not_available"
    sala = criar_convite(a, "chess", mode="online_ranked")
    assert sala["mode"] == "online_ranked" and sala["status"] == "waiting"


def test_catalogo_so_marca_xadrez_como_ranqueado(client: TestClient, mailer: MemoryMailer) -> None:
    a, _ = duas_contas(client, mailer)
    jogos = {g["id"]: g["ranked_enabled"] for g in a.get(f"{API}/games").json()}
    assert jogos == {"tictactoe": False, "checkers": False, "chess": True}


def test_conta_nao_verificada_nao_cria_nem_entra_em_sala_ranqueada(
        client: TestClient, mailer: MemoryMailer) -> None:
    a = conta_logada(client, mailer, 1)
    sem_verificar = novo_cliente(client)
    assert register(sem_verificar, 2).status_code == 201
    assert login(sem_verificar, 2).status_code == 200
    r = post(sem_verificar, "/matches", {"game_id": "chess", "mode": "online_ranked"})
    assert r.status_code == 403 and r.json()["type"] == "email_not_verified"
    sala = criar_convite(a, "chess", mode="online_ranked")
    r = entrar_por_codigo(sem_verificar, sala["invite_code"])
    assert r.status_code == 403 and r.json()["type"] == "email_not_verified"
    # A sala continua aguardando um oponente válido.
    assert a.get(f"{API}/matches/{sala['id']}").json()["status"] == "waiting"
    # A mesma conta joga o convite casual normalmente (em outro jogo: a sala acima segue ativa).
    casual = criar_convite(a, "checkers")
    assert entrar_por_codigo(sem_verificar, casual["invite_code"]).status_code == 200


def test_cliente_nao_escolhe_rating_nem_resultado(client: TestClient,
                                                  mailer: MemoryMailer) -> None:
    a, _ = duas_contas(client, mailer)
    base = {"game_id": "chess", "mode": "online_ranked"}
    for extra in ({"rating": 3000}, {"result": "p1_win"}, {"user_id": "x"}, {"ranked": True}):
        assert post(a, "/matches", {**base, **extra}).status_code == 422
    assert contar("ratings") == 0


# ---------- liquidação do rating (RF-019 / CA-019) ----------

def test_ca_019_vitoria_1200x1200_k40_da_mais_20_e_menos_20(
        client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida_ranqueada(a, b)
    jogar_abertura(a, b, mid)
    r = post(b, f"/matches/{mid}/resign")
    assert r.status_code == 200
    visao = r.json()
    assert visao["status"] == "finished" and visao["result"] == "p1_win"
    assert visao["rating_changes"] == [{"seat": 1, "before": 1200, "after": 1220},
                                       {"seat": 2, "before": 1200, "after": 1180}]
    assert ratings_por_conta() == {A: (1220, 1), B: (1180, 1)}
    # Persistido: a consulta posterior mostra o mesmo resultado.
    assert a.get(f"{API}/matches/{mid}").json()["rating_changes"] == visao["rating_changes"]
    with get_engine().connect() as conn:
        hist = conn.execute(text(
            "SELECT u.email, h.before, h.after FROM rating_history h "
            "JOIN users u ON u.id = h.user_id WHERE h.match_id = :m ORDER BY u.email"),
            {"m": mid}).all()
    assert [tuple(h) for h in hist] == [(A, 1200, 1220), (B, 1200, 1180)]


def test_partida_encerrada_pelo_motor_tambem_liquida(client: TestClient,
                                                     mailer: MemoryMailer) -> None:
    """Mate do pastor: o rating é liquidado no mesmo `submit_move` que dá o xeque-mate."""
    a, b = duas_contas(client, mailer)
    mid = partida_ranqueada(a, b)
    lances = ["e2e4", "e7e5", "f1c4", "b8c6", "d1h5", "g8f6", "h5f7"]
    for ply, mv in enumerate(lances):
        r = lance(a if ply % 2 == 0 else b, mid, mv, ply)
        assert r.status_code == 200, r.text
    visao = r.json()
    assert visao["status"] == "finished" and visao["result"] == "p1_win"
    assert visao["end_reason"] == "normal"
    assert ratings_por_conta() == {A: (1220, 1), B: (1180, 1)}


def test_desistencia_antes_do_segundo_lance_de_cada_lado_anula_sem_rating(
        client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida_ranqueada(a, b)
    jogar_abertura(a, b, mid, plies=3)  # as pretas ainda não fizeram o 2º lance
    r = post(b, f"/matches/{mid}/resign")
    assert r.status_code == 200
    visao = r.json()
    assert visao["status"] == "annulled" and visao["end_reason"] == "annulled"
    assert visao["result"] is None and visao["rating_changes"] == []
    assert contar("ratings") == 0 and contar("rating_history") == 0
    # A partida anulada libera os dois para jogar de novo.
    assert criar_convite(a, "chess", mode="online_ranked")["status"] == "waiting"


def test_desistencia_depois_do_segundo_lance_de_cada_lado_conta(
        client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida_ranqueada(a, b)
    jogar_abertura(a, b, mid, plies=4)
    assert post(a, f"/matches/{mid}/resign").json()["result"] == "p2_win"
    assert ratings_por_conta() == {A: (1180, 1), B: (1220, 1)}


def test_abandono_conta_e_abandono_precoce_anula(client: TestClient, mailer: MemoryMailer,
                                                 fake_clock: FakeClock) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida_ranqueada(a, b)
    jogar_abertura(a, b, mid, plies=4)  # é a vez das brancas (a), que somem
    fake_clock.advance(seconds=61)
    r = post(b, f"/matches/{mid}/claim-abandon")
    assert r.status_code == 200 and r.json()["end_reason"] == "abandon"
    assert ratings_por_conta() == {A: (1180, 1), B: (1220, 1)}
    # Abandono logo no 1º lance: anulada, sem rating novo.
    mid2 = partida_ranqueada(a, b)
    jogar_abertura(a, b, mid2, plies=1)
    fake_clock.advance(seconds=61)
    r = post(a, f"/matches/{mid2}/claim-abandon")
    assert r.status_code == 200 and r.json()["status"] == "annulled"
    assert ratings_por_conta() == {A: (1180, 1), B: (1220, 1)}


def test_empate_por_acordo_entre_iguais_conta_a_partida_sem_mudar_o_rating(
        client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida_ranqueada(a, b)
    jogar_abertura(a, b, mid, plies=4)
    assert post(a, f"/matches/{mid}/draw-offer").status_code == 200
    r = post(b, f"/matches/{mid}/draw-response", {"accept": True})
    assert r.status_code == 200 and r.json()["result"] == "draw"
    assert r.json()["rating_changes"] == [{"seat": 1, "before": 1200, "after": 1200},
                                          {"seat": 2, "before": 1200, "after": 1200}]
    assert ratings_por_conta() == {A: (1200, 1), B: (1200, 1)}


def test_empate_entre_desiguais_favorece_o_mais_fraco(client: TestClient,
                                                      mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    definir_rating(1, 1400)
    definir_rating(2, 1200)
    mid = partida_ranqueada(a, b)
    jogar_abertura(a, b, mid, plies=4)
    post(a, f"/matches/{mid}/draw-offer")
    post(b, f"/matches/{mid}/draw-response", {"accept": True})
    # E(1400 x 1200) = 0,759747: 40*(0,5-0,759747) = -10,39 -> -10; o outro lado +10.
    assert ratings_por_conta() == {A: (1390, 1), B: (1210, 1)}


def test_k20_depois_de_30_partidas_e_k_por_jogador(client: TestClient,
                                                   mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    definir_rating(1, 1500, jogadas=30)
    definir_rating(2, 1500, jogadas=30)
    mid = partida_ranqueada(a, b)
    jogar_abertura(a, b, mid)
    post(b, f"/matches/{mid}/resign")
    assert ratings_por_conta() == {A: (1510, 31), B: (1490, 31)}
    # Novato (29 partidas, K=40) vence veterano (30, K=20): +20 e -10 (não é soma zero).
    mid2 = partida_ranqueada(b, a)
    definir_rating(1, 1200, jogadas=29)
    definir_rating(2, 1200, jogadas=30)
    jogar_abertura(b, a, mid2)
    post(b, f"/matches/{mid2}/resign")  # b (veterano) desiste; a (novato) vence
    assert ratings_por_conta() == {A: (1220, 30), B: (1190, 31)}


# ---------- o que NÃO altera rating ----------

def test_partidas_casual_ia_e_local_nao_alteram_rating(client: TestClient,
                                                       mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    casual = partida(a, b, "chess")
    for i, mv in enumerate(["e2e4", "e7e5", "g1f3", "b8c6"]):
        assert lance(a if i % 2 == 0 else b, casual["id"], mv, i).status_code == 200
    assert post(b, f"/matches/{casual['id']}/resign").json()["result"] == "p1_win"
    for corpo in ({"game_id": "chess", "mode": "ai", "ai_level": 1},
                  {"game_id": "chess", "mode": "local"}):
        m = post(a, "/matches", corpo).json()
        assert post(a, f"/matches/{m['id']}/resign").status_code == 200
    assert contar("ratings") == 0 and contar("rating_history") == 0
    with get_engine().connect() as conn:
        assert conn.execute(text(
            "SELECT count(*) FROM match_players WHERE rating_after IS NOT NULL")).scalar_one() == 0


def test_resultado_ranqueado_so_e_calculado_pelo_servidor(client: TestClient,
                                                         mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida_ranqueada(a, b)
    jogar_abertura(a, b, mid)
    r = post(b, f"/matches/{mid}/resign", {"result": "p2_win", "rating": 9999})
    assert r.status_code == 200
    assert r.json()["result"] == "p1_win"
    assert ratings_por_conta() == {A: (1220, 1), B: (1180, 1)}


def test_terceiro_nao_ve_nem_dispara_a_liquidacao(client: TestClient,
                                                  mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    c = conta_logada(novo_cliente(client), mailer, 3)
    mid = partida_ranqueada(a, b)
    jogar_abertura(a, b, mid)
    assert c.get(f"{API}/matches/{mid}").status_code == 404
    assert post(c, f"/matches/{mid}/resign").status_code == 404
    assert contar("ratings") == 0


# ---------- atomicidade, idempotência e concorrência ----------

def test_falha_depois_do_calculo_nao_grava_nada(client: TestClient, mailer: MemoryMailer,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    """CA-019: se algo falha depois de calcular, nem partida nem rating mudam."""
    a, b = duas_contas(client, mailer)
    mid = partida_ranqueada(a, b)
    jogar_abertura(a, b, mid)
    real = rating_service.settle

    def com_falha(db: Session, match: Match, players: list[MatchPlayer]):
        real(db, match, players)
        raise RuntimeError("falha simulada depois do cálculo")

    monkeypatch.setattr(match_service.rating_service, "settle", com_falha)
    try:
        post(b, f"/matches/{mid}/resign")
    except RuntimeError:
        pass
    monkeypatch.undo()
    assert contar("ratings") == 0 and contar("rating_history") == 0
    visao = a.get(f"{API}/matches/{mid}").json()
    assert visao["status"] == "in_progress" and visao["result"] is None
    # Depois da falha a desistência funciona normalmente, uma única vez.
    assert post(b, f"/matches/{mid}/resign").status_code == 200
    assert ratings_por_conta() == {A: (1220, 1), B: (1180, 1)}


def test_liquidar_duas_vezes_e_idempotente(client: TestClient, mailer: MemoryMailer,
                                           db: Session) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida_ranqueada(a, b)
    jogar_abertura(a, b, mid)
    post(b, f"/matches/{mid}/resign")
    match = db.get(Match, uuid.UUID(mid))
    assert match is not None
    players = list(db.scalars(select(MatchPlayer).where(MatchPlayer.match_id == match.id)
                              .order_by(MatchPlayer.seat)))
    de_novo = rating_service.settle(db, match, players)
    db.commit()
    assert [(c.seat, c.before, c.after) for c in de_novo] == [(1, 1200, 1220), (2, 1200, 1180)]
    assert ratings_por_conta() == {A: (1220, 1), B: (1180, 1)}
    assert contar("rating_history") == 2


def test_historico_tem_uma_linha_por_usuario_e_partida(client: TestClient, mailer: MemoryMailer,
                                                      db: Session) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida_ranqueada(a, b)
    jogar_abertura(a, b, mid)
    post(b, f"/matches/{mid}/resign")
    existente = db.scalar(select(RatingHistory).limit(1))
    assert existente is not None
    db.add(RatingHistory(user_id=existente.user_id, game_id="chess", match_id=existente.match_id,
                         before=1, after=2))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_desistencias_simultaneas_geram_um_unico_ajuste(client: TestClient,
                                                        mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida_ranqueada(a, b)
    jogar_abertura(a, b, mid)
    barreira = threading.Barrier(2)
    codigos: list[int] = []

    def desistir(c: TestClient) -> None:
        barreira.wait()
        codigos.append(post(c, f"/matches/{mid}/resign").status_code)

    threads = [threading.Thread(target=desistir, args=(c,)) for c in (a, b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert sorted(codigos) == [200, 409]
    assert contar("rating_history") == 2
    ratings = ratings_por_conta()
    assert sorted(ratings.values()) == [(1180, 1), (1220, 1)]  # um ajuste só, soma zero
    with get_engine().connect() as conn:
        assert conn.execute(text(
            "SELECT count(*) FROM match_players WHERE rating_after IS NOT NULL")).scalar_one() == 2


def test_lance_final_e_desistencia_simultaneos_geram_um_unico_ajuste(
        client: TestClient, mailer: MemoryMailer) -> None:
    """Mate do pastor no último lance enquanto o adversário desiste: um só resultado."""
    a, b = duas_contas(client, mailer)
    mid = partida_ranqueada(a, b)
    for ply, mv in enumerate(["e2e4", "e7e5", "f1c4", "b8c6", "d1h5", "g8f6"]):
        assert lance(a if ply % 2 == 0 else b, mid, mv, ply).status_code == 200
    barreira = threading.Barrier(2)
    codigos: list[int] = []

    def mate() -> None:
        barreira.wait()
        codigos.append(lance(a, mid, "h5f7", 6).status_code)

    def desistir() -> None:
        barreira.wait()
        codigos.append(post(b, f"/matches/{mid}/resign").status_code)

    threads = [threading.Thread(target=mate), threading.Thread(target=desistir)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert 200 in codigos and contar("rating_history") == 2
    # Em qualquer ordem, as brancas vencem: 1220 x 1180, uma única vez.
    assert ratings_por_conta() == {A: (1220, 1), B: (1180, 1)}


# ---------- tempo real ----------

def test_match_ended_traz_a_variacao_dos_dois_assentos(client: TestClient,
                                                       mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida_ranqueada(a, b)
    jogar_abertura(a, b, mid)
    esperado = [{"seat": 1, "before": 1200, "after": 1220},
                {"seat": 2, "before": 1200, "after": 1180}]
    with abrir(a) as wa, abrir(b) as wb:
        entrar(wa, mid, last=4)
        entrar(wb, mid, last=4)
        req = enviar(wb, "resign", {"match_id": mid})
        proprio = ate(wb, "match_ended", reply_to=req)
        outro = ate(wa, "match_ended")
    assert proprio["payload"]["rating_changes"] == esperado
    assert outro["payload"]["rating_changes"] == esperado
    assert ratings_por_conta() == {A: (1220, 1), B: (1180, 1)}


# ---------- fila ranqueada (RF-012 / CA-012) ----------

def test_fila_ranqueada_so_para_jogo_com_ranking(client: TestClient, mailer: MemoryMailer) -> None:
    a, _ = duas_contas(client, mailer)
    for jogo in ("tictactoe", "checkers"):
        r = fila(a, jogo)
        assert r.status_code == 422 and r.json()["type"] == "ranked_not_available"
    assert consulta(a)["state"] == "idle"


def test_ca_012_ratings_1200_e_1250_sao_pareados(client: TestClient,
                                                 mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    definir_rating(2, 1250)
    r1 = fila(a)
    assert r1.status_code == 202
    assert r1.json()["state"] == "queued" and r1.json()["ranked"] is True
    assert r1.json()["rating_window"] == 100
    r2 = fila(b)
    assert r2.status_code == 200 and r2.json()["state"] == "matched"
    visao = b.get(f"{API}/matches/{r2.json()['match_id']}").json()
    assert visao["mode"] == "online_ranked" and visao["status"] == "in_progress"
    assert consulta(a)["state"] == "matched"
    # Quem esperava recebeu o mesmo par; ninguém ficou na fila.
    assert contar("matchmaking_queue") == 0


def test_janela_de_rating_cresce_com_a_espera_ate_400(client: TestClient, mailer: MemoryMailer,
                                                      fake_clock: FakeClock) -> None:
    a, b = duas_contas(client, mailer)
    definir_rating(2, 1500)  # 300 de diferença: só cabe depois de 40 s (100 + 4*50)
    assert fila(a).status_code == 202
    assert fila(b).status_code == 202
    fake_clock.advance(seconds=21)
    assert consulta(a)["state"] == "queued" and consulta(b)["rating_window"] == 200
    fake_clock.advance(seconds=21)
    estado = consulta(a)  # a janela de 300 já cobre a diferença
    assert estado["state"] == "matched"
    assert consulta(b)["state"] == "matched"
    with get_engine().connect() as conn:
        modo = conn.execute(text("SELECT mode FROM matches")).scalar_one()
    assert modo == "online_ranked"


def test_diferenca_acima_de_400_nunca_pareia(client: TestClient, mailer: MemoryMailer,
                                            fake_clock: FakeClock) -> None:
    a, b = duas_contas(client, mailer)
    definir_rating(2, 1700)
    fila(a)
    fila(b)
    for _ in range(10):
        fake_clock.advance(seconds=20)
        assert consulta(a)["state"] == "queued"
        assert consulta(b)["state"] == "queued"
    assert consulta(a)["rating_window"] == 400
    assert contar("matches") == 0


def test_fila_ranqueada_e_casual_nao_se_misturam(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    assert fila(a, ranked=True).status_code == 202
    assert fila(b, ranked=False).status_code == 202
    assert contar("matches") == 0
    # Quem troca de fila sai da anterior e entra na outra.
    r = fila(b, ranked=True)
    assert r.status_code == 200 and r.json()["state"] == "matched"
    assert contar("matchmaking_queue") == 1  # só a entrada de `a`, ainda a consumir


def test_pareia_com_o_oponente_de_rating_mais_proximo(client: TestClient, mailer: MemoryMailer,
                                                      fake_clock: FakeClock, db: Session) -> None:
    contas = [conta_logada(novo_cliente(client), mailer, n) for n in range(1, 5)]
    entrante, c2, c3, c4 = contas
    for n, rating in ((2, 1050), (3, 1180), (4, 1300)):
        definir_rating(n, rating)
    for c in (c2, c3, c4):
        assert fila(c).status_code == 202  # nenhum par cabe na janela inicial de ±100
    fake_clock.advance(seconds=15)  # janela dos que esperam: ±150
    r = fila(entrante)
    assert r.status_code == 200
    adversario = db.scalar(
        select(MatchPlayer.user_id).where(MatchPlayer.match_id == uuid.UUID(r.json()["match_id"]),
                                          MatchPlayer.user_id != _id(db, 1)))
    assert adversario == _id(db, 3)  # 1180 está a 20 pontos; 1050 e 1300, a 150 e 100


def _id(db: Session, n: int) -> uuid.UUID:
    found = db.scalar(text("SELECT id FROM users WHERE email = :e").bindparams(
        e=f"jogador{n}@example.test"))
    assert found is not None
    return uuid.UUID(str(found))


def test_fila_ranqueada_concorrente_nunca_poe_usuario_em_duas_partidas(
        client: TestClient, mailer: MemoryMailer) -> None:
    contas = [conta_logada(novo_cliente(client), mailer, n) for n in range(1, 5)]
    barreira = threading.Barrier(len(contas))
    codigos: list[int] = []

    def entrar_na_fila(c: TestClient) -> None:
        barreira.wait()
        codigos.append(fila(c).status_code)

    threads = [threading.Thread(target=entrar_na_fila, args=(c,)) for c in contas]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert sorted(codigos) == [200, 200, 202, 202]
    for c in contas:
        c.get(f"{API}/matchmaking/queue")
    with get_engine().connect() as conn:
        linhas = conn.execute(text("SELECT user_id FROM match_players")).scalars().all()
        modos = conn.execute(text("SELECT DISTINCT mode FROM matches")).scalars().all()
    assert len(linhas) == 4 and len(set(linhas)) == 4
    assert modos == ["online_ranked"]
    assert contar("matchmaking_queue") == 0


def test_entrada_ranqueada_na_fila_fica_marcada_no_banco(client: TestClient, mailer: MemoryMailer,
                                                        db: Session) -> None:
    a, _ = duas_contas(client, mailer)
    fila(a)
    entrada = db.scalar(select(QueueEntry))
    assert entrada is not None and entrada.ranked is True
    assert online_service.rating_window(0) == 100 and online_service.rating_window(95) == 400
    assert online_service.rating_window(10_000) == 400


# ---------- antiabuso: mesmo oponente (RF-012, SEC-13) ----------

def test_no_maximo_3_partidas_ranqueadas_por_hora_contra_o_mesmo_oponente(
        client: TestClient, mailer: MemoryMailer, fake_clock: FakeClock) -> None:
    a, b = duas_contas(client, mailer)
    for _ in range(3):
        mid = partida_ranqueada(a, b)
        jogar_abertura(a, b, mid)
        assert post(b, f"/matches/{mid}/resign").status_code == 200
    # Quarta tentativa na mesma hora: por convite e pela fila.
    sala = criar_convite(a, "chess", mode="online_ranked")
    r = entrar_por_codigo(b, sala["invite_code"])
    assert r.status_code == 409 and r.json()["type"] == "repeat_opponent_limit"
    post(a, f"/matches/{sala['id']}/cancel")
    assert fila(a).status_code == 202
    assert fila(b).status_code == 202  # não pareia com o mesmo oponente
    with get_engine().connect() as conn:
        validas = conn.execute(text(
            "SELECT count(*) FROM matches WHERE status <> 'aborted'")).scalar_one()
    assert validas == 3
    # Passada a hora, volta a valer.
    fake_clock.advance(hours=1, minutes=1)
    sala2 = criar_convite(a, "chess", mode="online_ranked")
    assert entrar_por_codigo(b, sala2["invite_code"]).status_code == 200


def test_partidas_casuais_nao_contam_no_limite_de_repeticao(client: TestClient,
                                                           mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    for _ in range(4):
        sala = criar_convite(a, "chess")
        assert entrar_por_codigo(b, sala["invite_code"]).status_code == 200
        post(b, f"/matches/{sala['id']}/resign")
    sala = criar_convite(a, "chess", mode="online_ranked")
    assert entrar_por_codigo(b, sala["invite_code"]).status_code == 200


def test_fila_ranqueada_exige_login_csrf_e_corpo_valido(client: TestClient,
                                                         mailer: MemoryMailer) -> None:
    a, _ = duas_contas(client, mailer)
    corpo = {"game_id": "chess", "ranked": True}
    assert a.post(f"{API}/matchmaking/queue", json=corpo).status_code == 403  # sem CSRF
    anon = novo_cliente(client)
    assert anon.post(f"{API}/matchmaking/queue", json=corpo).status_code in (401, 403)
    assert post(a, "/matchmaking/queue", {**corpo, "rating": 2000}).status_code == 422
