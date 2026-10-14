"""RF-017 / CA-017 — motor de damas brasileiras (T-017). Cenários verificados contra o
regulamento (Fenae/CBD) para movimento, captura obrigatória, maioria, dama voadora e promoção."""

import random
from collections.abc import Callable
from typing import Any

import pytest

from app.game_engines.base import IllegalMove, InvalidState
from app.game_engines.checkers import (
    KINGS_ONLY_LIMIT_PLIES,
    CheckersEngine,
    State,
    position_key,
)

E = CheckersEngine()


def pos(w: tuple[int, ...] = (), b: tuple[int, ...] = (), kw: tuple[int, ...] = (),
        kb: tuple[int, ...] = (), to: str = "w", plies: int = 0) -> State:
    """Monta posição pelas casas PDN: w/b pedras, kw/kb damas."""
    sq = ["."] * 32
    for letter, squares in (("w", w), ("b", b), ("W", kw), ("B", kb)):
        for n in squares:
            sq[n - 1] = letter
    board = tuple(sq)
    return State(board, to, plies, (position_key(board, to),))


def moves(s: State) -> set[str]:
    return {str(m) for m in E.legal_moves(s)}


def perft(s: State, depth: int) -> int:
    if depth == 0:
        return 1
    return sum(perft(E.apply(s, m), depth - 1) for m in E.legal_moves(s))


# ---------- posição inicial e perft ----------

def test_posicao_inicial() -> None:
    s = E.initial_state()
    assert s.squares.count("w") == s.squares.count("b") == 12
    assert s.to_move == "w"
    assert moves(s) == {"21-17", "22-17", "22-18", "23-18", "23-19", "24-19", "24-20"}


def test_perft_ate_4_lances_confere_com_valores_conhecidos() -> None:
    """Sem capturas por dama, a árvore inicial coincide com a das damas inglesas até aqui."""
    s = E.initial_state()
    assert [perft(s, d) for d in range(1, 5)] == [7, 49, 302, 1469]


# ---------- movimento ----------

def test_pedra_so_anda_para_frente() -> None:
    assert moves(pos(w=(22,), b=(1,))) == {"22-17", "22-18"}
    assert moves(pos(b=(18,), w=(32,), to="b")) == {"18-22", "18-23"}


def test_dama_voadora_move_qualquer_distancia() -> None:
    s = pos(kw=(30,), b=(1,))
    assert moves(s) == {"30-26", "30-23", "30-19", "30-16", "30-12", "30-25", "30-21"}


# ---------- captura ----------

def test_captura_e_obrigatoria() -> None:
    s = pos(w=(22, 30), b=(18, 2))
    assert moves(s) == {"22x15"}
    with pytest.raises(IllegalMove, match="captura obrigatória"):
        E.apply(s, E.parse_move("30-26"))


def test_pedra_captura_para_tras() -> None:
    assert moves(pos(w=(15,), b=(18, 2))) == {"15x22"}


def test_lei_da_maioria() -> None:
    s = pos(w=(22, 31), b=(18, 11, 27))
    assert moves(s) == {"22x15x8"}
    with pytest.raises(IllegalMove, match="maioria"):
        E.apply(s, E.parse_move("31x24"))


def test_capturas_de_mesma_quantidade_sao_livres() -> None:
    assert moves(pos(w=(22, 31), b=(18, 27, 1))) == {"22x15", "31x24"}


def test_dama_captura_de_longe_e_escolhe_a_casa_de_pouso() -> None:
    assert moves(pos(kw=(30,), b=(23, 1))) == {"30x19", "30x16", "30x12"}


def test_dama_nao_captura_duas_pecas_coladas() -> None:
    assert moves(pos(kw=(30,), b=(23, 19))) == {"30-26", "30-25", "30-21"}


def test_dama_nao_salta_peca_propria() -> None:
    assert moves(pos(kw=(30,), w=(23,), b=(1,))) == {
        "30-26", "30-25", "30-21", "23-18", "23-19"}


def test_dama_e_pedra_valem_igual_na_contagem_da_maioria() -> None:
    # Dama capturando 1 peça vs pedra capturando 1 peça: ambas livres.
    s = pos(kw=(30,), w=(31,), b=(23, 27, 1))
    assert {"30x19", "30x16", "30x12", "31x24"} <= moves(s)


# ---------- promoção ----------

def test_pedra_que_termina_na_ultima_fileira_vira_dama() -> None:
    s = E.apply(pos(w=(8,), b=(30,)), E.parse_move("8-4"))
    assert s.squares[3] == "W"


def test_nao_promove_no_meio_de_uma_captura_que_continua() -> None:
    s = pos(w=(11,), b=(7, 6, 32))
    assert moves(s) == {"11x2x9"}
    after = E.apply(s, E.parse_move("11x2x9"))
    assert after.squares[8] == "w"  # continuou como pedra
    assert after.squares[1] == "." and after.squares[6] == "." and after.squares[5] == "."


def test_captura_que_termina_na_ultima_fileira_promove() -> None:
    after = E.apply(pos(w=(11,), b=(7, 32)), E.parse_move("11x2"))
    assert after.squares[1] == "W"


# ---------- fim de jogo e empates ----------

def test_sem_pecas_ou_sem_lances_perde() -> None:
    sem_pecas = pos(w=(22,), to="b")
    out_sem_pecas = E.outcome(sem_pecas)
    assert out_sem_pecas is not None and out_sem_pecas.winner == "w"
    bloqueado = pos(w=(29, 30), b=(25,), to="b")
    out = E.outcome(bloqueado)
    assert out is not None and (out.winner, out.reason) == ("w", "no_moves")
    assert E.legal_moves(bloqueado) == []


def test_empate_por_20_lances_de_cada_lado_so_com_damas() -> None:
    s = pos(kw=(30,), kb=(3,), plies=KINGS_ONLY_LIMIT_PLIES - 1)
    assert E.outcome(s) is None
    out = E.outcome(E.apply(s, E.parse_move("30-26")))
    assert out is not None and (out.winner, out.reason) == (None, "kings_only")


def test_captura_e_lance_de_pedra_zeram_o_contador() -> None:
    s = pos(kw=(30,), kb=(3,), w=(22,), plies=30)
    assert E.apply(s, E.parse_move("22-18")).kings_only_plies == 0
    assert E.apply(s, E.parse_move("30-26")).kings_only_plies == 31


def test_repeticao_tripla_empata() -> None:
    s = pos(kw=(30,), kb=(3,))
    ciclo = ["30-25", "3-7", "25-30", "7-3"]
    for volta in range(2):
        for i, m in enumerate(ciclo):
            assert E.outcome(s) is None, (volta, i)
            s = E.apply(s, E.parse_move(m))
    out = E.outcome(s)
    assert out is not None and (out.winner, out.reason) == (None, "repetition")
    assert E.legal_moves(s) == []


# ---------- serialização e notação ----------

def test_ida_e_volta_da_serializacao() -> None:
    s = E.apply(E.initial_state(), E.parse_move("22-18"))
    assert E.deserialize(E.serialize(s)) == s


def _good() -> dict[str, Any]:
    return E.serialize(E.initial_state())


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(schema_version=2),
    lambda d: d.update(squares=d["squares"][:31]),
    lambda d: d.update(squares=["x"] * 32),
    lambda d: d.update(to_move="x"),
    lambda d: d.update(halfmove_kings_only=41),
    lambda d: d.update(halfmove_kings_only=True),
    lambda d: d.update(halfmove_kings_only="0"),
    lambda d: d.update(position_history=[]),
    lambda d: d.update(position_history=["0" * 16]),  # não confere com a posição
    lambda d: d.update(position_history=["zz"]),
    lambda d: d.update(squares=["w"] * 32),  # peças demais
    lambda d: d.pop("squares"),
])
def test_estado_invalido_e_recusado(mutate: Callable[[dict[str, Any]], object]) -> None:
    data = _good()
    mutate(data)
    with pytest.raises(InvalidState):
        E.deserialize(data)


def test_pedra_na_fileira_de_promocao_e_estado_invalido() -> None:
    s = pos(w=(2,), b=(30,))
    with pytest.raises(InvalidState):
        E.deserialize(E.serialize(s))


@pytest.mark.parametrize(("raw", "path", "capture"), [
    ("11-15", (11, 15), False), ("15x24x31", (15, 24, 31), True), ("1x10", (1, 10), True),
])
def test_parse_move_valido(raw: str, path: tuple[int, ...], capture: bool) -> None:
    m = E.parse_move(raw)
    assert (m.path, m.capture, str(m)) == (path, capture, raw)


@pytest.mark.parametrize("raw", ["", "11", "11-", "11x", "0-5", "33-1", "11-15-19", "a-b",
                                 "11x15-19", "11-15x19", " 11-15", "11-15\n", "٣-٤"])
def test_parse_move_invalido(raw: str) -> None:
    with pytest.raises(IllegalMove):
        E.parse_move(raw)


def test_lance_ilegal_e_recusado_sem_alterar_o_estado() -> None:
    s = E.initial_state()
    for raw in ("1-5", "22-26", "17-13", "21-18"):
        with pytest.raises(IllegalMove):
            E.apply(s, E.parse_move(raw))
    assert s == E.initial_state()


# ---------- propriedades em partidas aleatórias ----------

def test_invariantes_em_partidas_aleatorias() -> None:
    rng = random.Random(2026)
    finais = set()
    for _ in range(150):
        s = E.initial_state()
        for _ply in range(600):
            legal = E.legal_moves(s)
            if not legal:
                break
            caps = [m for m in legal if m.capture]
            if caps:  # captura obrigatória + maioria
                assert len(caps) == len(legal)
                assert len({len(m.captured) for m in legal}) == 1
            for m in legal:
                assert len(set(m.captured)) == len(m.captured)
                assert E.parse_move(str(m)) == m
            m = rng.choice(legal)
            s = E.apply(s, m)
            assert E.deserialize(E.serialize(s)) == s
            for color in "wb":
                assert sum(1 for p in s.squares if p.lower() == color) <= 12
            assert not any(p == "w" and i < 4 or p == "b" and i >= 28
                           for i, p in enumerate(s.squares))
        out = E.outcome(s)
        assert out is not None  # toda partida termina
        finais.add(out.reason)
    assert "no_moves" in finais
