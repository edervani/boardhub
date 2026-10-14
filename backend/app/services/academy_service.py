"""Casos de uso da Academy: trilhas, exercícios, dicas, tentativas, domínio e avaliação inicial.

O servidor é a autoridade (AGENTS §5): a correção vem do motor, as dicas usadas são registradas
aqui e a pontuação nunca vem do cliente (doc 08). Nenhuma chamada de rede.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.academy import content, grading, mastery, placement
from app.academy.content import ExerciseRef, GameContent
from app.academy.mastery import Evidence, Progress
from app.academy.placement import Step
from app.ai.mentor.notation import describe_position
from app.core import clock
from app.core.errors import ProblemError
from app.core.ratelimit import limiter
from app.models import (
    ExerciseAttempt,
    ExerciseHint,
    Game,
    PlacementResult,
    SkillProgress,
    User,
)
from app.models.base import new_id
from app.schemas.academy import (
    AttemptOut,
    ConceptOut,
    ConceptStatusOut,
    Declared,
    ExerciseOut,
    ExerciseStubOut,
    HintOut,
    LessonOut,
    LessonsOut,
    OptionOut,
    PlacementConceptOut,
    PlacementOut,
    PlacementResultOut,
    ProgressOut,
    TrackOut,
)
from app.services import catalog_service, usage_service

DAY = 86400.0


def _not_found(what: str = "Conteúdo") -> ProblemError:
    return ProblemError(404, "not_found", f"{what} não encontrado")


def _visible_game(db: Session, user: User, game_id: str) -> tuple[Game, GameContent]:
    games = {g.id: g for g in catalog_service.visible_games(db, user.age_band)}
    game, game_content = games.get(game_id), content.game_content(game_id)
    if game is None or game_content is None:
        raise _not_found("Jogo")
    return game, game_content


def _visible_exercise(db: Session, user: User, exercise_id: str) -> ExerciseRef:
    ref = content.find_exercise(exercise_id)
    if ref is None:
        raise _not_found("Exercício")
    _visible_game(db, user, ref.content.game_id)  # respeita a classificação indicativa
    return ref


# ------------------------------------------------------------------ progresso

def _progress_of(row: SkillProgress | None) -> Progress:
    if row is None:
        return Progress()
    return Progress(row.mastery, row.status, row.review_stage, row.next_review_at,
                    row.mastered_at)


def _rows(db: Session, user: User, game_id: str | None = None) -> dict[tuple[str, str], Progress]:
    stmt = select(SkillProgress).where(SkillProgress.user_id == user.id)
    if game_id is not None:
        stmt = stmt.where(SkillProgress.game_id == game_id)
    return {(r.game_id, r.concept_key): _progress_of(r) for r in db.scalars(stmt)}


def _status_out(game_id: str, concept: content.Concept, progress: Progress,
                now: datetime) -> ConceptStatusOut:
    return ConceptStatusOut(
        game_id=game_id, concept_key=concept.key, title=concept.title,
        mastery=progress.mastery, status=progress.status,
        review_due=mastery.review_due(progress, now), next_review_at=progress.next_review_at)


def get_progress(db: Session, user: User, game_id: str | None) -> ProgressOut:
    rows = _rows(db, user, game_id)
    now = clock.now()
    visible = {g.id for g in catalog_service.visible_games(db, user.age_band)}
    out: list[ConceptStatusOut] = []
    for gid, game_content in content.load_all().items():
        if gid not in visible or (game_id is not None and gid != game_id):
            continue
        out.extend(_status_out(gid, c, rows.get((gid, c.key), Progress()), now)
                   for c in game_content.concepts)
    return ProgressOut(concepts=out)


def _solved_ids(db: Session, user: User, game_id: str) -> set[str]:
    return set(db.scalars(select(ExerciseAttempt.exercise_id).where(
        ExerciseAttempt.user_id == user.id, ExerciseAttempt.game_id == game_id,
        ExerciseAttempt.correct.is_(True)).distinct()))


def list_tracks(db: Session, user: User) -> list[TrackOut]:
    rows = _rows(db, user)
    tracks = []
    for game in catalog_service.visible_games(db, user.age_band):
        game_content = content.game_content(game.id)
        if game_content is None:
            continue
        tracks.append(TrackOut(
            game_id=game.id, game_name=game.name, title=game_content.track.title,
            description=game_content.track.description,
            lessons_count=len(game_content.lessons),
            exercises_count=sum(len(lesson.exercises) for lesson in game_content.lessons),
            concepts_total=len(game_content.concepts),
            concepts_mastered=sum(
                1 for c in game_content.concepts
                if rows.get((game.id, c.key), Progress()).status == mastery.MASTERED)))
    return tracks


def get_lessons(db: Session, user: User, game_id: str) -> LessonsOut:
    _, game_content = _visible_game(db, user, game_id)
    rows, solved, now = _rows(db, user, game_id), _solved_ids(db, user, game_id), clock.now()
    concepts = []
    for c in game_content.concepts:
        p = rows.get((game_id, c.key), Progress())
        concepts.append(ConceptOut(key=c.key, title=c.title, summary=c.summary,
                                   prerequisites=c.prerequisites, mastery=p.mastery,
                                   status=p.status, review_due=mastery.review_due(p, now)))
    lessons = [LessonOut(
        id=lesson.id, concept_key=lesson.concept,
        concept_title=game_content.concept(lesson.concept).title, title=lesson.title,
        summary=lesson.summary, body=lesson.body,
        completed=all(ex.id in solved for ex in lesson.exercises),
        exercises=[ExerciseStubOut(id=ex.id, type=ex.type, difficulty=ex.difficulty,
                                   solved=ex.id in solved) for ex in lesson.exercises])
        for lesson in game_content.lessons]
    return LessonsOut(game_id=game_id, content_version=game_content.content_version,
                      title=game_content.track.title, description=game_content.track.description,
                      concepts=concepts, lessons=lessons)


# ------------------------------------------------------------------ exercícios

def _exercise_out(ref: ExerciseRef, hints_used: int) -> ExerciseOut:
    ex, game_id = ref.exercise, ref.content.game_id
    position, legal = None, []
    if ex.type == "best_move":
        position = describe_position(game_id, grading.exercise_state(ref))
        legal = grading.legal_moves(ref)
    return ExerciseOut(
        id=ex.id, game_id=game_id, lesson_id=ref.lesson.id, concept_key=ref.concept_key,
        concept_title=ref.content.concept(ref.concept_key).title, type=ex.type,
        difficulty=ex.difficulty, prompt=ex.prompt, position=position, legal_moves=legal,
        options=[OptionOut(id=o.id, text=o.text) for o in ex.options], hints_used=hints_used)


def _hint_row(db: Session, user: User, exercise_id: str, lock: bool = False) -> ExerciseHint | None:
    stmt = select(ExerciseHint).where(ExerciseHint.user_id == user.id,
                                      ExerciseHint.exercise_id == exercise_id)
    return db.scalar(stmt.with_for_update() if lock else stmt)


def get_exercise(db: Session, user: User, exercise_id: str) -> ExerciseOut:
    ref = _visible_exercise(db, user, exercise_id)
    row = _hint_row(db, user, exercise_id)
    return _exercise_out(ref, row.level if row else 0)


def reveal_hint(db: Session, user: User, exercise_id: str, level: int) -> HintOut:
    limiter.hit(f"academy-hint:{user.id}", 60, 60)
    ref = _visible_exercise(db, user, exercise_id)
    row = _hint_row(db, user, exercise_id, lock=True)
    used = row.level if row else 0
    if level > used + 1:
        raise ProblemError(422, "hint_out_of_order", "Peça as dicas em ordem",
                           f"A próxima dica disponível é a de nível {used + 1}.")
    if level > used:
        if row is None:
            db.add(ExerciseHint(user_id=user.id, exercise_id=exercise_id, level=level))
        else:
            row.level = level
        used = level
    usage_service.touch(db, user)
    db.commit()
    return HintOut(level=level, text=grading.hint_text(ref, level), hints_used=used)


def _evidence(db: Session, user: User, game_id: str, concept_key: str) -> Evidence:
    rows = db.execute(select(ExerciseAttempt.exercise_id, ExerciseAttempt.created_at).where(
        ExerciseAttempt.user_id == user.id, ExerciseAttempt.game_id == game_id,
        ExerciseAttempt.concept_key == concept_key, ExerciseAttempt.correct.is_(True))).all()
    return Evidence(len(rows), len({r.exercise_id for r in rows}),
                    len({r.created_at.astimezone(UTC).date() for r in rows}))


def _locked_progress(db: Session, user: User, game_id: str, concept_key: str) -> SkillProgress:
    stmt = select(SkillProgress).where(
        SkillProgress.user_id == user.id, SkillProgress.game_id == game_id,
        SkillProgress.concept_key == concept_key).with_for_update()
    row = db.scalar(stmt)
    if row is not None:
        return row
    try:
        with db.begin_nested():
            db.add(SkillProgress(user_id=user.id, game_id=game_id, concept_key=concept_key,
                                 mastery=0.0, status=mastery.NOT_STARTED, review_stage=0,
                                 updated_at=clock.now()))
    except IntegrityError:  # outra requisição criou a linha ao mesmo tempo
        pass
    return db.scalars(stmt).one()


def _store(row: SkillProgress, progress: Progress, now: datetime) -> None:
    row.mastery, row.status = progress.mastery, progress.status
    row.review_stage, row.next_review_at = progress.review_stage, progress.next_review_at
    row.mastered_at, row.updated_at = progress.mastered_at, now


def submit_attempt(db: Session, user: User, exercise_id: str, answer: str,
                   duration_ms: int | None) -> AttemptOut:
    limiter.hit(f"academy-attempt:{user.id}", 60, 60)  # doc 06: 60/min
    ref = _visible_exercise(db, user, exercise_id)
    try:
        graded = grading.grade(ref, answer)
    except grading.InvalidAnswerError as exc:
        raise ProblemError(422, "invalid_answer", "Resposta inválida", str(exc)) from exc
    game_id, concept_key = ref.content.game_id, ref.concept_key
    now = clock.now()
    hint_row = _hint_row(db, user, exercise_id, lock=True)
    hint_level = hint_row.level if hint_row else 0
    db.add(ExerciseAttempt(
        id=new_id(), user_id=user.id, game_id=game_id, exercise_id=exercise_id,
        concept_key=concept_key, content_version=ref.content.content_version, answer=answer,
        correct=graded.correct, hint_level=hint_level, duration_ms=duration_ms, created_at=now))
    db.flush()
    row = _locked_progress(db, user, game_id, concept_key)
    before = _progress_of(row)
    after = mastery.apply_attempt(before, correct=graded.correct, hint_level=hint_level,
                                  evidence=_evidence(db, user, game_id, concept_key), now=now)
    _store(row, after, now)
    if graded.correct and hint_row is not None:
        db.delete(hint_row)  # as dicas valem para a tentativa que as usou
    usage_service.touch(db, user, now)  # RF-034: o tempo na Academy também conta
    db.commit()
    return AttemptOut(
        correct=graded.correct, feedback=graded.feedback,
        explanation=ref.exercise.explanation if graded.correct else None,
        hint_level=hint_level, concept_key=concept_key, mastery=after.mastery,
        status=after.status,
        mastered_now=before.status != mastery.MASTERED and after.status == mastery.MASTERED,
        next_review_at=after.next_review_at)


# --------------------------------------------------------------- avaliação inicial

def placement_step(db: Session, user: User, game_id: str, declared: Declared,
                   answers: list[tuple[str, str]]) -> PlacementOut:
    """Uma chamada da avaliação: devolve o próximo exercício ou, ao fim, o resultado (RF-022)."""
    limiter.hit(f"academy-placement-step:{user.id}", 60, 60)
    _, game_content = _visible_game(db, user, game_id)
    now = clock.now()
    previous = db.get(PlacementResult, (user.id, game_id))
    if previous is not None and (now - previous.completed_at).total_seconds() < (
            placement.REDO_AFTER_DAYS * DAY):
        raise ProblemError(409, "placement_too_soon", "Avaliação já feita recentemente",
                           f"Você pode refazê-la {placement.REDO_AFTER_DAYS} dias depois da "
                           "última. Enquanto isso, escolha qualquer lição livremente.")
    total = min(placement.LENGTH, len(placement.pool(game_content)))
    steps: list[Step] = []
    for exercise_id, answer in answers:
        nxt = placement.pick_next(game_content, declared, steps)
        if nxt is None or nxt[0].id != exercise_id:
            raise ProblemError(422, "invalid_placement", "Sequência de respostas inválida")
        ex, concept_key = nxt
        ref = content.find_exercise(ex.id)
        assert ref is not None
        try:
            graded = grading.grade(ref, answer)
        except grading.InvalidAnswerError as exc:
            raise ProblemError(422, "invalid_answer", "Resposta inválida", str(exc)) from exc
        steps.append(Step(ex, concept_key, graded.correct))
    nxt = placement.pick_next(game_content, declared, steps)
    if nxt is not None:
        ref = content.find_exercise(nxt[0].id)
        assert ref is not None
        usage_service.touch(db, user, now)
        db.commit()
        return PlacementOut(done=False, answered=len(steps), total=total,
                            next_exercise=_exercise_out(ref, 0), result=None)
    limiter.hit(f"academy-placement:{user.id}:{game_id}", 5, DAY)  # doc 06: 5/dia
    initial = placement.concept_mastery(steps)
    level = placement.suggested_ai_level(steps)
    _save_placement(db, user, game_id, declared, initial, level, now)
    usage_service.touch(db, user, now)
    db.commit()
    return PlacementOut(
        done=True, answered=len(steps), total=total, next_exercise=None,
        result=PlacementResultOut(suggested_ai_level=level, concepts=[
            PlacementConceptOut(concept_key=k, title=game_content.concept(k).title, mastery=v)
            for k, v in initial.items()]))


def _save_placement(db: Session, user: User, game_id: str, declared: str,
                    initial: dict[str, float], level: int, now: datetime) -> None:
    previous = db.get(PlacementResult, (user.id, game_id))
    if previous is None:
        db.add(PlacementResult(user_id=user.id, game_id=game_id, declared=declared,
                               suggested_ai_level=level, completed_at=now))
    else:
        previous.declared, previous.suggested_ai_level = declared, level
        previous.completed_at = now
    for concept_key, value in initial.items():
        if value <= 0:
            continue
        row = _locked_progress(db, user, game_id, concept_key)
        if row.status in (mastery.NOT_STARTED, mastery.IN_PRACTICE) and value > row.mastery:
            row.mastery = value  # nunca reduz nem concede domínio (máx. 0,5)
            row.status = mastery.IN_PRACTICE
            row.updated_at = now

