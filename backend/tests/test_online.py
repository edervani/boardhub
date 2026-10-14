"""RF-008, RF-011, RF-012, RF-015 (CA-008, CA-011, CA-012, CA-015) por REST; modo não ranqueado.

Contas e e-mails sintéticos (`@example.test`).
"""

import re
import threading
import uuid
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.models import DrawOffer, Match, QueueEntry
from tests.conftest import FakeClock, MemoryMailer
from tests.helpers import API, conta_logada, csrf, login, novo_cliente, register
from tests.online_helpers import (
    criar_convite,
    duas_contas,
    entrar_por_codigo,
    jogar_aleatorio,
    lance,
    partida,
)

CODIGO = re.compile(r"[A-HJKMNP-Z2-9]{8}")


def post(c: TestClient, caminho: str, corpo: dict[str, object] | None = None):
    return c.post(f"{API}{caminho}", headers=csrf(c), json=corpo)


@contextmanager
def classificacao(jogo: str, faixa: str) -> Iterator[None]:
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE games SET age_rating = :r WHERE id = :g"),
                     {"r": faixa, "g": jogo})
    try:
        yield
    finally:
        with get_engine().begin() as conn:
            conn.execute(text("UPDATE games SET age_rating = 'L' WHERE id = :g"), {"g": jogo})


# ---------- convite por código (RF-011 / CA-011) ----------

def test_convite_devolve_o_codigo_uma_unica_vez_e_guarda_so_o_hmac(
        client: TestClient, mailer: MemoryMailer, db: Session) -> None:
    a, _ = duas_contas(client, mailer)
    sala = criar_convite(a)
    assert sala["status"] == "waiting" and sala["mode"] == "online_casual"
    assert CODIGO.fullmatch(sala["invite_code"])
    assert sala["invite_expires_at"] is not None
    assert [s["is_you"] for s in sala["seats"]] == [True]
    de_novo = a.get(f"{API}/matches/{sala['id']}").json()
    assert de_novo["invite_code"] is None  # nunca mais exibido
    linha = db.scalar(select(Match).where(Match.id == uuid.UUID(sala["id"])))
    assert linha is not None and linha.invite_code_hash is not None
    assert len(linha.invite_code_hash) == 32
    assert sala["invite_code"].encode() not in linha.invite_code_hash


def test_entrar_por_codigo_inicia_a_partida_com_assentos_distintos(
        client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    sala = criar_convite(a, preferred_seat=2)
    resp = entrar_por_codigo(b, sala["invite_code"])
    assert resp.status_code == 200
    visao_b = resp.json()
    assert visao_b["status"] == "in_progress" and visao_b["ply"] == 0
    assert visao_b["legal_moves"] == [str(i) for i in range(9)]
    visao_a = a.get(f"{API}/matches/{sala['id']}").json()
    assento_a = next(s["seat"] for s in visao_a["seats"] if s["is_you"])
    assento_b = next(s["seat"] for s in visao_b["seats"] if s["is_you"])
    assert (assento_a, assento_b) == (2, 1)  # escolha do criador respeitada
    nomes = {p["seat"]: p["display_name"] for p in visao_b["players"]}
    assert nomes == {1: "jogador_teste_02", 2: "jogador_teste_01"}


def test_sem_preferencia_o_servidor_sorteia_assentos_distintos(
        client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    sala = criar_convite(a)  # sem preferred_seat
    visao = entrar_por_codigo(b, sala["invite_code"]).json()
    assert sorted(s["seat"] for s in visao["seats"]) == [1, 2]
    assert sum(1 for s in visao["seats"] if s["is_you"]) == 1


def test_codigo_aceita_minusculas_e_hifen(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    codigo = criar_convite(a)["invite_code"]
    digitado = f"{codigo[:4].lower()}-{codigo[4:].lower()}"
    assert entrar_por_codigo(b, digitado).status_code == 200


def test_erros_ao_entrar_por_codigo(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    c = conta_logada(novo_cliente(client), mailer, 3)
    codigo = criar_convite(a)["invite_code"]
    assert entrar_por_codigo(a, codigo).status_code == 403  # criador não ocupa as duas cadeiras
    for ruim in ("ZZZZZZZZ", "curto", "!!!!!!!!", "A" * 30):
        r = entrar_por_codigo(b, ruim)
        assert r.status_code == 404 and r.json()["type"] == "invite_not_found"
    assert entrar_por_codigo(b, codigo).status_code == 200
    assert entrar_por_codigo(c, codigo).status_code == 409  # sala cheia


def test_codigo_expirado_e_recusado_e_a_sala_some(client: TestClient, mailer: MemoryMailer,
                                                  fake_clock: FakeClock) -> None:
    a, b = duas_contas(client, mailer)
    sala = criar_convite(a)
    fake_clock.advance(minutes=16)
    assert entrar_por_codigo(b, sala["invite_code"]).status_code == 404
    assert a.get(f"{API}/matches/{sala['id']}").json()["status"] == "aborted"
    # O convite vencido não bloqueia um novo (DT-010 só vale para salas ativas).
    assert criar_convite(a)["status"] == "waiting"


def test_criador_cancela_antes_de_alguem_entrar(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    sala = criar_convite(a)
    assert post(b, f"/matches/{sala['id']}/cancel").status_code == 404  # IDOR
    assert post(a, f"/matches/{sala['id']}/cancel").status_code == 204
    assert entrar_por_codigo(b, sala["invite_code"]).status_code == 404
    assert criar_convite(a)["status"] == "waiting"  # liberou o limite de uma sala por jogo


def test_nao_cancela_partida_em_andamento(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    m = partida(a, b)
    assert post(a, f"/matches/{m['id']}/cancel").status_code == 409


def test_uma_partida_online_ativa_por_jogo(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    criar_convite(a)
    r = post(a, "/matches", {"game_id": "tictactoe", "mode": "online_casual"})
    assert r.status_code == 409 and r.json()["type"] == "active_online_match"
    assert criar_convite(a, "checkers")["status"] == "waiting"  # outro jogo: permitido
    # Quem já está em partida também não entra em outra do mesmo jogo.
    sala_b = criar_convite(b, "chess")
    assert entrar_por_codigo(a, sala_b["invite_code"]).status_code == 200
    outra = criar_convite(b, "checkers")
    assert entrar_por_codigo(a, outra["invite_code"]).status_code == 409


def test_convite_exige_login_csrf_e_corpo_valido(client: TestClient, mailer: MemoryMailer) -> None:
    a, _ = duas_contas(client, mailer)
    anon = novo_cliente(client)
    corpo = {"game_id": "tictactoe", "mode": "online_casual"}
    assert anon.post(f"{API}/matches", json=corpo).status_code in (401, 403)
    assert a.post(f"{API}/matches", json=corpo).status_code == 403  # sem CSRF
    assert post(a, "/matches", {**corpo, "ai_level": 3}).status_code == 422
    assert post(a, "/matches", {**corpo, "mode": "online_ranked"}).status_code == 422  # sem ranking
    assert post(a, "/matches/join", {"invite_code": "ABCDEFGH", "user_id": "x"}).status_code == 422


def test_limite_de_20_tentativas_de_codigo_por_hora(client: TestClient,
                                                    mailer: MemoryMailer) -> None:
    _, b = duas_contas(client, mailer)
    for _ in range(20):
        assert entrar_por_codigo(b, "ZZZZZZZZ").status_code == 404
    assert entrar_por_codigo(b, "ZZZZZZZZ").status_code == 429


# ---------- ECA Digital: idade e supervisão ----------

def test_menor_de_12_sem_responsavel_nao_joga_online(client: TestClient,
                                                     mailer: MemoryMailer) -> None:
    crianca = conta_logada(client, mailer, 1, age_band="under_12",
                           guardian_email="jogador9@example.test")
    r = post(crianca, "/matches", {"game_id": "tictactoe", "mode": "online_casual"})
    assert r.status_code == 403 and r.json()["type"] == "guardian_pending"
    assert entrar_por_codigo(crianca, "ABCDEFGH").status_code == 403
    assert post(crianca, "/matchmaking/queue", {"game_id": "tictactoe"}).status_code == 403


def test_jogo_acima_da_classificacao_da_faixa_nao_aparece_nem_entra(
        client: TestClient, mailer: MemoryMailer) -> None:
    adulto = conta_logada(client, mailer, 1)
    jovem = conta_logada(novo_cliente(client), mailer, 2, age_band="12_15",
                         guardian_email="jogador9@example.test")
    with classificacao("chess", "16"):
        r = post(jovem, "/matches", {"game_id": "chess", "mode": "online_casual"})
        assert r.status_code == 404 and r.json()["type"] == "game_not_found"
        sala = criar_convite(adulto, "chess")
        # Não revela que o código existe para quem não pode jogar aquele jogo.
        assert entrar_por_codigo(jovem, sala["invite_code"]).status_code == 404


def test_conta_supervisionada_nao_entra_na_fila_aberta(client: TestClient,
                                                       mailer: MemoryMailer) -> None:
    jovem = conta_logada(client, mailer, 1, age_band="12_15",
                         guardian_email="jogador9@example.test")
    r = post(jovem, "/matchmaking/queue", {"game_id": "tictactoe"})
    assert r.status_code == 403 and r.json()["type"] == "open_matchmaking_disabled"
    # Convite por código segue permitido (sem chat e sem desconhecidos).
    assert criar_convite(jovem)["status"] == "waiting"


# ---------- fila de pareamento (RF-012 / CA-012) ----------

def test_dois_usuarios_na_fila_do_mesmo_jogo_sao_pareados(client: TestClient,
                                                         mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    r1 = post(a, "/matchmaking/queue", {"game_id": "tictactoe"})
    assert r1.status_code == 202 and r1.json()["state"] == "queued"
    assert a.get(f"{API}/matchmaking/queue").json()["state"] == "queued"
    r2 = post(b, "/matchmaking/queue", {"game_id": "tictactoe"})
    assert r2.status_code == 200 and r2.json()["state"] == "matched"
    id_partida = r2.json()["match_id"]
    consumo = a.get(f"{API}/matchmaking/queue").json()
    assert consumo["state"] == "matched" and consumo["match_id"] == id_partida
    assert a.get(f"{API}/matchmaking/queue").json()["state"] == "idle"  # consumido
    visao = a.get(f"{API}/matches/{id_partida}").json()
    assert visao["status"] == "in_progress" and visao["mode"] == "online_casual"
    assert sorted(s["seat"] for s in visao["seats"]) == [1, 2]


def test_jogos_diferentes_nao_se_pareiam(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    assert post(a, "/matchmaking/queue", {"game_id": "tictactoe"}).json()["state"] == "queued"
    assert post(b, "/matchmaking/queue", {"game_id": "checkers"}).json()["state"] == "queued"


def test_sair_da_fila_e_quem_ja_foi_pareado_nao_sai(client: TestClient,
                                                    mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    post(a, "/matchmaking/queue", {"game_id": "tictactoe"})
    assert a.delete(f"{API}/matchmaking/queue", headers=csrf(a)).status_code == 204
    assert post(b, "/matchmaking/queue", {"game_id": "tictactoe"}).json()["state"] == "queued"
    post(a, "/matchmaking/queue", {"game_id": "tictactoe"})  # pareia com b
    r = b.delete(f"{API}/matchmaking/queue", headers=csrf(b))
    assert r.status_code == 409 and r.json()["type"] == "already_matched"


def test_fila_exige_email_verificado(client: TestClient, mailer: MemoryMailer) -> None:
    assert register(client, 1).status_code == 201
    assert login(client, 1).status_code == 200  # sem confirmar o e-mail
    r = post(client, "/matchmaking/queue", {"game_id": "tictactoe"})
    assert r.status_code == 403 and r.json()["type"] == "email_not_verified"


def test_depois_de_60_segundos_a_fila_oferece_a_ia(client: TestClient, mailer: MemoryMailer,
                                                  fake_clock: FakeClock) -> None:
    a, _ = duas_contas(client, mailer)
    post(a, "/matchmaking/queue", {"game_id": "tictactoe"})
    assert a.get(f"{API}/matchmaking/queue").json()["offer_ai"] is False
    fake_clock.advance(seconds=61)
    estado = a.get(f"{API}/matchmaking/queue").json()
    assert estado["offer_ai"] is True and estado["waited_seconds"] >= 61


def test_entrada_abandonada_na_fila_e_ignorada(client: TestClient, mailer: MemoryMailer,
                                               fake_clock: FakeClock, db: Session) -> None:
    a, b = duas_contas(client, mailer)
    post(a, "/matchmaking/queue", {"game_id": "tictactoe"})
    fake_clock.advance(seconds=46)  # a parou de consultar a fila
    assert post(b, "/matchmaking/queue", {"game_id": "tictactoe"}).json()["state"] == "queued"
    assert db.scalar(select(QueueEntry).where(QueueEntry.matched_match_id.is_not(None))) is None


def test_entrar_em_partida_online_tira_o_usuario_da_fila(client: TestClient,
                                                         mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    post(a, "/matchmaking/queue", {"game_id": "tictactoe"})
    sala = criar_convite(b, "checkers")
    assert entrar_por_codigo(a, sala["invite_code"]).status_code == 200
    assert a.get(f"{API}/matchmaking/queue").json()["state"] == "idle"


def test_fila_concorrente_nunca_poe_usuario_em_duas_partidas(client: TestClient,
                                                            mailer: MemoryMailer) -> None:
    contas = [conta_logada(novo_cliente(client), mailer, n) for n in range(1, 5)]
    barreira = threading.Barrier(len(contas))
    codigos: list[int] = []

    def entrar(c: TestClient) -> None:
        barreira.wait()
        codigos.append(post(c, "/matchmaking/queue", {"game_id": "tictactoe"}).status_code)

    threads = [threading.Thread(target=entrar, args=(c,)) for c in contas]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert sorted(codigos) == [200, 200, 202, 202]
    for c in contas:  # quem esperava consome o pareamento
        c.get(f"{API}/matchmaking/queue")
    with get_engine().connect() as conn:
        linhas = conn.execute(text("SELECT user_id FROM match_players")).scalars().all()
        fila = conn.execute(text("SELECT count(*) FROM matchmaking_queue")).scalar_one()
    assert len(linhas) == 4 and set(Counter(linhas).values()) == {1}
    assert fila == 0


# ---------- lobby (RF-008) ----------

def test_lobby_lista_partidas_em_andamento_e_salas_aguardando(
        client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    partida(a, b, "checkers", seat=1)
    sala = criar_convite(a, "chess")
    post(a, "/matches", {"game_id": "tictactoe", "mode": "local"})
    itens = a.get(f"{API}/me/active-matches").json()
    por_modo = {(i["game_id"], i["mode"]): i for i in itens}
    assert set(por_modo) == {("checkers", "online_casual"), ("chess", "online_casual"),
                             ("tictactoe", "local")}
    jogo = por_modo[("checkers", "online_casual")]
    assert jogo["status"] == "in_progress" and jogo["your_turn"] is True
    assert jogo["opponent_name"] == "jogador_teste_02"
    espera = por_modo[("chess", "online_casual")]
    assert espera["status"] == "waiting" and espera["invite_expires_at"] is not None
    assert espera["id"] == sala["id"]
    # O oponente vê a mesma partida; a sala aguardando é só de quem a criou.
    do_b = b.get(f"{API}/me/active-matches").json()
    assert [i["game_id"] for i in do_b] == ["checkers"] and do_b[0]["your_turn"] is False


def test_lobby_exige_login(client: TestClient) -> None:
    assert novo_cliente(client).get(f"{API}/me/active-matches").status_code == 401


# ---------- autorização (SEC-05 / IDOR) ----------

def test_terceiro_nao_ve_nem_age_na_partida_online(client: TestClient,
                                                   mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    m = partida(a, b, "chess")
    intruso = conta_logada(novo_cliente(client), mailer, 3)
    mid = m["id"]
    assert intruso.get(f"{API}/matches/{mid}").status_code == 404
    assert intruso.get(f"{API}/matches/{mid}/moves").status_code == 404
    assert lance(intruso, mid, "e2e4", 0).status_code == 404
    for caminho in ("resign", "draw-offer", "claim-abandon", "cancel"):
        assert post(intruso, f"/matches/{mid}/{caminho}").status_code == 404, caminho
    assert post(intruso, f"/matches/{mid}/draw-response", {"accept": True}).status_code == 404
    assert intruso.get(f"{API}/me/active-matches").json() == []


# ---------- lances por REST em partida online (RF-013) ----------

def test_lance_fora_de_turno_ilegal_e_desatualizado(client: TestClient,
                                                    mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    m = partida(a, b)
    mid = m["id"]
    r = lance(b, mid, "0", 0)
    assert r.status_code == 403 and r.json()["type"] == "not_your_turn"
    assert lance(a, mid, "9", 0).status_code == 422
    assert lance(a, mid, "0", 4).json()["type"] == "stale_state"
    ok = lance(a, mid, "0", 0)
    assert ok.status_code == 200 and ok.json()["to_move_seat"] == 2
    assert lance(b, mid, "0", 1).json()["type"] == "illegal_move"  # casa ocupada


def test_mesmo_client_move_id_grava_um_lance(client: TestClient, mailer: MemoryMailer,
                                             db: Session) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b)["id"]
    cid = str(uuid.uuid4())
    assert lance(a, mid, "4", 0, cid).status_code == 200
    assert lance(a, mid, "4", 0, cid).status_code == 200
    n = db.execute(text("SELECT count(*) FROM match_moves")).scalar_one()
    assert n == 1


def test_lances_simultaneos_do_mesmo_jogador_aplicam_so_um(client: TestClient,
                                                           mailer: MemoryMailer,
                                                           db: Session) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b)["id"]
    barreira = threading.Barrier(2)
    codigos: list[int] = []

    def jogar(move: str) -> None:
        barreira.wait()
        codigos.append(lance(a, mid, move, 0).status_code)

    threads = [threading.Thread(target=jogar, args=(mv,)) for mv in ("0", "1")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert sorted(codigos) == [200, 409]
    assert db.execute(text("SELECT count(*) FROM match_moves")).scalar_one() == 1


def test_lances_simultaneos_dos_dois_jogadores_respeitam_o_turno(
        client: TestClient, mailer: MemoryMailer, db: Session) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b)["id"]
    barreira = threading.Barrier(2)
    codigos: dict[str, int] = {}

    def jogar(nome: str, c: TestClient, move: str) -> None:
        barreira.wait()
        codigos[nome] = lance(c, mid, move, 0).status_code

    threads = [threading.Thread(target=jogar, args=("a", a, "0")),
               threading.Thread(target=jogar, args=("b", b, "4"))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert codigos["a"] == 200 and codigos["b"] in (403, 409)
    assert db.execute(text("SELECT count(*) FROM match_moves")).scalar_one() == 1


def test_limite_de_120_lances_por_minuto(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b)["id"]
    for _ in range(120):
        assert lance(a, mid, "0", 7).status_code == 409
    assert lance(a, mid, "0", 7).status_code == 429


def test_partida_online_termina_com_vitoria_e_nao_aceita_mais_lances(
        client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b)["id"]
    for autor, mv, ply in ((a, "0", 0), (b, "3", 1), (a, "1", 2), (b, "4", 3), (a, "2", 4)):
        assert lance(autor, mid, mv, ply).status_code == 200
    final = a.get(f"{API}/matches/{mid}").json()
    assert final["status"] == "finished" and final["result"] == "p1_win"
    assert final["end_reason"] == "normal" and final["legal_moves"] == []
    assert lance(b, mid, "5", 5).json()["type"] == "match_finished"


def test_lance_antes_de_a_sala_ter_oponente_e_recusado(client: TestClient,
                                                      mailer: MemoryMailer) -> None:
    a, _ = duas_contas(client, mailer)
    sala = criar_convite(a)
    r = lance(a, sala["id"], "0", 0)
    assert r.status_code == 409 and r.json()["type"] == "match_not_started"
    assert post(a, f"/matches/{sala['id']}/resign").status_code == 409


# ---------- desistência, empate por acordo e abandono (RF-015 / CA-015) ----------

def test_desistencia_online_da_a_vitoria_ao_oponente(client: TestClient,
                                                     mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b, seat=1)["id"]
    r = post(b, f"/matches/{mid}/resign")
    assert r.status_code == 200
    assert r.json()["result"] == "p1_win" and r.json()["end_reason"] == "resign"
    assert post(b, f"/matches/{mid}/resign").status_code == 409


def test_empate_por_acordo_oferecer_e_aceitar(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b, "chess")["id"]
    oferta = post(a, f"/matches/{mid}/draw-offer")
    assert oferta.status_code == 200 and oferta.json()["draw_offer_by_seat"] == 1
    assert b.get(f"{API}/matches/{mid}").json()["draw_offer_by_seat"] == 1  # visível ao oponente
    fim = post(b, f"/matches/{mid}/draw-response", {"accept": True})
    assert fim.status_code == 200
    assert fim.json()["result"] == "draw" and fim.json()["end_reason"] == "agreement"
    assert fim.json()["status"] == "finished"


def test_empate_recusado_mantem_a_partida(client: TestClient, mailer: MemoryMailer,
                                          db: Session) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b, "checkers")["id"]
    post(a, f"/matches/{mid}/draw-offer")
    r = post(b, f"/matches/{mid}/draw-response", {"accept": False})
    assert r.status_code == 200 and r.json()["status"] == "in_progress"
    assert r.json()["draw_offer_by_seat"] is None
    assert db.scalar(select(DrawOffer.status)) == "declined"


def test_respostas_de_empate_invalidas(client: TestClient, mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b, "chess")["id"]
    assert post(b, f"/matches/{mid}/draw-response", {"accept": True}).json()["type"] == \
        "no_draw_offer"
    post(a, f"/matches/{mid}/draw-offer")
    assert post(a, f"/matches/{mid}/draw-response", {"accept": True}).status_code == 409  # própria
    assert post(a, f"/matches/{mid}/draw-offer").json()["type"] == "draw_offer_pending"
    assert post(b, f"/matches/{mid}/draw-offer").json()["type"] == "draw_offer_pending"
    assert post(b, f"/matches/{mid}/draw-response", {"accept": "sim"}).status_code == 422


def test_segunda_proposta_em_menos_de_10_lances_e_rejeitada(client: TestClient,
                                                            mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b, "chess")["id"]
    post(a, f"/matches/{mid}/draw-offer")
    post(b, f"/matches/{mid}/draw-response", {"accept": False})
    r = post(a, f"/matches/{mid}/draw-offer")
    assert r.status_code == 429 and r.json()["type"] == "draw_offer_limited"
    # O adversário tem a sua própria cota.
    assert post(b, f"/matches/{mid}/draw-offer").status_code == 200
    post(a, f"/matches/{mid}/draw-response", {"accept": False})
    jogar_aleatorio(a, b, mid, ate_ply=10)
    assert post(a, f"/matches/{mid}/draw-offer").status_code == 200


def test_jogar_recusa_implicitamente_a_proposta_do_oponente(client: TestClient,
                                                            mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b, "chess")["id"]
    post(a, f"/matches/{mid}/draw-offer")
    assert lance(a, mid, "e2e4", 0).status_code == 200  # o próprio autor jogar não cancela
    assert a.get(f"{API}/matches/{mid}").json()["draw_offer_by_seat"] == 1
    assert lance(b, mid, "e7e5", 1).status_code == 200  # quem recebeu jogou: recusou
    assert a.get(f"{API}/matches/{mid}").json()["draw_offer_by_seat"] is None
    assert post(b, f"/matches/{mid}/draw-response", {"accept": True}).status_code == 409


def test_jogo_da_velha_nao_tem_empate_por_acordo(client: TestClient,
                                                 mailer: MemoryMailer) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b)["id"]
    r = post(a, f"/matches/{mid}/draw-offer")
    assert r.status_code == 422 and r.json()["type"] == "draw_not_available"


def test_abandono_so_depois_da_tolerancia_com_o_adversario_na_vez(
        client: TestClient, mailer: MemoryMailer, fake_clock: FakeClock) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b, seat=1)["id"]
    r = post(b, f"/matches/{mid}/claim-abandon")  # é a vez de a, que nunca conectou
    assert r.status_code == 409 and r.json()["type"] == "too_early"
    assert post(a, f"/matches/{mid}/claim-abandon").json()["type"] == "too_early"  # vez própria
    fake_clock.advance(seconds=59)
    assert post(b, f"/matches/{mid}/claim-abandon").status_code == 409
    fake_clock.advance(seconds=2)
    ok = post(b, f"/matches/{mid}/claim-abandon")
    assert ok.status_code == 200
    assert ok.json()["end_reason"] == "abandon" and ok.json()["result"] == "p2_win"


def test_tolerancia_so_conta_no_turno_do_desconectado(client: TestClient, mailer: MemoryMailer,
                                                      fake_clock: FakeClock) -> None:
    a, b = duas_contas(client, mailer)
    mid = partida(a, b, seat=1)["id"]
    fake_clock.advance(seconds=120)  # b esperou tempo demais, mas não era a vez dele
    assert lance(a, mid, "0", 0).status_code == 200
    r = post(a, f"/matches/{mid}/claim-abandon")  # agora é a vez de b: a contagem recomeça
    assert r.status_code == 409 and r.json()["type"] == "too_early"
    fake_clock.advance(seconds=61)
    assert post(a, f"/matches/{mid}/claim-abandon").status_code == 200


def test_nenhuma_acao_online_vale_para_partida_contra_ia(client: TestClient,
                                                         mailer: MemoryMailer) -> None:
    a, _ = duas_contas(client, mailer)
    m = post(a, "/matches", {"game_id": "chess", "mode": "ai", "ai_level": 1}).json()
    for caminho in ("draw-offer", "claim-abandon"):
        assert post(a, f"/matches/{m['id']}/{caminho}").status_code == 422
