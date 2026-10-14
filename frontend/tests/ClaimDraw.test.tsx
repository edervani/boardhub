import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { OnlineMatch, type BoardRenderer } from "../src/features/lobby/OnlineMatch";
import { onlineStatusText } from "../src/features/lobby/onlineStatus";
import { GamePage } from "../src/features/tictactoe/GamePage";
import type { MatchView, Me } from "../src/services/types";
import { FakeWebSocket, installFakeWebSocket, mockApi } from "./helpers";

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

const me: Me = { id: "u1", email: "a@example.test", display_name: "jogador_teste_01",
  email_verified: true, age_band: "18_plus", role: "user", supervised: false };

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
const BUTTON = { name: "Reivindicar empate" };

const chess = (over: Partial<MatchView> = {}): MatchView => ({
  id: "m1", game_id: "chess", mode: "online_casual", status: "in_progress", ply: 8,
  state: { schema_version: 1, fen: START, moves: [] }, to_move_seat: 1,
  legal_moves: ["g1f3"], result: null, end_reason: null, ai_level: null,
  created_at: "2026-10-14T00:00:00Z", finished_at: null,
  seats: [{ seat: 1, is_ai: false, is_you: true }, { seat: 2, is_ai: false, is_you: false }],
  players: [
    { seat: 1, display_name: "jogador_teste_01", connected: true, grace_deadline: null },
    { seat: 2, display_name: "jogador_teste_02", connected: true, grace_deadline: null },
  ],
  invite_code: null, invite_expires_at: null, draw_offer_by_seat: null, ...over,
});

const renderBoard: BoardRenderer = ({ playable }) => (
  <div data-testid="board" data-playable={playable.join(",")} />
);

async function abrirOnline(over: Partial<MatchView> = {}) {
  installFakeWebSocket();
  mockApi({ "GET /matches/m1": { body: chess(over) } });
  render(<OnlineMatch matchId="m1" renderBoard={renderBoard} onLeave={vi.fn()} />);
  const ws = FakeWebSocket.instances[0]!;
  await screen.findByTestId("board");
  act(() => ws.open());
  return ws;
}

test("sem a indicação do servidor o botão de reivindicar empate não aparece", async () => {
  await abrirOnline();
  expect(screen.queryByRole("button", BUTTON)).toBeNull();
});

test("com can_claim_draw falso o botão não aparece", async () => {
  await abrirOnline({ can_claim_draw: false });
  expect(screen.queryByRole("button", BUTTON)).toBeNull();
});

test("o botão aparece quando o servidor indica e envia claim_draw pelo WebSocket", async () => {
  const ws = await abrirOnline({ can_claim_draw: true });
  const grupo = screen.getByRole("group", { name: "Reivindicação de empate" });
  expect(grupo).toHaveTextContent("Você pode reivindicar empate");
  expect(grupo.querySelector('[aria-live="polite"]')).not.toBeNull(); // anunciado ao leitor de tela
  await userEvent.click(screen.getByRole("button", BUTTON));
  const enviado = ws.sentMessages().find((m) => m.type === "claim_draw");
  expect(enviado?.payload).toEqual({ match_id: "m1" });
});

test("lance do adversário que habilita a reivindicação mostra o botão e avisa; o fim some com ele", async () => {
  const ws = await abrirOnline({ ply: 7, to_move_seat: 2, legal_moves: [] });
  expect(screen.queryByRole("button", BUTTON)).toBeNull();
  const evento = (canClaim: boolean, next: number) => ({ type: "move_applied", seq: 8, payload: {
    match_id: "m1", ply: 8, seat: 2, move: "f6g8", next_seat: next, legal_moves: ["g1f3"],
    state: { schema_version: 1, fen: START, moves: [] }, can_claim_draw: canClaim } });
  act(() => ws.receive(evento(true, 1)));
  expect(screen.getByRole("button", BUTTON)).toBeInTheDocument();
  expect(screen.getByText(/Você pode reivindicar empate\.$/)).toBeInTheDocument();
  act(() => ws.receive({ type: "match_ended", seq: 8, payload: {
    match_id: "m1", result: "draw", end_reason: "repetition", ply: 8 } }));
  expect(screen.queryByRole("button", BUTTON)).toBeNull();
  expect(screen.getByText("Empate por repetição de posição.")).toBeInTheDocument();
});

test("quem não tem a vez não vê o botão mesmo que o evento traga a indicação", async () => {
  const ws = await abrirOnline({ ply: 6, to_move_seat: 1 });
  act(() => ws.receive({ type: "move_applied", seq: 7, payload: {
    match_id: "m1", ply: 7, seat: 1, move: "f3g1", next_seat: 2, legal_moves: [],
    state: { schema_version: 1, fen: START, moves: [] }, can_claim_draw: true } }));
  expect(screen.queryByRole("button", BUTTON)).toBeNull();
});

test("o erro do servidor ao reivindicar é mostrado ao jogador", async () => {
  const ws = await abrirOnline({ can_claim_draw: true });
  await userEvent.click(screen.getByRole("button", BUTTON));
  const enviado = ws.sentMessages().find((m) => m.type === "claim_draw")!;
  act(() => ws.receive({ type: "error", reply_to: enviado.id, payload: {
    code: "draw_not_claimable", message: "Ainda não cabe reivindicar empate", status: 409 } }));
  expect(await screen.findByText("Ainda não cabe reivindicar empate")).toBeInTheDocument();
});

test("textos de fim por reivindicação não dependem de cor", () => {
  const base = { game_id: "chess", status: "finished", result: "draw", to_move_seat: null,
    seats: chess().seats } as const;
  expect(onlineStatusText({ ...base, end_reason: "repetition" })).toBe("Empate por repetição de posição.");
  expect(onlineStatusText({ ...base, end_reason: "fifty_move" })).toBe("Empate pela regra dos 50 lances.");
});

test("partida contra a IA ou local: o botão usa o REST e mostra o empate", async () => {
  const fn = mockApi({
    "POST /matches": () => ({ status: 201, body: chess({ mode: "local", can_claim_draw: true,
      seats: [{ seat: 1, is_ai: false, is_you: true }, { seat: 2, is_ai: false, is_you: true }] }) }),
    "POST /matches/m1/claim-draw": () => ({ body: chess({ mode: "local", status: "finished",
      result: "draw", end_reason: "repetition", to_move_seat: null, legal_moves: [],
      can_claim_draw: false }) }),
  });
  render(<GamePage me={me} />);
  await userEvent.click(screen.getByRole("button", { name: "Começar" }));
  await userEvent.click(await screen.findByRole("button", BUTTON));
  expect(await screen.findByText("Empate (repetição de posição).")).toBeInTheDocument();
  expect(screen.queryByRole("button", BUTTON)).toBeNull();
  expect(fn.mock.calls.some(([u, i]) => String(u).endsWith("/matches/m1/claim-draw") && i?.method === "POST")).toBe(true);
});

test("partida local sem indicação do servidor não mostra o botão", async () => {
  mockApi({ "POST /matches": () => ({ status: 201, body: chess({ mode: "local" }) }) });
  render(<GamePage me={me} />);
  await userEvent.click(screen.getByRole("button", { name: "Começar" }));
  await screen.findByRole("button", { name: "Desistir" });
  expect(screen.queryByRole("button", BUTTON)).toBeNull();
});
