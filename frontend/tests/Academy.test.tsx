import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { AcademyPage } from "../src/features/academy/AcademyPage";
import { ReviewPage } from "../src/features/academy/ReviewPage";
import type { Analysis, Exercise, LessonsResponse, Track } from "../src/features/academy/types";
import { History } from "../src/features/tictactoe/History";
import { bodyOf, mockApi } from "./helpers";

afterEach(() => { vi.unstubAllGlobals(); });

const track: Track = {
  game_id: "tictactoe", game_name: "Jogo da Velha", title: "Jogo da velha: do básico à estratégia",
  description: "Regras e táticas.", lessons_count: 1, exercises_count: 1, concepts_total: 1, concepts_mastered: 0,
};

const lessons: LessonsResponse = {
  game_id: "tictactoe", content_version: "1", title: "Jogo da velha", description: "",
  concepts: [{ key: "tt.win_in_one", title: "Vencer em um lance", summary: "", prerequisites: [],
    mastery: 0, status: "not_started", review_due: false }],
  lessons: [{ id: "tt-l2", concept_key: "tt.win_in_one", concept_title: "Vencer em um lance",
    title: "Vença em um lance", summary: "", body: ["Complete a linha."], completed: false,
    exercises: [{ id: "tt-win-1", type: "best_move", difficulty: 1, solved: false }] }],
};

const exercise: Exercise = {
  id: "tt-win-1", game_id: "tictactoe", lesson_id: "tt-l2", concept_key: "tt.win_in_one",
  concept_title: "Vencer em um lance", type: "best_move", difficulty: 1,
  prompt: "Você é X. Encontre o lance que vence.",
  position: { board: "XX_OO____", to_move: "X" }, legal_moves: ["2", "5", "6", "7", "8"],
  options: [], hints_used: 0, hints_available: 3,
};

const attempt = (correct: boolean) => ({
  correct, feedback: correct ? "Isso mesmo." : "Esse lance não vence.", explanation: null, hint_level: 0,
  concept_key: "tt.win_in_one", mastery: correct ? 0.3 : 0, status: "in_practice",
  mastered_now: false, next_review_at: null,
});

function routes(onAttempt: (init: RequestInit | undefined) => { body: unknown }) {
  return {
    "GET /academy/tracks": { body: [track] },
    "GET /academy/tictactoe/lessons": { body: lessons },
    "GET /academy/exercises/tt-win-1": { body: exercise },
    "POST /academy/exercises/tt-win-1/attempts": onAttempt,
    "POST /academy/exercises/tt-win-1/hints": { body: { level: 1, text: "Olhe a linha de cima.", hints_used: 1 } },
  };
}

async function abrirExercicio() {
  await userEvent.click(await screen.findByRole("button", { name: "Abrir trilha Jogo da velha: do básico à estratégia" }));
  await userEvent.click(await screen.findByRole("button", { name: "Vença em um lance" }));
  await userEvent.click(screen.getByRole("button", { name: /Exercício 1/ }));
  await screen.findByText("Você é X. Encontre o lance que vence.");
}

test("trilha, lição e exercício: resposta enviada ao servidor sem hints_used", async () => {
  const fetchMock = mockApi(routes(() => ({ body: attempt(true) })));
  render(<AcademyPage />);
  await abrirExercicio();
  await userEvent.click(screen.getByRole("button", { name: "Linha 1, coluna 3: vazia" }));
  expect(await screen.findByText("Isso mesmo.")).toBeInTheDocument();
  expect(screen.getByText(/Domínio de “Vencer em um lance”: 30%/)).toBeInTheDocument();
  expect(screen.getByText(/Em prática/)).toBeInTheDocument();
  const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/attempts"));
  const body = bodyOf(call?.[1] as RequestInit);
  expect(body.answer).toBe("2");
  expect(body).not.toHaveProperty("hints_used");
});

test("resposta errada mostra o feedback e permite tentar de novo", async () => {
  mockApi(routes(() => ({ body: attempt(false) })));
  render(<AcademyPage />);
  await abrirExercicio();
  await userEvent.click(screen.getByRole("button", { name: "Linha 3, coluna 1: vazia" }));
  expect(await screen.findByText("Esse lance não vence.")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
  expect(screen.queryByText("Esse lance não vence.")).not.toBeInTheDocument();
});

test("dica vem do servidor", async () => {
  mockApi(routes(() => ({ body: attempt(true) })));
  render(<AcademyPage />);
  await abrirExercicio();
  await userEvent.click(screen.getByRole("button", { name: "Pedir dica" }));
  expect(await screen.findByText(/Dica 1: Olhe a linha de cima./)).toBeInTheDocument();
});

test("exercício de regras usa grupo de opções rotulado", async () => {
  const quiz: Exercise = { ...exercise, type: "rule_quiz", position: null, legal_moves: [],
    options: [{ id: "a", text: "Três em linha" }, { id: "b", text: "Quatro cantos" }] };
  const fetchMock = mockApi({ ...routes(() => ({ body: attempt(true) })), "GET /academy/exercises/tt-win-1": { body: quiz } });
  render(<AcademyPage />);
  await userEvent.click(await screen.findByRole("button", { name: /Abrir trilha/ }));
  await userEvent.click(await screen.findByRole("button", { name: "Vença em um lance" }));
  await userEvent.click(screen.getByRole("button", { name: /Exercício 1/ }));
  expect(await screen.findByRole("group", { name: "Escolha uma resposta" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("radio", { name: /Três em linha/ }));
  await userEvent.click(screen.getByRole("button", { name: "Responder" }));
  await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/attempts"))).toBe(true));
});

const analysis: Analysis = {
  match_id: "m1", game_id: "tictactoe", engine_version: "mentor-1", analyzed_moves: 5, user_moves: 5,
  truncated: false, counts: { inaccuracy: 0, mistake: 0, blunder: 1 },
  moments: [{ ply: 3, move_number: 4, severity: "blunder", kind: "allowed_loss", played: "6",
    played_label: "linha 3, coluna 1", best: "2", best_label: "linha 1, coluna 3", reply: "2",
    reply_label: "linha 1, coluna 3", explanation: "No lance 4, você jogou linha 3, coluna 1.",
    explanation_source: "template", concept_key: "tt.block", concept_title: "Bloquear o adversário",
    lesson_id: "tt-l3", position: { board: "XX__O____", to_move: "O" } }],
  caveat: "Análise por material, sem motor externo.",
};

test("revisão mostra severidade em texto, explicação e a ressalva", async () => {
  mockApi({ "GET /matches/m1/analysis": { body: analysis } });
  render(<ReviewPage matchId="m1" onBack={() => undefined} />);
  expect(await screen.findByText("Lance 4: Erro grave")).toBeInTheDocument();
  expect(screen.getByText("No lance 4, você jogou linha 3, coluna 1.")).toBeInTheDocument();
  expect(screen.getByText("Análise por material, sem motor externo.")).toBeInTheDocument();
  // tabuleiro somente leitura
  expect(screen.getByRole("button", { name: "Linha 1, coluna 3: vazia" })).toHaveAttribute("aria-disabled", "true");
});

test("revisão mostra a mensagem de erro do servidor", async () => {
  mockApi({ "GET /matches/m1/analysis": { status: 409, body: { type: "analysis_unavailable", title: "A partida ainda não terminou." } } });
  render(<ReviewPage matchId="m1" onBack={() => undefined} />);
  expect(await screen.findByRole("alert")).toBeInTheDocument();
});

test("histórico oferece revisar só partidas finalizadas", async () => {
  mockApi({ "GET /me/matches?limit=20": { body: { next_cursor: null, items: [
    { id: "a", game_id: "tictactoe", mode: "ai", status: "finished", result: "draw", created_at: "2026-10-13T00:00:00Z" },
    { id: "b", game_id: "tictactoe", mode: "ai", status: "in_progress", result: null, created_at: "2026-10-13T00:00:00Z" },
  ] } } });
  const onReview = vi.fn();
  render(<History onReview={onReview} />);
  const btn = await screen.findByRole("button", { name: "Revisar partida" });
  await userEvent.click(btn);
  expect(onReview).toHaveBeenCalledWith("a");
  expect(screen.getAllByRole("button", { name: "Revisar partida" })).toHaveLength(1);
});
