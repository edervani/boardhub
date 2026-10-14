"""Contratos da Academy e da análise pós-partida (doc 06 §2)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.auth import Strict

Declared = Literal["never", "knows_rules", "regular", "competitive"]


class ConceptStatusOut(BaseModel):
    game_id: str
    concept_key: str
    title: str
    mastery: float
    status: str  # not_started | in_practice | mastered | in_review
    review_due: bool
    next_review_at: datetime | None


class ProgressOut(BaseModel):
    concepts: list[ConceptStatusOut]


class TrackOut(BaseModel):
    game_id: str
    game_name: str
    title: str
    description: str
    lessons_count: int
    exercises_count: int
    concepts_total: int
    concepts_mastered: int


class ExerciseStubOut(BaseModel):
    id: str
    type: str
    difficulty: int
    solved: bool


class LessonOut(BaseModel):
    id: str
    concept_key: str
    concept_title: str
    title: str
    summary: str
    body: list[str]
    completed: bool
    exercises: list[ExerciseStubOut]


class ConceptOut(BaseModel):
    key: str
    title: str
    summary: str
    prerequisites: list[str]
    mastery: float
    status: str
    review_due: bool


class LessonsOut(BaseModel):
    game_id: str
    content_version: str
    title: str
    description: str
    concepts: list[ConceptOut]
    lessons: list[LessonOut]


class OptionOut(BaseModel):
    id: str
    text: str


class ExerciseOut(BaseModel):
    """Exercício sem a solução: não há `accepted`, `correct_option` nem explicação."""

    id: str
    game_id: str
    lesson_id: str
    concept_key: str
    concept_title: str
    type: Literal["best_move", "rule_quiz"]
    difficulty: int
    prompt: str
    position: dict[str, Any] | None
    legal_moves: list[str]
    options: list[OptionOut]
    hints_used: int
    hints_available: int = 3


class HintIn(Strict):
    level: int = Field(ge=1, le=3)


class HintOut(BaseModel):
    level: int
    text: str
    hints_used: int


class AttemptIn(Strict):
    answer: str = Field(min_length=1, max_length=64)
    duration_ms: int | None = Field(default=None, ge=0, le=3_600_000)


class AttemptOut(BaseModel):
    correct: bool
    feedback: str
    explanation: str | None
    hint_level: int
    concept_key: str
    mastery: float
    status: str
    mastered_now: bool
    next_review_at: datetime | None


class PlacementAnswer(Strict):
    exercise_id: str = Field(min_length=1, max_length=40)
    answer: str = Field(min_length=1, max_length=64)


class PlacementIn(Strict):
    declared: Declared
    answers: list[PlacementAnswer] = Field(default_factory=list, max_length=10)


class PlacementConceptOut(BaseModel):
    concept_key: str
    title: str
    mastery: float


class PlacementResultOut(BaseModel):
    suggested_ai_level: int
    concepts: list[PlacementConceptOut]


class PlacementOut(BaseModel):
    done: bool
    answered: int
    total: int
    next_exercise: ExerciseOut | None
    result: PlacementResultOut | None


# ------------------------------------------------------------- análise pós-partida

class MomentOut(BaseModel):
    ply: int
    move_number: int
    severity: str  # inaccuracy | mistake | blunder
    kind: str
    played: str
    played_label: str
    best: str
    best_label: str
    reply: str | None
    reply_label: str | None
    explanation: str
    explanation_source: Literal["template", "llm"]
    concept_key: str
    concept_title: str
    lesson_id: str | None
    position: dict[str, Any]


class AnalysisOut(BaseModel):
    match_id: str
    game_id: str
    engine_version: str
    analyzed_moves: int
    user_moves: int
    truncated: bool
    counts: dict[str, int]
    moments: list[MomentOut]
    caveat: str
