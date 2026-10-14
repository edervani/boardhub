import { useRef, type KeyboardEvent } from "react";

interface BoardProps {
  board: string; // 9 caracteres: X, O ou _
  playable: string[]; // índices jogáveis agora, em texto
  onPlay: (index: number) => void;
}

const cellLabel = (i: number, c: string) =>
  `Linha ${Math.floor(i / 3) + 1}, coluna ${(i % 3) + 1}: ${c === "_" ? "vazia" : c}`;

export function Board({ board, playable, onPlay }: BoardProps) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKeyDown(e: KeyboardEvent<HTMLButtonElement>, i: number) {
    const delta: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -3, ArrowDown: 3 };
    const step = delta[e.key];
    if (step === undefined) return;
    const col = i % 3;
    if ((e.key === "ArrowLeft" && col === 0) || (e.key === "ArrowRight" && col === 2)) return;
    const next = i + step;
    if (next < 0 || next > 8) return;
    e.preventDefault();
    refs.current[next]?.focus();
  }

  return (
    <div role="group" aria-label="Tabuleiro do jogo da velha"
      style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(3.5rem, 1fr))", gap: ".5rem", maxWidth: "20rem" }}>
      {Array.from(board).map((c, i) => {
        const canPlay = playable.includes(String(i));
        return (
          <button key={i} ref={(el) => { refs.current[i] = el; }} type="button"
            aria-label={cellLabel(i, c)} aria-disabled={!canPlay}
            onKeyDown={(e) => onKeyDown(e, i)}
            onClick={() => { if (canPlay) onPlay(i); }}
            style={{ aspectRatio: "1", fontSize: "2rem", fontWeight: 700, opacity: canPlay || c !== "_" ? 1 : 0.6 }}>
            {c === "_" ? "" : c}
          </button>
        );
      })}
    </div>
  );
}
