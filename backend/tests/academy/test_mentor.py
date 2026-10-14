"""RF-024 / CA-024 / T-024: o Mentor reexecuta a partida e só afirma o que o motor calculou."""

import pytest

from app.ai.llm.provider import cited_in
from app.ai.mentor import analysis, evaluation
from app.game_engines.tictactoe import TicTacToeEngine

TTT = TicTacToeEngine()


def perfect_ttt_game() -> list[str]:
    state = TTT.initial_state()
    moves: list[str] = []
    while TTT.outcome(state) is None:
        best = evaluation.best_move("tictactoe", state)
        assert best is not None
        moves.append(best.move)
        state = TTT.apply(state, TTT.parse_move(best.move))
    return moves


def test_velha_jogo_perfeito_nao_tem_momentos_criticos() -> None:
    result = analysis.analyze_game("tictactoe", perfect_ttt_game(), frozenset({1, 2}))
    assert result.moments == []
    assert result.analyzed_moves == result.user_moves == 9
    assert not result.truncated


def test_velha_deixar_de_bloquear_e_erro_grave_com_refutacao_e_conceito() -> None:
    # X: 0, 1 e 2 (vence). O joga 4, e depois 6 em vez de bloquear a casa 2.
    result = analysis.analyze_game("tictactoe", ["0", "4", "1", "6", "2"], frozenset({2}))
    assert len(result.moments) == 1
    m = result.moments[0]
    assert (m.ply, m.seat, m.severity, m.kind) == (3, 2, "blunder", "lost_position")
    assert (m.played, m.best, m.reply) == ("6", "2", "2")
    assert m.reply_is_win and m.reason == "block" and m.concept_key == "tt.block"
    assert result.counts == {"inaccuracy": 0, "mistake": 0, "blunder": 1}
    text = analysis.explain("tictactoe", m)
    assert text.startswith("No lance 4, você jogou linha 3, coluna 1.")
    assert "vencer com linha 1, coluna 3" in text
    assert "Uma opção melhor era linha 1, coluna 3, que bloqueava a vitória do adversário." in text


def test_velha_so_analisa_os_lances_do_usuario() -> None:
    result = analysis.analyze_game("tictactoe", ["0", "4", "1", "6", "2"], frozenset({1}))
    assert result.moments == []
    assert result.user_moves == 3


def test_analise_e_deterministica() -> None:
    moves = ["0", "4", "1", "6", "2"]
    a = analysis.analyze_game("tictactoe", moves, frozenset({2}))
    b = analysis.analyze_game("tictactoe", moves, frozenset({2}))
    assert a == b


def test_texto_so_cita_lances_que_o_motor_calculou() -> None:
    result = analysis.analyze_game("tictactoe", ["0", "4", "1", "6", "2"], frozenset({2}))
    m = result.moments[0]
    text = analysis.explain("tictactoe", m)
    allowed = {m.played_label, m.best_label, m.reply_label}
    assert cited_in(text) == allowed


def test_damas_lance_que_entrega_peca_e_erro_com_captura_do_adversario() -> None:
    result = analysis.analyze_game("checkers", ["21-17", "9-14", "22-18"], frozenset({1}))
    assert len(result.moments) == 1
    m = result.moments[0]
    assert (m.ply, m.played, m.severity, m.kind) == (2, "22-18", "mistake", "lost_material")
    assert m.loss == 100 and m.best != m.played
    assert m.reply is not None and m.reply_detail == "1 peça"
    text = analysis.explain("checkers", m)
    assert "No lance 2, você jogou 22-18." in text
    assert f"capturar 1 peça com {m.reply}" in text
    assert "1 pedra a menos" in text
    assert m.concept_key == "ck.mandatory_capture"


def test_damas_orcamento_esgotado_marca_a_analise_como_parcial() -> None:
    result = analysis.analyze_game("checkers", ["21-17", "9-14", "22-18"], frozenset({1}),
                                   node_budget=20)
    assert result.truncated
    assert result.analyzed_moves < result.user_moves


def test_no_maximo_tres_momentos_ordenados_no_tempo() -> None:
    # Tantos erros quanto couberem: o usuário joga pelas duas cores, sempre o pior lance.
    state_moves: list[str] = []
    engine = evaluation.ENGINES["checkers"]
    state = engine.initial_state()
    for _ in range(10):
        scores = evaluation.move_scores("checkers", state)
        worst = min(scores, key=lambda k: (scores[k], k))
        state_moves.append(worst)
        state = engine.apply(state, engine.parse_move(worst))
        if engine.outcome(state):
            break
    result = analysis.analyze_game("checkers", state_moves, frozenset({1, 2}))
    assert len(result.moments) <= analysis.MAX_MOMENTS
    plies = [m.ply for m in result.moments]
    assert plies == sorted(plies)
    assert sum(result.counts.values()) >= len(result.moments)


def test_xadrez_mate_do_louco_e_erro_grave_que_permite_o_mate() -> None:
    result = analysis.analyze_game("chess", ["f2f3", "e7e5", "g2g4", "d8h4"], frozenset({1}))
    assert len(result.moments) == 1
    m = result.moments[0]
    assert (m.ply, m.severity, m.kind, m.played) == (2, "blunder", "allowed_loss", "g2g4")
    assert m.reply == "d8h4" and m.reply_is_win
    text = analysis.explain("chess", m)
    assert "o adversário podia vencer com Dh4#" in text
    assert "No lance 2, você jogou g4." in text
    assert m.concept_key == "ch.mate_in_one"


def test_xadrez_mate_perdido() -> None:
    result = analysis.analyze_game("chess", ["f2f3", "e7e5", "g2g4", "a7a6"], frozenset({2}))
    assert len(result.moments) == 1
    m = result.moments[0]
    assert (m.ply, m.kind, m.severity, m.best) == (3, "missed_win", "blunder", "d8h4")
    assert m.reason == "win"
    assert "Uma opção melhor era Dh4#, que dava xeque-mate." in analysis.explain("chess", m)


def test_xadrez_abertura_normal_nao_gera_momentos() -> None:
    result = analysis.analyze_game("chess", ["e2e4", "e7e5", "g1f3", "b8c6"], frozenset({1, 2}))
    assert result.moments == []


def test_xadrez_dama_entregue_e_classificada_por_perda_em_centipeoes() -> None:
    # 1.e4 e5 2.Dh5 Cc6 3.Dxe5?? Cxe5: a dama é perdida por um peão.
    result = analysis.analyze_game("chess", ["e2e4", "e7e5", "d1h5", "b8c6", "h5e5", "c6e5"],
                                   frozenset({1}))
    blunders = [m for m in result.moments if m.ply == 4]
    assert blunders and blunders[0].severity == "blunder"
    assert blunders[0].loss >= 300
    assert blunders[0].reply == "c6e5" and blunders[0].reply_detail == "a dama em e5"


@pytest.mark.parametrize(("best", "played", "expected"), [
    (0, -49, None), (0, -50, ("inaccuracy", "lost_material")),
    (0, -99, ("inaccuracy", "lost_material")), (0, -100, ("mistake", "lost_material")),
    (0, -299, ("mistake", "lost_material")), (0, -300, ("blunder", "lost_material")),
    (evaluation.CHESS_MATE - 1, 0, ("blunder", "missed_win")),
    (0, -evaluation.CHESS_MATE + 2, ("blunder", "allowed_loss")),
])
def test_limiares_do_xadrez_seguem_o_doc_08(best: int, played: int,
                                            expected: tuple[str, str] | None) -> None:
    assert analysis.classify("chess", best, played) == expected


def test_limiares_de_damas_e_velha() -> None:
    assert analysis.classify("checkers", 0, -99) is None
    assert analysis.classify("checkers", 0, -100) == ("mistake", "lost_material")
    assert analysis.classify("tictactoe", 0, -evaluation.TTT_WIN) == ("blunder", "lost_position")
    assert analysis.classify("tictactoe", evaluation.TTT_WIN, 0) is None
    assert analysis.classify("tictactoe", -evaluation.TTT_WIN, -evaluation.TTT_WIN) is None
