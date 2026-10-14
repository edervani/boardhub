import type { MatchView } from "../../services/types";

export const GAME_TITLES: Record<string, string> = {
  tictactoe: "Jogo da velha",
  checkers: "Damas",
  chess: "Xadrez",
};

/** Jogos com empate por acordo (RF-015). */
export const DRAW_AGREEMENT_GAMES: ReadonlySet<string> = new Set(["checkers", "chess"]);

const SEAT_NAMES: Record<string, [string, string]> = {
  tictactoe: ["X", "O"],
  checkers: ["Brancas", "Pretas"],
  chess: ["Brancas", "Pretas"],
};

export function seatName(game: string, seat: number): string {
  const names = SEAT_NAMES[game] ?? ["1º jogador", "2º jogador"];
  return seat === 1 ? names[0] : names[1];
}

export function mySeat(match: Pick<MatchView, "seats">): number | null {
  return match.seats.find((s) => s.is_you)?.seat ?? null;
}

/** Texto de estado da partida online, sempre sem depender de cor (doc 10 §1). */
export function onlineStatusText(
  m: Pick<MatchView, "game_id" | "status" | "result" | "end_reason" | "to_move_seat" | "seats">,
): string {
  const mine = mySeat(m);
  if (m.status === "waiting") return "Aguardando o oponente entrar com o código.";
  if (m.status === "aborted") return "Sala cancelada ou expirada.";
  if (m.status === "annulled") return "Partida anulada: terminou cedo demais e não altera o rating.";
  if (m.status === "finished") {
    if (m.result === "draw") {
      const reasons: Record<string, string> = {
        agreement: "Empate por acordo.",
        repetition: "Empate por repetição de posição.",
        fifty_move: "Empate pela regra dos 50 lances.",
      };
      return reasons[m.end_reason ?? ""] ?? "Empate.";
    }
    const winner = m.result === "p1_win" ? 1 : 2;
    const yours = winner === mine;
    if (m.end_reason === "resign") {
      return yours ? "Você venceu: o adversário desistiu." : "Você perdeu: você desistiu.";
    }
    if (m.end_reason === "abandon") {
      return yours ? "Você venceu: o adversário abandonou a partida." : "Você perdeu por abandono.";
    }
    const name = seatName(m.game_id, winner);
    return yours ? `Você venceu como ${name}!` : `Você perdeu. O adversário venceu como ${name}.`;
  }
  const toMove = m.to_move_seat ?? 1;
  return toMove === mine
    ? `Sua vez (${seatName(m.game_id, toMove)}).`
    : `Vez do adversário (${seatName(m.game_id, toMove)}).`;
}

/** Variação de rating do próprio jogador ao fim de uma partida ranqueada (RF-019). */
export function ratingChangeText(
  m: Pick<MatchView, "seats" | "rating_changes">,
): string | null {
  const mine = mySeat(m);
  const c = (m.rating_changes ?? []).find((r) => r.seat === mine);
  if (!c) return null;
  const delta = c.after - c.before;
  const signed = delta > 0 ? `+${delta}` : String(delta);
  return `Seu rating: ${c.before} → ${c.after} (${signed}).`;
}
