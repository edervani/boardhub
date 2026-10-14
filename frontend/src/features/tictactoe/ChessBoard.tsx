import { useRef, useState, type KeyboardEvent } from "react";

interface ChessBoardProps {
  fen: string;
  playable: string[]; // lances UCI legais, ex.: "e2e4", "e7e8q"
  flipped: boolean; // true quando o usuário joga com as pretas (assento 2)
  onPlay: (move: string) => void;
}

const EMPTY_BOARD = (): string[] => Array<string>(64).fill("");

/** Interpreta o campo de posição do FEN. Índice 0 = a8, 63 = h1; "" = vazia. FEN inválido → tabuleiro vazio. */
export function fenToSquares(fen: string): string[] {
  const ranks = (fen.split(" ")[0] ?? "").split("/");
  if (ranks.length !== 8) return EMPTY_BOARD();
  const out: string[] = [];
  for (const rank of ranks) {
    let n = 0;
    for (const ch of rank) {
      if (/[1-8]/.test(ch)) {
        for (let k = 0; k < Number(ch); k++) out.push("");
        n += Number(ch);
      } else if (/[pnbrqkPNBRQK]/.test(ch)) {
        out.push(ch);
        n += 1;
      } else return EMPTY_BOARD();
    }
    if (n !== 8) return EMPTY_BOARD();
  }
  return out;
}

const NAMES: Record<string, string> = {
  p: "peão", n: "cavalo", b: "bispo", r: "torre", q: "dama", k: "rei",
};
const GLYPHS: Record<string, string> = {
  P: "♙", N: "♘", B: "♗", R: "♖", Q: "♕", K: "♔", p: "♟", n: "♞", b: "♝", r: "♜", q: "♛", k: "♚",
};
const PROMO: { code: string; name: string }[] = [
  { code: "q", name: "Dama" }, { code: "r", name: "Torre" }, { code: "b", name: "Bispo" }, { code: "n", name: "Cavalo" },
];

export const squareName = (idx: number) => `${"abcdefgh"[idx % 8]}${8 - Math.floor(idx / 8)}`;

export function pieceName(p: string): string {
  if (!p) return "vazia";
  const name = NAMES[p.toLowerCase()] ?? "peça";
  const fem = name === "torre" || name === "dama" || name === "peça";
  const white = p === p.toUpperCase();
  return `${name} ${white ? (fem ? "branca" : "branco") : (fem ? "preta" : "preto")}`;
}

export function ChessBoard({ fen, playable, flipped, onPlay }: ChessBoardProps) {
  const [from, setFrom] = useState<string | null>(null);
  const [promo, setPromo] = useState<{ from: string; to: string } | null>(null);
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const squares = fenToSquares(fen);

  const origins = new Set(playable.map((m) => m.slice(0, 2)));
  const targets = new Set(from ? playable.filter((m) => m.startsWith(from)).map((m) => m.slice(2, 4)) : []);

  function click(name: string) {
    if (promo) return;
    if (from === name) { setFrom(null); return; }
    if (from && targets.has(name)) {
      const matching = playable.filter((m) => m.startsWith(from + name));
      if (matching.length > 1) { setPromo({ from, to: name }); return; }
      setFrom(null);
      onPlay(matching[0] as string);
      return;
    }
    setFrom(origins.has(name) ? name : null);
  }

  function choose(code: string) {
    if (!promo) return;
    const move = promo.from + promo.to + code;
    setPromo(null); setFrom(null);
    onPlay(move);
  }

  const order = flipped ? [7, 6, 5, 4, 3, 2, 1, 0] : [0, 1, 2, 3, 4, 5, 6, 7];

  function onKeyDown(e: KeyboardEvent<HTMLButtonElement>, row: number, col: number) {
    // Setas seguem a direção visual (o tabuleiro é invertido para as pretas).
    const d: Record<string, [number, number]> = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] };
    const step = d[e.key];
    if (!step) return;
    const vr = order.indexOf(row) + step[0];
    const vc = order.indexOf(col) + step[1];
    if (vr < 0 || vr > 7 || vc < 0 || vc > 7) return;
    e.preventDefault();
    refs.current[squareName((order[vr] as number) * 8 + (order[vc] as number))]?.focus();
  }

  return (
    <div>
      <div role="group" aria-label="Tabuleiro de xadrez"
        style={{ display: "grid", gridTemplateColumns: "repeat(8, minmax(2.5rem, 1fr))", maxWidth: "32rem" }}>
        {order.flatMap((row) => order.map((col) => {
          const idx = row * 8 + col;
          const name = squareName(idx);
          const piece = squares[idx] ?? "";
          const selected = from === name;
          const canClick = from === null ? origins.has(name) : (targets.has(name) || origins.has(name));
          const state = selected ? ", selecionada" : canClick ? ", jogável" : "";
          return (
            <button key={name} ref={(el) => { refs.current[name] = el; }} type="button"
              aria-label={`${name}: ${pieceName(piece)}${state}`}
              aria-disabled={!canClick} aria-pressed={selected}
              onKeyDown={(e) => onKeyDown(e, row, col)}
              onClick={() => { if (canClick) click(name); }}
              style={{ aspectRatio: "1", fontSize: "1.8rem", padding: 0, borderRadius: 0,
                color: "#000", background: (row + col) % 2 === 1 ? "#b8b8b8" : "#f4f4f4",
                outline: selected ? "3px solid #000" : undefined, outlineOffset: "-3px",
                border: canClick ? "2px dashed #000" : "1px solid #888" }}>
              <span aria-hidden="true">{GLYPHS[piece] ?? ""}</span>
              <span aria-hidden="true" style={{ display: "block", fontSize: ".6rem" }}>{name}</span>
            </button>
          );
        }))}
      </div>
      {promo && (
        <div role="dialog" aria-label="Escolha a peça da promoção">
          <p>Promover o peão para:</p>
          {PROMO.filter((p) => playable.includes(promo.from + promo.to + p.code)).map((p) => (
            <button key={p.code} type="button" onClick={() => choose(p.code)}>{p.name}</button>
          ))}{" "}
          <button type="button" className="secondary" onClick={() => setPromo(null)}>Cancelar</button>
        </div>
      )}
    </div>
  );
}
