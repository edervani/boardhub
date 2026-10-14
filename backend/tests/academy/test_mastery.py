"""RF-025 / CA-025 / T-025: domínio, dicas e revisão espaçada (funções puras)."""

from datetime import UTC, datetime, timedelta

from app.academy import mastery
from app.academy.mastery import Evidence, Progress

T0 = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


def run(attempts: list[tuple[bool, int, str, int]]) -> Progress:
    """Aplica tentativas (correta, dica, exercício, dia) e devolve o progresso final."""
    progress = Progress()
    correct_by: list[tuple[str, int]] = []
    for correct, hint, exercise, day in attempts:
        if correct:
            correct_by.append((exercise, day))
        evidence = Evidence(len(correct_by), len({e for e, _ in correct_by}),
                            len({d for _, d in correct_by}))
        progress = mastery.apply_attempt(progress, correct=correct, hint_level=hint,
                                         evidence=evidence, now=T0 + timedelta(days=day))
    return progress


def test_ganho_de_dominio_reduzido_por_dicas() -> None:
    gains = [mastery.next_mastery(0.0, True, h) for h in (0, 1, 2, 3)]
    assert gains[0] > gains[1] > gains[2]
    assert gains[2] == gains[3]
    assert mastery.next_mastery(0.5, False, 0) < 0.5


def test_calibracao_cinco_acertos_sem_dica_alcancam_o_limiar() -> None:
    """P-18: com alfa = 0,25 o resultado seria 0,763 e CA-025 nunca poderia ser atendido."""
    value = 0.0
    for _ in range(5):
        value = mastery.next_mastery(value, True, 0)
    assert value >= mastery.MASTERY_THRESHOLD


def test_uma_resposta_isolada_nunca_concede_dominio() -> None:
    assert run([(True, 0, "a", 0)]).status == mastery.IN_PRACTICE


def test_cinco_acertos_no_mesmo_exercicio_nao_concedem_dominio() -> None:
    progress = run([(True, 0, "a", 0), (True, 0, "a", 0), (True, 0, "a", 1),
                    (True, 0, "a", 1), (True, 0, "a", 2), (True, 0, "a", 2)])
    assert progress.mastery >= mastery.MASTERY_THRESHOLD
    assert progress.status == mastery.IN_PRACTICE


def test_cinco_acertos_em_tres_exercicios_em_dois_dias_concedem_dominio() -> None:
    progress = run([(True, 0, "a", 0), (True, 0, "b", 0), (True, 0, "c", 0),
                    (True, 0, "a", 1), (True, 0, "b", 1)])
    assert progress.status == mastery.MASTERED
    assert progress.mastered_at == T0 + timedelta(days=1)
    assert progress.next_review_at == T0 + timedelta(days=1 + 3)


def test_acertos_em_um_unico_dia_nao_concedem_dominio() -> None:
    progress = run([(True, 0, x, 0) for x in "abcab"])
    assert progress.status == mastery.IN_PRACTICE


def test_dicas_atrasam_o_dominio() -> None:
    with_hints = run([(True, 2, "a", 0), (True, 2, "b", 0), (True, 2, "c", 0),
                      (True, 2, "a", 1), (True, 2, "b", 1)])
    assert with_hints.mastery < mastery.MASTERY_THRESHOLD
    assert with_hints.status == mastery.IN_PRACTICE


def mastered() -> Progress:
    return run([(True, 0, "a", 0), (True, 0, "b", 0), (True, 0, "c", 0),
                (True, 0, "a", 1), (True, 0, "b", 1)])


def evidence() -> Evidence:
    return Evidence(6, 3, 2)


def test_revisao_espacada_3_7_21_60_dias() -> None:
    progress = mastered()
    now = progress.next_review_at
    assert now is not None
    expected = [7, 21, 60, 60]
    for days in expected:
        assert mastery.review_due(progress, now)
        progress = mastery.apply_attempt(progress, correct=True, hint_level=0,
                                         evidence=evidence(), now=now)
        assert progress.status == mastery.MASTERED
        assert progress.next_review_at == now + timedelta(days=days)
        now = now + timedelta(days=days)


def test_erro_na_revisao_devida_leva_a_em_revisao_e_reinicia_o_intervalo() -> None:
    progress = mastered()
    due = progress.next_review_at
    assert due is not None
    failed = mastery.apply_attempt(progress, correct=False, hint_level=0, evidence=evidence(),
                                   now=due + timedelta(days=1))
    assert failed.status == mastery.IN_REVIEW
    assert failed.review_stage == 0
    assert failed.next_review_at is None
    again = mastery.apply_attempt(failed, correct=True, hint_level=0, evidence=evidence(),
                                  now=due + timedelta(days=2))
    assert again.status == mastery.MASTERED
    assert again.next_review_at == due + timedelta(days=2 + 3)


def test_erro_fora_da_revisao_nao_tira_o_dominio() -> None:
    progress = mastered()
    due = progress.next_review_at
    assert due is not None
    early = mastery.apply_attempt(progress, correct=False, hint_level=0, evidence=evidence(),
                                  now=due - timedelta(days=1))
    assert early.status == mastery.MASTERED
    assert early.next_review_at == due
