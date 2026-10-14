import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { CheckersBoard, squarePos } from "../src/features/tictactoe/CheckersBoard";
import { statusText } from "../src/features/tictactoe/status";

const initial = [...Array(12).fill("b"), ...Array(8).fill("."), ...Array(12).fill("w")];

test("geometria: casa 1 no topo e casa 32 na base", () => {
  expect(squarePos(1)).toEqual({ row: 0, col: 1 });
  expect(squarePos(4)).toEqual({ row: 0, col: 7 });
  expect(squarePos(32)).toEqual({ row: 7, col: 6 });
});

test("lance simples: clica na origem e no destino", async () => {
  const onPlay = vi.fn();
  render(<CheckersBoard squares={initial} playable={["21-17", "22-17"]} flipped={false} onPlay={onPlay} />);
  await userEvent.click(screen.getByRole("button", { name: /^Casa 21:/ }));
  expect(screen.getByRole("button", { name: /^Casa 21:.*selecionada/ })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /^Casa 17:/ }));
  expect(onPlay).toHaveBeenCalledWith("21-17");
});

test("captura em cadeia exige clicar em cada casa do caminho", async () => {
  const onPlay = vi.fn();
  render(<CheckersBoard squares={initial} playable={["9x18x27"]} flipped={false} onPlay={onPlay} />);
  await userEvent.click(screen.getByRole("button", { name: /^Casa 9:/ }));
  await userEvent.click(screen.getByRole("button", { name: /^Casa 18:/ }));
  expect(onPlay).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: /^Casa 27:/ }));
  expect(onPlay).toHaveBeenCalledWith("9x18x27");
});

test("casa sem lance legal não dispara jogada", async () => {
  const onPlay = vi.fn();
  render(<CheckersBoard squares={initial} playable={["21-17"]} flipped={false} onPlay={onPlay} />);
  await userEvent.click(screen.getByRole("button", { name: /^Casa 1:/ }));
  expect(onPlay).not.toHaveBeenCalled();
});

test("texto de estado de damas usa cores por extenso", () => {
  const base = { game_id: "checkers", status: "finished", mode: "local", to_move_seat: null,
    seats: [], end_reason: "normal", result: "p1_win" as const };
  expect(statusText(base)).toBe("Brancas venceram.");
  expect(statusText({ ...base, result: "draw", end_reason: "repetition" })).toBe("Empate (tripla repetição).");
});
