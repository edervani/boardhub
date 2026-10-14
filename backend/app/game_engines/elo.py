"""Fórmula Elo pura (RF-019, DT-008, DT-019): sem banco, sem relógio, sem aleatoriedade.

Rating inicial 1200; K = 40 nas primeiras 30 partidas ranqueadas do jogador e 20 depois.
O ajuste de cada jogador usa o próprio K, por isso a soma das variações só é zero quando os
dois estão na mesma faixa de K. O arredondamento é "meio afastando de zero" e o rating
nunca cai abaixo de `RATING_FLOOR`.
"""

import math

INITIAL_RATING = 1200
K_PROVISIONAL = 40
K_ESTABLISHED = 20
PROVISIONAL_GAMES = 30
RATING_FLOOR = 100

WIN = 1.0
DRAW = 0.5
LOSS = 0.0


def expected_score(rating: int, opponent_rating: int) -> float:
    """Pontuação esperada de `rating` contra `opponent_rating` (0 a 1)."""
    return 1.0 / (1.0 + math.pow(10.0, (opponent_rating - rating) / 400.0))


def k_factor(games_played: int) -> int:
    """`games_played` = partidas ranqueadas já concluídas antes desta (a 30ª ainda usa K=40)."""
    return K_PROVISIONAL if games_played < PROVISIONAL_GAMES else K_ESTABLISHED


def _round_half_away(value: float) -> int:
    return int(math.copysign(math.floor(abs(value) + 0.5), value))


def rating_delta(rating: int, opponent_rating: int, score: float, games_played: int) -> int:
    """Variação inteira do rating (antes de aplicar o piso)."""
    gap = score - expected_score(rating, opponent_rating)
    return _round_half_away(k_factor(games_played) * gap)


def new_rating(rating: int, opponent_rating: int, score: float, games_played: int) -> int:
    return max(RATING_FLOOR, rating + rating_delta(rating, opponent_rating, score, games_played))
