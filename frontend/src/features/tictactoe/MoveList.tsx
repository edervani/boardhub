import { useEffect, useState } from "react";
import { api } from "../../services/api";
import type { MatchView, MoveNotation, Preferences } from "../../services/types";

const PT_LETTERS: Record<string, string> = { K: "R", Q: "D", R: "T", N: "C" };

/** SAN internacional → algébrica com as letras das peças em português (R, D, T, B, C). */
export const toPortuguese = (san: string): string => san.replace(/[KQRN]/g, (c) => PT_LETTERS[c] ?? c);

/**
 * Lances do xadrez no texto da notação escolhida (RF-007). Só exibição: o servidor continua
 * falando UCI; a SAN vem pronta do servidor (`san_moves`), o cliente não tem motor de regras.
 */
export function chessMoveTexts(match: Pick<MatchView, "state" | "san_moves">, notation: MoveNotation): string[] {
  if (notation === "uci") return match.state.moves ?? [];
  const san = match.san_moves ?? [];
  return notation === "san" ? san : san.map(toPortuguese);
}

function Inner({ match }: { match: MatchView }) {
  const [notation, setNotation] = useState<MoveNotation>("algebraic_pt");

  useEffect(() => {
    let live = true;
    api<Preferences>("GET", "/me/preferences")
      .then((p) => { if (live && p.move_notation) setNotation(p.move_notation); })
      .catch(() => undefined); // sem preferência salva, vale o padrão
    return () => { live = false; };
  }, []);

  const texts = chessMoveTexts(match, notation);
  const rows: string[][] = [];
  for (let i = 0; i < texts.length; i += 2) rows.push(texts.slice(i, i + 2));
  if (rows.length === 0) return null;
  return (
    <section aria-labelledby="moves-title">
      <h3 id="moves-title">Lances</h3>
      <ol aria-label="Lances da partida (brancas e pretas)">
        {rows.map((pair, i) => <li key={i}>{pair.join(" ")}</li>)}
      </ol>
    </section>
  );
}

/** Lista de lances do xadrez; some enquanto não houver lances. */
export function MoveList({ match }: { match: MatchView }) {
  if (match.game_id !== "chess" || (match.state.moves ?? []).length === 0) return null;
  return <Inner match={match} />;
}
