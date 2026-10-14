import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { Board } from "../src/features/tictactoe/Board";
import { GamePage } from "../src/features/tictactoe/GamePage";
import { History } from "../src/features/tictactoe/History";
import { statusText } from "../src/features/tictactoe/status";
import type { MatchView, Me } from "../src/services/types";
import { bodyOf, cellButtons, mockApi } from "./helpers";

afterEach(() => { vi.unstubAllGlobals(); });

const me: Me = { id: "u1", email: "a@example.test", display_name: "jogador_teste_01",
  email_verified: true, age_band: "18_plus", role: "user", supervised: false };

const match = (over: Partial<MatchView> = {}): MatchView => ({
  id: "m1", game_id: "tictactoe", mode: "ai", status: "in_progress", ply: 0,
  state: { schema_version: 1, board: "_________", to_move: "X" }, to_move_seat: 1,
  legal_moves: ["0", "1", "2", "3", "4", "5", "6", "7", "8"], result: null, end_reason: null,
  ai_level: 3, created_at: "2026-10-13T00:00:00Z", finished_at: null,
  seats: [{ seat: 1, is_ai: false, is_you: true }, { seat: 2, is_ai: true, is_you: false }], ...over,
});

test("textos de estado não dependem de cor e cobrem todos os desfechos", () => {
  expect(statusText(match())).toBe("Sua vez (X).");
  expect(statusText(match({ to_move_seat: 2 }))).toBe("A IA está pensando…");
  expect(statusText(match({ status: "finished", result: "p1_win" }))).toBe("Você venceu como X!");
  expect(statusText(match({ status: "finished", result: "p2_win" }))).toBe("A IA venceu como O.");
  expect(statusText(match({ status: "finished", result: "draw" }))).toBe("Empate.");
  expect(statusText(match({ status: "finished", result: "p2_win", end_reason: "resign" }))).toBe("Você desistiu. A IA venceu.");
  expect(statusText(match({ mode: "local", to_move_seat: 2 }))).toBe("Vez de O.");
  expect(statusText(match({ status: "aborted" }))).toContain("erro");
});

test("tabuleiro: 9 casas com rótulo acessível, só joga em casa livre", async () => {
  const onPlay = vi.fn();
  const { container } = render(<Board board="X________" playable={["1", "2"]} onPlay={onPlay} />);
  const cells = cellButtons(container);
  expect(cells).toHaveLength(9);
  expect(cells[0]).toHaveAccessibleName("Linha 1, coluna 1: X");
  expect(cells[4]).toHaveAccessibleName("Linha 2, coluna 2: vazia");
  await userEvent.click(cells[0]!);
  await userEvent.click(cells[4]!);
  expect(onPlay).not.toHaveBeenCalled();
  await userEvent.click(cells[1]!);
  expect(onPlay).toHaveBeenCalledWith(1);
});

test("tabuleiro: setas movem o foco e não saem das bordas", () => {
  const { container } = render(<Board board="_________" playable={[]} onPlay={() => {}} />);
  const cells = cellButtons(container);
  cells[0]!.focus();
  fireEvent.keyDown(cells[0]!, { key: "ArrowRight" });
  expect(cells[1]).toHaveFocus();
  fireEvent.keyDown(cells[1]!, { key: "ArrowDown" });
  expect(cells[4]).toHaveFocus();
  fireEvent.keyDown(cells[4]!, { key: "ArrowLeft" });
  fireEvent.keyDown(cells[3]!, { key: "ArrowLeft" });
  expect(cells[3]).toHaveFocus();
  fireEvent.keyDown(cells[3]!, { key: "ArrowUp" });
  fireEvent.keyDown(cells[0]!, { key: "ArrowUp" });
  expect(cells[0]).toHaveFocus();
});

test("visitante joga localmente e cada lance é validado pelo servidor", async () => {
  const fn = mockApi({
    "POST /engines/tictactoe/apply": (init) => ({ body: {
      state: { schema_version: 1, board: "____X____", to_move: "O" },
      outcome: null, legal_moves: ["0", "1", "2", "3", "5", "6", "7", "8"], echo: bodyOf(init).move } }),
  });
  const { container } = render(<GamePage me={null} />);
  expect(screen.getByRole("status")).toHaveTextContent("Vez de X.");
  await userEvent.click(cellButtons(container)[4]!);
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Vez de O."));
  expect(cellButtons(container)[4]).toHaveAccessibleName("Linha 2, coluna 2: X");
  const [, init] = fn.mock.calls[0] as [string, RequestInit];
  expect(bodyOf(init).move).toBe("4");
});

test("usuário inicia partida contra a IA e envia lance com expected_ply e client_move_id", async () => {
  vi.stubGlobal("crypto", { randomUUID: () => "11111111-1111-4111-8111-111111111111" });
  const fn = mockApi({
    "POST /matches": () => ({ status: 201, body: match() }),
    "POST /matches/m1/moves": () => ({ body: match({ ply: 2,
      state: { schema_version: 1, board: "O___X____", to_move: "X" },
      legal_moves: ["1", "2", "3", "5", "6", "7", "8"] }) }),
  });
  const { container } = render(<GamePage me={me} />);
  await userEvent.selectOptions(screen.getByLabelText("Nível da IA"), "5");
  await userEvent.click(screen.getByRole("button", { name: "Começar" }));
  const [, create] = fn.mock.calls[0] as [string, RequestInit];
  expect(bodyOf(create)).toEqual({ game_id: "tictactoe", mode: "ai", ai_level: 5, preferred_seat: 1 });
  await screen.findByText("Sua vez (X).");
  await userEvent.click(cellButtons(container)[4]!);
  await waitFor(() => expect(cellButtons(container)[0]).toHaveAccessibleName("Linha 1, coluna 1: O"));
  const [, move] = fn.mock.calls[1] as [string, RequestInit];
  expect(bodyOf(move)).toEqual({ expected_ply: 0, move: "4", client_move_id: "11111111-1111-4111-8111-111111111111" });
});

test("estado desatualizado (409) mostra o erro e ressincroniza com o servidor", async () => {
  const fn = mockApi({
    "POST /matches": () => ({ status: 201, body: match() }),
    "POST /matches/m1/moves": () => ({ status: 409, body: { type: "stale_state", title: "Estado desatualizado" } }),
    "GET /matches/m1": () => ({ body: match({ ply: 2, state: { schema_version: 1, board: "O___X____", to_move: "X" } }) }),
  });
  const { container } = render(<GamePage me={me} />);
  await userEvent.click(screen.getByRole("button", { name: "Começar" }));
  await screen.findByText("Sua vez (X).");
  await userEvent.click(cellButtons(container)[8]!);
  expect(await screen.findByRole("alert")).toHaveTextContent("Estado desatualizado");
  await waitFor(() => expect(cellButtons(container)[4]).toHaveAccessibleName("Linha 2, coluna 2: X"));
  expect(fn.mock.calls.some(([u]) => String(u).endsWith("/matches/m1"))).toBe(true);
});

test("desistir pede ao servidor e mostra o resultado", async () => {
  mockApi({
    "POST /matches": () => ({ status: 201, body: match() }),
    "POST /matches/m1/resign": () => ({ body: match({ status: "finished", result: "p2_win", end_reason: "resign", to_move_seat: null, legal_moves: [] }) }),
  });
  render(<GamePage me={me} />);
  await userEvent.click(screen.getByRole("button", { name: "Começar" }));
  await userEvent.click(await screen.findByRole("button", { name: "Desistir" }));
  expect(await screen.findByText("Você desistiu. A IA venceu.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Desistir" })).not.toBeInTheDocument();
});

test("histórico lista partidas e carrega a próxima página", async () => {
  const item = (id: string, result: string) => ({ id, game_id: "tictactoe", mode: "ai", status: "finished",
    result, ply: 7, created_at: "2026-10-13T12:00:00Z", finished_at: "2026-10-13T12:05:00Z" });
  const fn = mockApi({
    "GET /me/matches?limit=20": () => ({ body: { items: [item("a", "draw")], next_cursor: "abc" } }),
    "GET /me/matches?limit=20&cursor=abc": () => ({ body: { items: [item("b", "p1_win")], next_cursor: null } }),
  });
  render(<History />);
  expect(await screen.findByText(/Empate/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Carregar mais" }));
  expect(await screen.findByText(/Vitória do 1º jogador/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Carregar mais" })).not.toBeInTheDocument();
  expect(fn).toHaveBeenCalledTimes(2);
});
