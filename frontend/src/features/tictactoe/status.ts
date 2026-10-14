import type { MatchView } from "../../services/types";

/** Texto de estado do jogo, sempre sem depender de cor (princípio 1 do doc 10). */
export function statusText(m: Pick<MatchView, "game_id" | "status" | "result" | "mode" | "to_move_seat" | "seats" | "end_reason">): string {
  const chess = m.game_id === "chess";
  const colors = chess || m.game_id === "checkers";
  const [first, second] = colors ? ["Brancas", "Pretas"] : ["X", "O"];
  const verb = colors ? "venceram" : "venceu";
  const name = (seat: number) => (seat === 1 ? first : second);
  const reasons: Record<string, string> = {
    repetition: " (tripla repetição)", kings_only: " (limite de lances só com damas)",
  };
  const chessReasons: Record<string, string> = {
    stalemate: " (afogamento)", repetition: " (repetição quíntupla)", fifty_move: " (regra dos 75 lances)",
  };
  if (m.status === "aborted") return "Partida encerrada por um erro. Comece outra.";
  if (m.status === "finished") {
    if (m.result === "draw") return `Empate${(chess ? chessReasons : reasons)[m.end_reason ?? ""] ?? ""}.`;
    const winnerSeat = m.result === "p1_win" ? 1 : 2;
    const symbol = name(winnerSeat);
    const yours = m.seats.find((s) => s.seat === winnerSeat)?.is_you ?? false;
    if (m.end_reason === "resign") {
      return m.mode === "local" ? `${symbol} ${verb}: o outro jogador desistiu.` : yours ? "Você venceu: o oponente desistiu." : "Você desistiu. A IA venceu.";
    }
    const mate = chess ? "Xeque-mate. " : "";
    if (m.mode === "local") return `${mate}${symbol} ${verb}.`;
    return mate + (yours ? `Você venceu como ${symbol}!` : `A IA venceu como ${symbol}.`);
  }
  const symbol = name(m.to_move_seat ?? 1);
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
