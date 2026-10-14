import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { ChessBoard, fenToSquares } from "../src/features/tictactoe/ChessBoard";
import { statusText } from "../src/features/tictactoe/status";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
const PROMO_FEN = "8/4P3/8/8/8/8/8/k6K w - - 0 1";

test("fenToSquares: posição inicial", () => {
  const s = fenToSquares(START);
  expect(s).toHaveLength(64);
  expect(s[0]).toBe("r");
  expect(s[4]).toBe("k");
  expect(s[8]).toBe("p");
  expect(s[16]).toBe("");
  expect(s[52]).toBe("P"); // e2
  expect(s[60]).toBe("K"); // e1
  expect(s[63]).toBe("R");
});

test("fenToSquares: FEN inválido vira tabuleiro vazio", () => {
  expect(fenToSquares("").every((c) => c === "")).toBe(true);
  expect(fenToSquares("8/8/8 w").every((c) => c === "")).toBe(true);
  expect(fenToSquares("9/8/8/8/8/8/8/8").every((c) => c === "")).toBe(true);
});

test("lance simples: origem e depois destino", async () => {
  const onPlay = vi.fn();
  render(<ChessBoard fen={START} playable={["e2e4", "e2e3"]} flipped={false} onPlay={onPlay} />);
  await userEvent.click(screen.getByRole("button", { name: "e2: peão branco, jogável" }));
  expect(screen.getByRole("button", { name: "e2: peão branco, selecionada" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "e4: vazia, jogável" }));
  expect(onPlay).toHaveBeenCalledWith("e2e4");
});

test("casa não jogável não dispara nem seleciona", async () => {
  const onPlay = vi.fn();
  render(<ChessBoard fen={START} playable={["e2e4"]} flipped={false} onPlay={onPlay} />);
  await userEvent.click(screen.getByRole("button", { name: "a2: peão branco" }));
  await userEvent.click(screen.getByRole("button", { name: "e2: peão branco, jogável" }));
  await userEvent.click(screen.getByRole("button", { name: "h5: vazia" }));
  expect(onPlay).not.toHaveBeenCalled();
});

test("promoção abre seletor e envia o sufixo escolhido", async () => {
  const onPlay = vi.fn();
  render(<ChessBoard fen={PROMO_FEN} playable={["e7e8q", "e7e8r", "e7e8b", "e7e8n"]} flipped={false} onPlay={onPlay} />);
  await userEvent.click(screen.getByRole("button", { name: /^e7:/ }));
  await userEvent.click(screen.getByRole("button", { name: /^e8:/ }));
  expect(onPlay).not.toHaveBeenCalled();
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Cavalo" }));
  expect(onPlay).toHaveBeenCalledWith("e7e8n");
  expect(screen.queryByRole("dialog")).toBeNull();
});

test("tabuleiro invertido para as pretas começa em h1", () => {
  const { container, unmount } = render(<ChessBoard fen={START} playable={[]} flipped={false} onPlay={() => {}} />);
  const labels = (c: HTMLElement) => Array.from(c.querySelectorAll("button")).map((b) => b.getAttribute("aria-label") ?? "");
  expect(labels(container)[0]).toMatch(/^a8:/);
  unmount();
  const r = render(<ChessBoard fen={START} playable={[]} flipped onPlay={() => {}} />);
  expect(labels(r.container)[0]).toMatch(/^h1:/);
  expect(labels(r.container)[63]).toMatch(/^a8:/);
});

test("setas do teclado seguem a direção visual", async () => {
  render(<ChessBoard fen={START} playable={[]} flipped onPlay={() => {}} />);
  screen.getByRole("button", { name: /^h1:/ }).focus();
  await userEvent.keyboard("{ArrowRight}");
  expect(screen.getByRole("button", { name: /^g1:/ })).toHaveFocus();
  await userEvent.keyboard("{ArrowDown}");
  expect(screen.getByRole("button", { name: /^g2:/ })).toHaveFocus();
});

test("textos de status do xadrez", () => {
  const base = { game_id: "chess", status: "finished", mode: "local", to_move_seat: null,
    seats: [], end_reason: "normal", result: "p1_win" as const };
  expect(statusText(base)).toBe("Xeque-mate. Brancas venceram.");
  expect(statusText({ ...base, result: "p2_win", end_reason: "resign" })).toBe("Pretas venceram: o outro jogador desistiu.");
  expect(statusText({ ...base, result: "draw", end_reason: "stalemate" })).toBe("Empate (afogamento).");
  expect(statusText({ ...base, result: "draw", end_reason: "repetition" })).toBe("Empate (repetição de posição).");
  expect(statusText({ ...base, result: "draw", end_reason: "fifty_move" })).toBe("Empate (regra dos 50/75 lances).");
  expect(statusText({ ...base, status: "in_progress", result: null, end_reason: null, to_move_seat: 2 })).toBe("Vez de Pretas.");
});
