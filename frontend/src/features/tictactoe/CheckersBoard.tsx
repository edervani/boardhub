import { useState } from "react";

interface CheckersBoardProps {
  squares: string[]; // 32 casas PDN: w/b pedras, W/B damas, "." vazia
  playable: string[]; // lances legais completos, ex.: "21-17" ou "9x18x27"
  flipped: boolean; // true quando o usuário joga com as pretas (assento 2)
  onPlay: (move: string) => void;
}

const parts = (move: string) => move.split(/[-x]/).map(Number);

/** Casa PDN (1..32) → linha/coluna, igual à geometria do motor (casa 1 no topo, coluna 1). */
export function squarePos(n: number): { row: number; col: number } {
  const i = n - 1;
  const rowTop = Math.floor(i / 4);
  const r = 7 - rowTop;
  return { row: rowTop, col: 2 * (i % 4) + (r % 2) };
}

const PIECE_NAME: Record<string, string> = {
  w: "pedra branca", W: "dama branca", b: "pedra preta", B: "dama preta", ".": "vazia",
};
const GLYPH: Record<string, string> = { w: "○", W: "♕", b: "●", B: "♛", ".": "" };

export function CheckersBoard({ squares, playable, flipped, onPlay }: CheckersBoardProps) {
  const [path, setPath] = useState<number[]>([]);
  const candidates = playable.map(parts).filter((p) => path.every((s, i) => p[i] === s));
  const nextSquares = new Set(candidates.filter((p) => p.length > path.length).map((p) => p[path.length]));

  function click(n: number) {
    const next = [...path, n];
    const matching = playable.filter((m) => {
      const p = parts(m);
      return next.every((s, i) => p[i] === s);
    });
    if (matching.length === 0) { setPath(playable.some((m) => parts(m)[0] === n) ? [n] : []); return; }
    const full = matching.find((m) => parts(m).length === next.length);
    if (full) { setPath([]); onPlay(full); } else setPath(next);
  }

  const cells: { row: number; col: number; n: number }[] = [];
  for (let n = 1; n <= 32; n++) cells.push({ ...squarePos(n), n });
  const byPos = new Map(cells.map((c) => [`${c.row},${c.col}`, c.n]));
  const rows = [...Array(8).keys()];
  const order = flipped ? [...rows].reverse() : rows;
  const colOrder = flipped ? [...rows].reverse() : rows;

  return (
    <div role="group" aria-label="Tabuleiro de damas"
      style={{ display: "grid", gridTemplateColumns: "repeat(8, minmax(2.5rem, 1fr))", maxWidth: "30rem" }}>
      {order.flatMap((row) => colOrder.map((col) => {
        const n = byPos.get(`${row},${col}`);
        if (n === undefined) return <div key={`${row}-${col}`} aria-hidden="true" style={{ aspectRatio: "1" }} />;
        const piece = squares[n - 1] ?? ".";
        const selected = path.includes(n);
        const canClick = path.length === 0
          ? playable.some((m) => parts(m)[0] === n)
          : nextSquares.has(n) || playable.some((m) => parts(m)[0] === n);
        const label = `Casa ${n}: ${PIECE_NAME[piece]}${selected ? ", selecionada" : ""}${
          canClick && !selected ? ", jogável" : ""}`;
        return (
          <button key={n} type="button" aria-label={label} aria-disabled={!canClick}
            aria-pressed={selected}
            onClick={() => { if (canClick) click(n); }}
            style={{ aspectRatio: "1", fontSize: "1.6rem", padding: 0, borderRadius: 0,
              outline: selected ? "3px solid currentColor" : undefined,
              border: canClick ? "2px dashed currentColor" : "1px solid #888",
              opacity: canClick || piece !== "." ? 1 : 0.7 }}>
            {GLYPH[piece]}
            <span style={{ display: "block", fontSize: ".6rem" }} aria-hidden="true">{n}</span>
          </button>
        );
      }))}
    </div>
  );
}
