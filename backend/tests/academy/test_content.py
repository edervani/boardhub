"""RF-023 / CA-023 / T-023: todo exercício do conteúdo tem a solução confirmada pelo motor.

Estes testes não usam banco: rodam com `pytest --noconftest tests/academy`.
"""

import pytest

from app.academy import content, grading, placement
from app.academy.content import ExerciseRef
from app.ai.mentor import evaluation
from app.game_engines.checkers import _captures, generate

ALL_BOARD = [ref for ref in content.exercise_index().values() if ref.exercise.type == "best_move"]
ALL_QUIZ = [ref for ref in content.exercise_index().values() if ref.exercise.type == "rule_quiz"]


def ids(refs: list[ExerciseRef]) -> list[str]:
    return [r.exercise.id for r in refs]


def test_conteudo_carrega_e_cobre_os_tres_jogos() -> None:
    assert set(content.load_all()) == {"tictactoe", "checkers", "chess"}
    for game in content.load_all().values():
        assert game.content_version
        assert len(game.lessons) >= 4
        for lesson in game.lessons:
            assert lesson.body and lesson.exercises


def test_cada_conceito_tem_ao_menos_tres_exercicios_para_poder_ser_dominado() -> None:
    """Domínio exige acertos em >= 3 exercícios distintos (doc 08 §6)."""
    for game_id, game in content.load_all().items():
        for concept in game.concepts:
            n = len(content.concept_exercises(game_id, concept.key))
            assert n >= 3, f"{concept.key} tem só {n} exercícios"


def test_cada_conceito_tem_uma_licao() -> None:
    for game_id, game in content.load_all().items():
        for concept in game.concepts:
            assert content.lesson_for_concept(game_id, concept.key) is not None


def test_avaliacao_inicial_tem_exercicios_suficientes() -> None:
    for game in content.load_all().values():
        assert len(placement.pool(game)) >= placement.LENGTH + 2


@pytest.mark.parametrize("ref", ALL_BOARD, ids=ids(ALL_BOARD))
def test_todo_exercicio_de_lance_tem_solucao_confirmada_pelo_motor(ref: ExerciseRef) -> None:
    ex, game_id = ref.exercise, ref.content.game_id
    legal = set(grading.legal_moves(ref))
    solutions = set(grading.correct_moves(ref))
    assert legal and solutions, "posição sem lances ou sem solução"
    assert solutions <= legal
    for move in solutions:
        assert grading.grade(ref, move).correct, move
    for move in legal - solutions:
        result = grading.grade(ref, move)
        assert not result.correct, move
        assert result.feedback
    if ex.goal == "listed":
        assert set(ex.accepted) == solutions
    if ex.goal == "listed" and ex.verify == "best":
        # Os lances aceitos são exatamente os que o motor considera sem perda relevante
        # (menos de 1 pedra / 1 peão) e todos os outros perdem pelo menos isso.
        scores = evaluation.move_scores(game_id, grading.exercise_state(ref))
        top = max(scores.values())
        close = {m for m, s in scores.items() if top - s < 100}
        assert close == set(ex.accepted), {m: s for m, s in scores.items()}


def test_exercicios_de_execucao_nao_exigem_que_o_lance_seja_o_melhor() -> None:
    legal_only = {ref.exercise.id for ref in ALL_BOARD if ref.exercise.verify == "legal"}
    assert legal_only == {"ck-move-1", "ck-cap-1", "ck-major-1", "ck-major-2", "ch-move-1"}


@pytest.mark.parametrize("ref", ALL_QUIZ, ids=ids(ALL_QUIZ))
def test_quiz_tem_uma_unica_alternativa_correta(ref: ExerciseRef) -> None:
    ex = ref.exercise
    assert grading.grade(ref, ex.correct_option or "").correct
    for option in ex.options:
        if option.id != ex.correct_option:
            assert not grading.grade(ref, option.id).correct
    with pytest.raises(grading.InvalidAnswerError):
        grading.grade(ref, "z")


@pytest.mark.parametrize("ref", ALL_BOARD, ids=ids(ALL_BOARD))
def test_resposta_ilegal_nao_e_corrigida(ref: ExerciseRef) -> None:
    with pytest.raises(grading.InvalidAnswerError):
        grading.grade(ref, "zz")
    with pytest.raises(grading.InvalidAnswerError):
        grading.grade(ref, "99")


@pytest.mark.parametrize("ref", ALL_BOARD + ALL_QUIZ, ids=ids(ALL_BOARD + ALL_QUIZ))
def test_dicas_em_tres_niveis_nao_vazias(ref: ExerciseRef) -> None:
    texts = [grading.hint_text(ref, level) for level in (1, 2, 3)]
    assert all(t.strip() for t in texts)
    assert len(set(texts)) == 3
    with pytest.raises(ValueError):
        grading.hint_text(ref, 4)


def test_dica_3_e_o_resumo_do_conceito() -> None:
    ref = content.find_exercise("tt-win-1")
    assert ref is not None
    assert grading.hint_text(ref, 3) == ref.content.concept("tt.win_in_one").summary


def test_lei_da_maioria_os_exercicios_tem_captura_menor_proibida() -> None:
    for exercise_id in ("ck-major-1", "ck-major-2"):
        ref = content.find_exercise(exercise_id)
        assert ref is not None
        state = grading.exercise_state(ref)
        lengths = [len(taken) for i, p in enumerate(state.squares)
                   if p != "." and p.lower() == state.to_move
                   for _, taken in _captures(state.squares, i)]
        assert min(lengths) < max(lengths), "o exercício precisa ter uma captura menor"
        legal_lengths = {len(m.captured) for m in generate(state.squares, state.to_move)}
        assert legal_lengths == {max(lengths)}


def test_promocao_so_conta_quando_o_lance_termina_na_ultima_fileira() -> None:
    ref = content.find_exercise("ck-promo-2")
    assert ref is not None
    assert grading.correct_moves(ref) == ["7-2"]


def test_feedback_de_erro_nao_cita_a_solucao_exceto_na_refutacao_do_bloqueio() -> None:
    """Em `block_loss` a refutação (a vitória do adversário) é justamente a explicação do erro."""
    for ref in ALL_BOARD:
        if ref.exercise.goal == "block_loss":
            continue
        wrong = set(grading.legal_moves(ref)) - set(grading.correct_moves(ref))
        for move in wrong:
            feedback = grading.grade(ref, move).feedback
            for solution in grading.correct_moves(ref):
                assert f" {solution}" not in feedback.replace(".", " ")


def test_afirmacao_do_conteudo_cavalo_f6_nao_evita_o_mate_de_f7() -> None:
    """ch-mate-def-1 diz que atacar a dama com o cavalo de g8 não basta."""
    ref = content.find_exercise("ch-mate-def-1")
    assert ref is not None
    result = grading.grade(ref, "g8f6")
    assert not result.correct
    assert "f7" in result.feedback
