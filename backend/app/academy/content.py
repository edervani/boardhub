"""Conteúdo da Academy: trilhas, lições e exercícios como dados versionados (doc 08, DT-017).

Os arquivos JSON em `content/` são a fonte do conteúdo e passam por revisão humana (P-08). Aqui
só se carrega e valida a estrutura; a correção das respostas é sempre calculada pelo motor
(`grading.py`) e conferida pelos testes. Nada aqui chama rede.
"""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CONTENT_DIR = Path(__file__).parent / "content"
GAMES = ("tictactoe", "checkers", "chess")
Goal = Literal["win_now", "block_loss", "optimal", "promote", "give_check", "free_capture",
               "listed"]
BOARD_GOALS: dict[str, tuple[str, ...]] = {
    "tictactoe": ("win_now", "block_loss", "optimal"),
    "checkers": ("win_now", "block_loss", "optimal", "promote", "listed"),
    "chess": ("win_now", "block_loss", "give_check", "free_capture", "listed", "optimal"),
}


class ContentError(Exception):
    """Conteúdo inválido. O carregamento falha alto em vez de servir lição quebrada."""


class Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Concept(Frozen):
    key: str = Field(pattern=r"^[a-z]{2}\.[a-z_]+$")
    title: str
    summary: str
    prerequisites: list[str]


class Option(Frozen):
    id: str = Field(pattern=r"^[a-z]$")
    text: str


class Exercise(Frozen):
    id: str = Field(pattern=r"^[a-z]{2}-[a-z0-9-]+$")
    type: Literal["best_move", "rule_quiz"]
    difficulty: int = Field(ge=1, le=3)
    prompt: str
    explanation: str
    goal: Goal | None = None
    # Só para o objetivo `listed`: "best" = os lances aceitos são os melhores segundo o motor
    # (conferido por teste); "legal" = exercício de execução (basta o lance ser legal e pedido).
    verify: Literal["best", "legal"] | None = None
    position: dict[str, str] | None = None
    accepted: list[str] = Field(default_factory=list)
    options: list[Option] = Field(default_factory=list)
    correct_option: str | None = None

    @model_validator(mode="after")
    def _coherent(self) -> "Exercise":
        if self.type == "rule_quiz":
            ids = [o.id for o in self.options]
            if len(ids) < 2 or len(set(ids)) != len(ids) or self.correct_option not in ids:
                raise ValueError(f"{self.id}: alternativas inválidas")
            if self.goal or self.position or self.accepted:
                raise ValueError(f"{self.id}: quiz não tem objetivo, posição nem lances")
        else:
            if self.goal is None or self.position is None or self.options or self.correct_option:
                raise ValueError(f"{self.id}: exercício de lance exige objetivo e posição")
            if (self.goal == "listed") != bool(self.accepted):
                raise ValueError(f"{self.id}: só o objetivo 'listed' tem lances aceitos")
            if (self.goal == "listed") != (self.verify is not None):
                raise ValueError(f"{self.id}: 'verify' é obrigatório (e só vale) em 'listed'")
        return self


class Lesson(Frozen):
    id: str = Field(pattern=r"^[a-z]{2}-l[0-9]+$")
    concept: str
    title: str
    summary: str
    body: list[str]
    exercises: list[Exercise]


class Track(Frozen):
    title: str
    description: str


class GameContent(Frozen):
    content_version: str
    game_id: str
    track: Track
    concepts: list[Concept]
    lessons: list[Lesson]

    def concept(self, key: str) -> Concept:
        return next(c for c in self.concepts if c.key == key)


@dataclass(frozen=True)
class ExerciseRef:
    content: GameContent
    lesson: Lesson
    exercise: Exercise

    @property
    def concept_key(self) -> str:
        return self.lesson.concept


def _validate(content: GameContent) -> None:
    keys = [c.key for c in content.concepts]
    if len(set(keys)) != len(keys):
        raise ContentError(f"{content.game_id}: conceitos duplicados")
    prefix = {"tictactoe": "tt.", "checkers": "ck.", "chess": "ch."}[content.game_id]
    for c in content.concepts:
        if not c.key.startswith(prefix):
            raise ContentError(f"{c.key}: prefixo inesperado para {content.game_id}")
        if any(p not in keys for p in c.prerequisites):
            raise ContentError(f"{c.key}: pré-requisito inexistente")
    lesson_ids = [lesson.id for lesson in content.lessons]
    if len(set(lesson_ids)) != len(lesson_ids):
        raise ContentError(f"{content.game_id}: lições duplicadas")
    for lesson in content.lessons:
        if lesson.concept not in keys:
            raise ContentError(f"{lesson.id}: conceito inexistente")
        for ex in lesson.exercises:
            if ex.type == "best_move" and ex.goal not in BOARD_GOALS[content.game_id]:
                raise ContentError(f"{ex.id}: objetivo {ex.goal} inválido em {content.game_id}")


def _load_file(path: Path) -> GameContent:
    try:
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        content = GameContent.model_validate(raw)
    except (OSError, ValueError) as exc:
        raise ContentError(f"{path.name}: {exc}") from exc
    if content.game_id not in GAMES or path.stem != content.game_id:
        raise ContentError(f"{path.name}: game_id inesperado")
    _validate(content)
    return content


@cache
def load_all() -> dict[str, GameContent]:
    """Carrega e valida todo o conteúdo uma única vez por processo."""
    contents = {g: _load_file(CONTENT_DIR / f"{g}.json") for g in GAMES}
    seen: set[str] = set()
    for content in contents.values():
        for lesson in content.lessons:
            for ex in lesson.exercises:
                if ex.id in seen:
                    raise ContentError(f"exercício duplicado: {ex.id}")
                seen.add(ex.id)
    return contents


def game_content(game_id: str) -> GameContent | None:
    return load_all().get(game_id)


@cache
def exercise_index() -> dict[str, ExerciseRef]:
    return {ex.id: ExerciseRef(content, lesson, ex)
            for content in load_all().values()
            for lesson in content.lessons
            for ex in lesson.exercises}


def find_exercise(exercise_id: str) -> ExerciseRef | None:
    return exercise_index().get(exercise_id)


def lesson_for_concept(game_id: str, concept_key: str) -> Lesson | None:
    content = game_content(game_id)
    if content is None:
        return None
    return next((lesson for lesson in content.lessons if lesson.concept == concept_key), None)


def concept_exercises(game_id: str, concept_key: str) -> list[Exercise]:
    content = game_content(game_id)
    if content is None:
        return []
    return [ex for lesson in content.lessons if lesson.concept == concept_key
            for ex in lesson.exercises]
