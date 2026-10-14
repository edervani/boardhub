import type { MatchView } from "../../services/types";

/** Texto de estado do jogo, sempre sem depender de cor (princípio 1 do doc 10). */
export function statusText(m: Pick<MatchView, "status" | "result" | "mode" | "to_move_seat" | "seats" | "end_reason">): string {
  if (m.status === "aborted") return "Partida encerrada por um erro. Comece outra.";
  if (m.status === "finished") {
    if (m.result === "draw") return "Empate.";
    const winnerSeat = m.result === "p1_win" ? 1 : 2;
    const symbol = winnerSeat === 1 ? "X" : "O";
    const yours = m.seats.find((s) => s.seat === winnerSeat)?.is_you ?? false;
    if (m.end_reason === "resign") {
      return m.mode === "local" ? `${symbol} venceu: o outro jogador desistiu.` : yours ? "Você venceu: o oponente desistiu." : "Você desistiu. A IA venceu.";
    }
    if (m.mode === "local") return `${symbol} venceu.`;
    return yours ? `Você venceu como ${symbol}!` : `A IA venceu como ${symbol}.`;
  }
  const symbol = m.to_move_seat === 1 ? "X" : "O";
  if (m.mode === "local") return `Vez de ${symbol}.`;
  const mine = m.seats.find((s) => s.seat === m.to_move_seat)?.is_you ?? false;
  return mine ? `Sua vez (${symbol}).` : "A IA está pensando…";
}

export const LEVEL_LABELS: Record<number, string> = {
  1: "1 – Muito fácil",
  2: "2 – Fácil",
  3: "3 – Médio",
  4: "4 – Difícil",
  5: "5 – Perfeito",
};
