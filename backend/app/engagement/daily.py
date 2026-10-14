"""Escolha determinística do desafio diário (RF-027).

Sem aleatoriedade nem estado: o exercício do dia depende só da data civil (America/Sao_Paulo) e
do jogo, então é o mesmo para todas as pessoas e pode ser recalculado a qualquer momento. O
conteúdo vem da Academy (mesmos exercícios, mesma correção pelo motor).
"""

import hashlib
from datetime import date

from app.academy import content
from app.academy.content import ExerciseRef


def pool(game_id: str) -> list[ExerciseRef]:
    """Exercícios do jogo em ordem estável (por id)."""
    game = content.game_content(game_id)
    if game is None:
        return []
    refs = [ExerciseRef(game, lesson, ex) for lesson in game.lessons for ex in lesson.exercises]
    return sorted(refs, key=lambda r: r.exercise.id)


def pick(game_id: str, day: date) -> ExerciseRef | None:
    refs = pool(game_id)
    if not refs:
        return None
    digest = hashlib.sha256(f"boardhub-daily:{day.isoformat()}:{game_id}".encode()).digest()
    return refs[int.from_bytes(digest[:8], "big") % len(refs)]
