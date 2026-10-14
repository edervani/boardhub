"""RF-022 a RF-025 (CA-022, CA-023, CA-025) e T-007 (Academy não lê `piece_styles`)."""

import json
import pathlib
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.academy import content, grading, placement
from app.models import ExerciseAttempt, SkillProgress
from tests.conftest import FakeClock, MemoryMailer
from tests.helpers import API, conta_logada, csrf, novo_cliente


@pytest.fixture
def aluno(client: TestClient, mailer: MemoryMailer) -> TestClient:
    return conta_logada(client, mailer)


def outro_aluno(client: TestClient, mailer: MemoryMailer) -> TestClient:
    return conta_logada(novo_cliente(client), mailer, 2)


def responder(c: TestClient, exercise_id: str, answer: str, **extra: Any) -> Response:
    return c.post(f"{API}/academy/exercises/{exercise_id}/attempts", headers=csrf(c),
                  json={"answer": answer, **extra})


def solucao(exercise_id: str) -> str:
    """Resposta certa calculada pelo motor (os testes não decoram respostas)."""
    ref = content.find_exercise(exercise_id)
    assert ref is not None
    if ref.exercise.type == "rule_quiz":
        return str(ref.exercise.correct_option)
    return grading.correct_moves(ref)[0]


def errada(exercise_id: str) -> str:
    ref = content.find_exercise(exercise_id)
    assert ref is not None
    if ref.exercise.type == "rule_quiz":
        return next(o.id for o in ref.exercise.options if o.id != ref.exercise.correct_option)
    return next(m for m in grading.legal_moves(ref) if m not in grading.correct_moves(ref))


def progresso(c: TestClient, game_id: str = "tictactoe") -> dict[str, dict[str, Any]]:
    resp = c.get(f"{API}/academy/progress", params={"game_id": game_id})
    assert resp.status_code == 200
    return {p["concept_key"]: p for p in resp.json()["concepts"]}


# ---------------------------------------------------------------- trilhas e lições

def test_academy_exige_login(client: TestClient) -> None:
    for path in ("/academy/tracks", "/academy/progress", "/academy/tictactoe/lessons",
                 "/academy/exercises/tt-win-1"):
        assert client.get(f"{API}{path}").status_code == 401


def test_trilhas_por_jogo(aluno: TestClient) -> None:
    resp = aluno.get(f"{API}/academy/tracks")
    assert resp.status_code == 200
    tracks = {t["game_id"]: t for t in resp.json()}
    assert set(tracks) == {"tictactoe", "checkers", "chess"}
    assert tracks["tictactoe"]["lessons_count"] == 5
    assert tracks["tictactoe"]["concepts_mastered"] == 0
    assert tracks["chess"]["title"].startswith("Xadrez")


def test_licoes_da_trilha_nao_trazem_solucao(aluno: TestClient) -> None:
    resp = aluno.get(f"{API}/academy/tictactoe/lessons")
    assert resp.status_code == 200
    body = resp.json()
    assert [c["key"] for c in body["concepts"]][:2] == ["tt.rules", "tt.win_in_one"]
    assert body["lessons"][1]["exercises"][0] == {
        "id": "tt-win-1", "type": "best_move", "difficulty": 1, "solved": False}
    raw = resp.text
    for forbidden in ("accepted", "correct_option", "explanation", '"goal"'):
        assert forbidden not in raw


def test_jogo_inexistente_ou_sem_conteudo_da_404(aluno: TestClient) -> None:
    assert aluno.get(f"{API}/academy/go/lessons").status_code == 404
    assert aluno.get(f"{API}/academy/exercises/nao-existe").status_code == 404


# ---------------------------------------------------------------- CA-023

def test_get_exercicio_nao_expoe_a_resposta(aluno: TestClient) -> None:
    resp = aluno.get(f"{API}/academy/exercises/tt-win-1")
    assert resp.status_code == 200
    ex = resp.json()
    assert ex["position"] == {"board": "XX_O_O___", "to_move": "X"}
    assert ex["legal_moves"] == ["2", "4", "6", "7", "8"]
    assert ex["hints_used"] == 0 and ex["concept_key"] == "tt.win_in_one"
    assert set(ex) == {"id", "game_id", "lesson_id", "concept_key", "concept_title", "type",
                       "difficulty", "prompt", "position", "legal_moves", "options",
                       "hints_used", "hints_available"}
    quiz = aluno.get(f"{API}/academy/exercises/tt-rules-1").json()
    assert quiz["position"] is None and quiz["legal_moves"] == []
    assert [o["id"] for o in quiz["options"]] == ["a", "b", "c", "d"]
    assert "correct" not in json.dumps(quiz)


def test_resposta_correta_e_incorreta_avaliadas_pelo_motor(aluno: TestClient) -> None:
    certo = responder(aluno, "tt-win-1", "2")
    assert certo.status_code == 200
    body = certo.json()
    assert body["correct"] is True and body["explanation"]
    assert body["mastery"] == pytest.approx(0.3) and body["status"] == "in_practice"
    errado = responder(aluno, "tt-win-1", "4").json()
    assert errado["correct"] is False and errado["explanation"] is None
    assert "não encerra a partida" in errado["feedback"]
    assert errado["mastery"] < body["mastery"]


def test_erro_de_bloqueio_mostra_a_refutacao_calculada_pelo_motor(aluno: TestClient) -> None:
    body = responder(aluno, "tt-block-1", "1").json()
    assert body["correct"] is False
    assert "o adversário vence com linha 2, coluna 3" in body["feedback"]


def test_quiz_e_corrigido_no_servidor(aluno: TestClient) -> None:
    assert responder(aluno, "tt-rules-1", "b").json()["correct"] is True
    assert responder(aluno, "tt-rules-1", "a").json()["correct"] is False


def test_resposta_invalida_nao_conta_como_tentativa(aluno: TestClient, db: Session) -> None:
    assert responder(aluno, "tt-win-1", "3").status_code == 422  # casa ocupada
    assert responder(aluno, "tt-win-1", "abc").status_code == 422
    assert responder(aluno, "tt-rules-1", "z").status_code == 422
    assert responder(aluno, "nao-existe", "1").status_code == 404
    assert db.scalars(select(ExerciseAttempt)).all() == []


def test_corpo_extra_e_rejeitado_e_o_cliente_nao_informa_dicas_nem_pontuacao(
        aluno: TestClient) -> None:
    for extra in ({"hints_used": 0}, {"mastery": 1}, {"correct": True}):
        assert responder(aluno, "tt-win-1", "2", **extra).status_code == 422


def test_post_exige_csrf(aluno: TestClient) -> None:
    resp = aluno.post(f"{API}/academy/exercises/tt-win-1/attempts", json={"answer": "2"})
    assert resp.status_code == 403


def test_dicas_em_ordem_e_reduzem_o_ganho(client: TestClient, mailer: MemoryMailer) -> None:
    a = conta_logada(client, mailer)
    b = outro_aluno(client, mailer)
    sem_dica = responder(a, "tt-win-1", "2").json()
    assert b.post(f"{API}/academy/exercises/tt-win-1/hints", headers=csrf(b),
                  json={"level": 2}).status_code == 422  # pula a dica 1
    h1 = b.post(f"{API}/academy/exercises/tt-win-1/hints", headers=csrf(b), json={"level": 1})
    assert h1.status_code == 200 and h1.json()["text"] == "Observe a linha 1."
    h2 = b.post(f"{API}/academy/exercises/tt-win-1/hints", headers=csrf(b), json={"level": 2})
    assert h2.json()["text"] == "Jogue na linha 1, coluna 3." and h2.json()["hints_used"] == 2
    h3 = b.post(f"{API}/academy/exercises/tt-win-1/hints", headers=csrf(b), json={"level": 3})
    assert h3.json()["text"].startswith("Antes de qualquer plano")
    assert b.get(f"{API}/academy/exercises/tt-win-1").json()["hints_used"] == 3
    com_dica = responder(b, "tt-win-1", "2").json()
    assert com_dica["hint_level"] == 3
    assert com_dica["mastery"] < sem_dica["mastery"]
    assert b.get(f"{API}/academy/exercises/tt-win-1").json()["hints_used"] == 0
    assert b.post(f"{API}/academy/exercises/tt-win-1/hints", headers=csrf(b),
                  json={"level": 4}).status_code == 422


def test_limite_de_60_tentativas_por_minuto(aluno: TestClient) -> None:
    for _ in range(60):
        assert responder(aluno, "tt-rules-1", "b").status_code == 200
    assert responder(aluno, "tt-rules-1", "b").status_code == 429


# ---------------------------------------------------------------- CA-025

def test_cinco_acertos_no_mesmo_exercicio_nao_concedem_dominio(aluno: TestClient,
                                                                fake_clock: FakeClock) -> None:
    for _ in range(3):
        for _ in range(2):
            assert responder(aluno, "tt-win-1", "2").status_code == 200
        fake_clock.advance(days=1)
    p = progresso(aluno)["tt.win_in_one"]
    assert p["mastery"] >= 0.8
    assert p["status"] == "in_practice"


def test_cinco_acertos_em_tres_exercicios_e_dois_dias_concedem_dominio(
        aluno: TestClient, fake_clock: FakeClock, db: Session) -> None:
    for ex in ("tt-win-1", "tt-win-2", "tt-win-3"):
        assert responder(aluno, ex, solucao(ex)).json()["mastered_now"] is False
    fake_clock.advance(days=1)
    assert responder(aluno, "tt-win-1", "2").json()["mastered_now"] is False
    last = responder(aluno, "tt-win-2", "8").json()
    assert last["mastered_now"] is True and last["status"] == "mastered"
    assert last["mastery"] >= 0.8 and last["next_review_at"]
    assert progresso(aluno)["tt.win_in_one"]["status"] == "mastered"
    track = next(t for t in aluno.get(f"{API}/academy/tracks").json()
                 if t["game_id"] == "tictactoe")
    assert track["concepts_mastered"] == 1
    assert len(db.scalars(select(ExerciseAttempt)).all()) == 5


def test_erro_em_revisao_devida_leva_a_em_revisao(aluno: TestClient,
                                                  fake_clock: FakeClock) -> None:
    for ex in ("tt-win-1", "tt-win-2", "tt-win-3"):
        responder(aluno, ex, solucao(ex))
    fake_clock.advance(days=1)
    responder(aluno, "tt-win-1", "2")
    assert responder(aluno, "tt-win-2", "8").json()["status"] == "mastered"
    assert progresso(aluno)["tt.win_in_one"]["review_due"] is False
    fake_clock.advance(days=3, minutes=1)
    assert progresso(aluno)["tt.win_in_one"]["review_due"] is True
    assert responder(aluno, "tt-win-1", errada("tt-win-1")).json()["status"] == "in_review"
    assert progresso(aluno)["tt.win_in_one"]["status"] == "in_review"
    assert responder(aluno, "tt-win-1", "2").json()["status"] == "mastered"


def test_progresso_e_privado_por_usuario(client: TestClient, mailer: MemoryMailer) -> None:
    a = conta_logada(client, mailer)
    b = outro_aluno(client, mailer)
    responder(a, "tt-win-1", "2")
    assert progresso(a)["tt.win_in_one"]["status"] == "in_practice"
    assert progresso(b)["tt.win_in_one"]["status"] == "not_started"


def test_exclusao_da_conta_apaga_o_progresso(aluno: TestClient, db: Session) -> None:
    responder(aluno, "tt-win-1", "2")
    assert db.scalars(select(SkillProgress)).all()
    db.execute(text("DELETE FROM users"))
    db.commit()
    assert db.scalars(select(SkillProgress)).all() == []
    assert db.scalars(select(ExerciseAttempt)).all() == []


def test_academia_nao_le_estilos_de_peca(aluno: TestClient) -> None:
    """T-007: dificuldade e estilo visual são independentes."""
    antes = progresso(aluno)
    aluno.put(f"{API}/me/preferences", headers=csrf(aluno), json={"piece_styles": {
        "chess": "infantil"}})
    assert progresso(aluno) == antes
    root = pathlib.Path(content.__file__).parent.parent
    for path in list((root / "academy").rglob("*.py")) + list((root / "ai").rglob("*.py")):
        assert "piece_styles" not in path.read_text(encoding="utf-8"), path


# ---------------------------------------------------------------- CA-022

def passo(c: TestClient, game: str, declared: str, answers: list[dict[str, str]]) -> Response:
    return c.post(f"{API}/academy/{game}/placement", headers=csrf(c),
                  json={"declared": declared, "answers": answers})


def avaliar(c: TestClient, game: str, declared: str, acertar: bool) -> dict[str, Any]:
    answers: list[dict[str, str]] = []
    while True:
        resp = passo(c, game, declared, answers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        if body["done"]:
            return dict(body)
        ex = body["next_exercise"]
        assert body["answered"] == len(answers) and body["total"] == placement.LENGTH
        answers.append({"exercise_id": ex["id"],
                        "answer": solucao(ex["id"]) if acertar else errada(ex["id"])})


def test_avaliacao_inicial_adaptativa_limita_o_dominio_a_meio(aluno: TestClient) -> None:
    result = avaliar(aluno, "tictactoe", "competitive", True)["result"]
    assert result["suggested_ai_level"] == 4
    assert result["concepts"] and all(0 < c["mastery"] <= 0.5 for c in result["concepts"])
    p = progresso(aluno)
    tested = {c["concept_key"] for c in result["concepts"]}
    for key in tested:
        assert p[key]["status"] == "in_practice" and p[key]["mastery"] <= 0.5
    assert all(p[k]["status"] == "not_started" for k in p if k not in tested)


def test_avaliacao_com_erros_sugere_nivel_baixo_e_nao_inicia_conceitos(aluno: TestClient) -> None:
    result = avaliar(aluno, "tictactoe", "never", False)["result"]
    assert result["suggested_ai_level"] == 1
    assert all(c["mastery"] == 0 for c in result["concepts"])
    assert all(c["status"] == "not_started" for c in progresso(aluno).values())


def test_autodeclaracao_define_o_primeiro_exercicio(aluno: TestClient) -> None:
    easy = passo(aluno, "chess", "never", []).json()["next_exercise"]
    assert easy["difficulty"] == 1
    hard = passo(aluno, "chess", "competitive", []).json()["next_exercise"]
    assert hard["difficulty"] == 3


def test_avaliacao_pode_ser_pulada_e_idade_nao_e_parametro(aluno: TestClient) -> None:
    assert all(c["status"] == "not_started" for c in progresso(aluno).values())  # nada feito
    resp = aluno.post(f"{API}/academy/tictactoe/placement", headers=csrf(aluno),
                      json={"declared": "never", "answers": [], "age_band": "under_12"})
    assert resp.status_code == 422


def test_sequencia_forjada_e_rejeitada(aluno: TestClient) -> None:
    first = passo(aluno, "tictactoe", "knows_rules", []).json()["next_exercise"]["id"]
    other = next(i for i in content.exercise_index() if i.startswith("tt-") and i != first)
    assert passo(aluno, "tictactoe", "knows_rules", [
        {"exercise_id": other, "answer": "a"}]).status_code == 422
    bad_answer = passo(aluno, "tictactoe", "knows_rules", [
        {"exercise_id": first, "answer": "zz"}])
    assert bad_answer.status_code == 422
    too_many = [{"exercise_id": first, "answer": "a"}] * 11
    assert passo(aluno, "tictactoe", "knows_rules", too_many).status_code == 422


def test_so_pode_refazer_depois_de_30_dias(aluno: TestClient, fake_clock: FakeClock) -> None:
    avaliar(aluno, "tictactoe", "regular", True)
    again = passo(aluno, "tictactoe", "regular", [])
    assert again.status_code == 409 and again.json()["type"] == "placement_too_soon"
    assert passo(aluno, "checkers", "regular", []).status_code == 200  # outro jogo
    fake_clock.advance(days=31)
    assert passo(aluno, "tictactoe", "regular", []).status_code == 200


def test_avaliacao_nao_reduz_dominio_ja_conquistado(aluno: TestClient, fake_clock: FakeClock,
                                                    db: Session) -> None:
    for ex in ("tt-win-1", "tt-win-2", "tt-win-3"):
        responder(aluno, ex, solucao(ex))
    fake_clock.advance(days=1)
    responder(aluno, "tt-win-1", "2")
    responder(aluno, "tt-win-2", "8")
    avaliar(aluno, "tictactoe", "never", False)
    assert progresso(aluno)["tt.win_in_one"]["status"] == "mastered"
    assert progresso(aluno)["tt.win_in_one"]["mastery"] >= 0.8
