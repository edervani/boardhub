"""Análise pós-partida do Mentor (RF-024, doc 08 §7 e §8, doc 06 §2).

Só participantes (não participante e inexistente respondem igual — SEC-05) e só partidas
finalizadas. O resultado é cacheado por (partida, usuário). A IA generativa, se houver, apenas
reformula o texto e sua saída é verificada; o padrão (`NullProvider`) mantém o modelo de texto.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.academy import content
from app.ai.llm.provider import Facts, accept_rewrite, cited_in, get_provider
from app.ai.mentor import analysis
from app.core.errors import ProblemError
from app.core.ratelimit import limiter
from app.models import Match, MatchAnalysis, MatchMove, MatchPlayer, User
from app.schemas.academy import AnalysisOut, MomentOut

HOUR = 3600.0
CAVEAT = ("Análise simples feita pelo motor do BoardHub: considera material e mates próximos, "
          "não substitui um motor forte nem um professor.")


def _load(db: Session, user: User, match_id: uuid.UUID) -> tuple[Match, list[MatchPlayer]]:
    match = db.scalar(select(Match).where(Match.id == match_id))
    players = list(db.scalars(select(MatchPlayer).where(MatchPlayer.match_id == match_id)))
    if match is None or not any(p.user_id == user.id for p in players):
        raise ProblemError(404, "not_found", "Partida não encontrada")
    return match, players


def _moment_out(game_id: str, m: analysis.Moment) -> MomentOut:
    text = analysis.explain(game_id, m)
    facts = Facts(text, frozenset(cited_in(text)))
    rewritten = accept_rewrite(facts, get_provider().rephrase(facts, "simple"))
    game_content = content.game_content(game_id)
    assert game_content is not None
    lesson = content.lesson_for_concept(game_id, m.concept_key)
    return MomentOut(
        ply=m.ply, move_number=analysis.move_number(game_id, m.ply), severity=m.severity,
        kind=m.kind, played=m.played, played_label=m.played_label, best=m.best,
        best_label=m.best_label, reply=m.reply, reply_label=m.reply_label,
        explanation=rewritten or text,
        explanation_source="llm" if rewritten else "template",
        concept_key=m.concept_key, concept_title=game_content.concept(m.concept_key).title,
        lesson_id=lesson.id if lesson else None, position=m.position)


def get_analysis(db: Session, user: User, match_id: uuid.UUID) -> AnalysisOut:
    match, players = _load(db, user, match_id)
    if match.status != "finished":
        # Partida em andamento (inclusive ranqueada): nenhuma ajuda é exibida (doc 08 §7).
        raise ProblemError(409, "analysis_unavailable", "Análise indisponível",
                           "A análise só existe depois que a partida termina.")
    cached = db.get(MatchAnalysis, (match.id, user.id))
    if cached is not None and cached.engine_version == analysis.ENGINE_VERSION:
        return AnalysisOut.model_validate(cached.result)
    limiter.hit(f"analysis:{user.id}", 10, HOUR)  # doc 06: 10/h
    moves = list(db.scalars(select(MatchMove.move).where(MatchMove.match_id == match.id)
                            .order_by(MatchMove.ply)))
    seats = frozenset(p.seat for p in players if p.user_id == user.id)
    result = analysis.analyze_game(match.game_id, moves, seats)
    out = AnalysisOut(
        match_id=str(match.id), game_id=match.game_id, engine_version=analysis.ENGINE_VERSION,
        analyzed_moves=result.analyzed_moves, user_moves=result.user_moves,
        truncated=result.truncated, counts=result.counts,
        moments=[_moment_out(match.game_id, m) for m in result.moments], caveat=CAVEAT)
    if cached is None:
        db.add(MatchAnalysis(match_id=match.id, user_id=user.id,
                             engine_version=analysis.ENGINE_VERSION,
                             result=out.model_dump(mode="json")))
    else:
        cached.engine_version, cached.result = analysis.ENGINE_VERSION, out.model_dump(mode="json")
    db.commit()
    return out
