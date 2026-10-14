"""RF-019 / CA-019 (T-019): fórmula Elo pura. Os valores esperados foram calculados à mão.

Esperança: E = 1 / (1 + 10^((Ro - R) / 400)). Variação: K * (S - E), arredondada para o inteiro
mais próximo (meio afastando de zero).
"""

import pytest

from app.game_engines import elo
from app.game_engines.elo import (
    DRAW,
    LOSS,
    WIN,
    expected_score,
    k_factor,
    new_rating,
    rating_delta,
)


def test_esperanca_entre_iguais_e_meio() -> None:
    assert expected_score(1200, 1200) == 0.5


def test_esperanca_com_200_pontos_de_diferenca() -> None:
    # 10^(200/400) = 3,16228 -> E = 1 / 4,16228 = 0,240253
    assert expected_score(1200, 1400) == pytest.approx(0.240253, abs=1e-6)
    assert expected_score(1400, 1200) == pytest.approx(0.759747, abs=1e-6)


def test_esperanca_com_400_pontos_de_diferenca() -> None:
    # 10^1 = 10 -> E = 1 / 11 = 0,090909
    assert expected_score(1200, 1600) == pytest.approx(0.090909, abs=1e-6)
    assert expected_score(1600, 1200) == pytest.approx(0.909091, abs=1e-6)


@pytest.mark.parametrize(("a", "b"), [(1200, 1200), (1000, 1731), (2400, 1500), (100, 101)])
def test_esperancas_dos_dois_lados_somam_um(a: int, b: int) -> None:
    assert expected_score(a, b) + expected_score(b, a) == pytest.approx(1.0, abs=1e-12)


def test_k_40_nas_primeiras_30_partidas_e_20_depois() -> None:
    assert [k_factor(n) for n in (0, 1, 29)] == [40, 40, 40]
    assert [k_factor(n) for n in (30, 31, 500)] == [20, 20, 20]


def test_ca_019_vitoria_1200x1200_com_k40_da_mais_20_e_menos_20() -> None:
    assert rating_delta(1200, 1200, WIN, 0) == 20
    assert rating_delta(1200, 1200, LOSS, 0) == -20
    assert new_rating(1200, 1200, WIN, 0) == 1220
    assert new_rating(1200, 1200, LOSS, 0) == 1180


def test_empate_entre_iguais_nao_muda_o_rating() -> None:
    assert rating_delta(1200, 1200, DRAW, 0) == 0
    assert rating_delta(1500, 1500, DRAW, 40) == 0


def test_zebra_do_mais_fraco_k40() -> None:
    # 1200 contra 1400, E = 0,240253: vitória 40*0,759747 = 30,39 -> +30;
    # empate 40*0,259747 = 10,39 -> +10; derrota 40*(-0,240253) = -9,61 -> -10.
    assert rating_delta(1200, 1400, WIN, 0) == 30
    assert rating_delta(1200, 1400, DRAW, 0) == 10
    assert rating_delta(1200, 1400, LOSS, 0) == -10


def test_favorito_k40() -> None:
    # 1400 contra 1200, E = 0,759747: vitória 40*0,240253 = 9,61 -> +10;
    # empate 40*(-0,259747) = -10,39 -> -10; derrota 40*(-0,759747) = -30,39 -> -30.
    assert rating_delta(1400, 1200, WIN, 0) == 10
    assert rating_delta(1400, 1200, DRAW, 0) == -10
    assert rating_delta(1400, 1200, LOSS, 0) == -30


def test_k20_depois_de_30_partidas() -> None:
    # 1500 x 1500: 20 * 0,5 = 10. 1600 x 1200 (E = 0,909091): +20*0,090909 = 1,82 -> +2
    # na vitória e 20*(-0,909091) = -18,18 -> -18 na derrota.
    assert rating_delta(1500, 1500, WIN, 30) == 10
    assert rating_delta(1600, 1200, WIN, 30) == 2
    assert rating_delta(1600, 1200, LOSS, 30) == -18


def test_trinta_partidas_ainda_vale_k40_na_ultima_provisoria() -> None:
    assert rating_delta(1200, 1200, WIN, 29) == 20  # a 30ª partida ainda usa K = 40
    assert rating_delta(1200, 1200, WIN, 30) == 10  # a 31ª já usa K = 20


def test_k_diferente_por_jogador_nao_e_soma_zero() -> None:
    # Novato (29 partidas, K=40) vence veterano (30, K=20), ambos 1200: +20 e -10.
    assert rating_delta(1200, 1200, WIN, 29) == 20
    assert rating_delta(1200, 1200, LOSS, 30) == -10


@pytest.mark.parametrize(("valor", "esperado"), [
    (2.4, 2), (2.5, 3), (2.6, 3), (-2.4, -2), (-2.5, -3), (-2.6, -3), (0.5, 1), (-0.5, -1),
    (0.0, 0),
])
def test_arredondamento_meio_afastando_de_zero(valor: float, esperado: int) -> None:
    assert elo._round_half_away(valor) == esperado  # noqa: SLF001


def test_piso_do_rating() -> None:
    # 100 x 100, derrota K=40: 100 - 20 = 80 -> piso 100.
    assert new_rating(100, 100, LOSS, 0) == elo.RATING_FLOOR
    # 110 x 100: E = 0,514388 -> -20,58 -> -21 -> 89 -> piso 100.
    assert new_rating(110, 100, LOSS, 0) == elo.RATING_FLOOR
    # Acima do piso nada muda: 300 x 300, derrota K=40 = -20.
    assert new_rating(300, 300, LOSS, 0) == 280


@pytest.mark.parametrize(("a", "b"), [(1200, 1200), (1300, 1150), (1000, 1380), (1850, 1200)])
def test_com_o_mesmo_k_a_vitoria_e_soma_zero(a: int, b: int) -> None:
    ganho = rating_delta(a, b, WIN, 0)
    perda = rating_delta(b, a, LOSS, 0)
    assert ganho + perda == 0
