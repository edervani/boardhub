"""RF-022 / CA-022 / T-022: avaliação inicial adaptativa (funções puras)."""

import pytest

from app.academy import content, placement
from app.academy.placement import Step


def play(game_id: str, declared: str, always_correct: bool) -> list[Step]:
    game = content.load_all()[game_id]
    steps: list[Step] = []
    while (nxt := placement.pick_next(game, declared, steps)) is not None:
        ex, concept = nxt
        steps.append(Step(ex, concept, always_correct))
    return steps


@pytest.mark.parametrize("game_id", ["tictactoe", "checkers", "chess"])
def test_avaliacao_tem_6_exercicios_sem_repeticao(game_id: str) -> None:
    steps = play(game_id, "knows_rules", True)
    assert len(steps) == placement.LENGTH
    assert len({s.exercise.id for s in steps}) == placement.LENGTH


def test_acerto_sobe_a_dificuldade_e_erro_desce() -> None:
    assert placement.target_difficulty("knows_rules", []) == 2
    assert placement.target_difficulty("knows_rules", [True]) == 3
    assert placement.target_difficulty("knows_rules", [True, True, True]) == 3
    assert placement.target_difficulty("never", [False, False]) == 1
    assert placement.target_difficulty("competitive", [False]) == 2


def test_autodeclaracao_define_o_ponto_de_partida() -> None:
    game = content.load_all()["tictactoe"]
    first = {d: placement.pick_next(game, d, []) for d in placement.START_DIFFICULTY}
    assert first["never"] is not None and first["never"][0].difficulty == 1
    assert first["competitive"] is not None and first["competitive"][0].difficulty == 3


def test_sequencia_e_deterministica() -> None:
    a = [s.exercise.id for s in play("checkers", "regular", True)]
    b = [s.exercise.id for s in play("checkers", "regular", True)]
    assert a == b


def test_dominio_inicial_nunca_passa_de_meio() -> None:
    steps = play("tictactoe", "competitive", True)
    values = placement.concept_mastery(steps)
    assert values and max(values.values()) <= 0.5
    wrong = placement.concept_mastery(play("tictactoe", "never", False))
    assert wrong and set(wrong.values()) == {0.0}


def test_nivel_de_ia_sugerido_vem_do_desempenho_e_nao_da_idade() -> None:
    assert placement.suggested_ai_level(play("tictactoe", "never", False)) == 1
    assert placement.suggested_ai_level(play("tictactoe", "never", True)) == 4
    assert "age" not in placement.__dict__
