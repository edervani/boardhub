"""Avaliação inicial adaptativa e sem estado no servidor (RF-022, doc 08 §4).

O servidor refaz a sequência a cada chamada a partir do que o cliente já respondeu: o cliente
não escolhe os exercícios, só envia as respostas na ordem em que foram apresentadas. A idade
nunca entra no cálculo.
"""

from dataclasses import dataclass
from typing import Literal

from app.academy.content import Exercise, GameContent

Declared = Literal["never", "knows_rules", "regular", "competitive"]
START_DIFFICULTY: dict[str, int] = {"never": 1, "knows_rules": 2, "regular": 2, "competitive": 3}
LENGTH = 6
MAX_MASTERY = 0.5  # domínio só se comprova na prática
AI_LEVEL_BY_CORRECT = {0: 1, 1: 1, 2: 2, 3: 2, 4: 3, 5: 4, 6: 4}
REDO_AFTER_DAYS = 30


@dataclass(frozen=True)
class Step:
    exercise: Exercise
    concept_key: str
    correct: bool


def pool(content: GameContent) -> list[tuple[Exercise, str]]:
    return [(ex, lesson.concept) for lesson in content.lessons for ex in lesson.exercises]


def target_difficulty(declared: str, correct_flags: list[bool]) -> int:
    level = START_DIFFICULTY[declared]
    for ok in correct_flags:
        level = min(3, level + 1) if ok else max(1, level - 1)
    return level


def pick_next(content: GameContent, declared: str,
              answered: list[Step]) -> tuple[Exercise, str] | None:
    """Próximo exercício, ou `None` quando a avaliação terminou."""
    if len(answered) >= min(LENGTH, len(pool(content))):
        return None
    target = target_difficulty(declared, [s.correct for s in answered])
    seen = {s.exercise.id for s in answered}
    candidates = [(abs(ex.difficulty - target), i, ex, concept)
                  for i, (ex, concept) in enumerate(pool(content)) if ex.id not in seen]
    if not candidates:
        return None
    _, _, ex, concept = min(candidates, key=lambda c: (c[0], c[1]))
    return ex, concept


def concept_mastery(steps: list[Step]) -> dict[str, float]:
    """Domínio inicial por conceito testado: no máximo 0,5, proporcional aos acertos."""
    totals: dict[str, list[int]] = {}
    for s in steps:
        entry = totals.setdefault(s.concept_key, [0, 0])
        entry[0] += int(s.correct)
        entry[1] += 1
    return {k: round(MAX_MASTERY * c / n, 3) for k, (c, n) in totals.items()}


def suggested_ai_level(steps: list[Step]) -> int:
    return AI_LEVEL_BY_CORRECT[sum(1 for s in steps if s.correct)]
