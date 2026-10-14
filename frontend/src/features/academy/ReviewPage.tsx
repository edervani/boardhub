import { useEffect, useState } from "react";
import { api, errorMessage } from "../../services/api";
import { PositionBoard } from "./PositionBoard";
import type { Analysis } from "./types";

const SEVERITY: Record<string, string> = {
  inaccuracy: "Imprecisão", mistake: "Erro", blunder: "Erro grave",
};

/** Revisão do Mentor: lances críticos da partida, com a explicação do servidor. */
export function ReviewPage({ matchId, onBack }: { matchId: string; onBack: () => void }) {
  const [a, setA] = useState<Analysis | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Analysis>("GET", `/matches/${matchId}/analysis`)
      .then(setA).catch((e: unknown) => setError(errorMessage(e)));
  }, [matchId]);

  return (
    <section aria-labelledby="rv-title">
      <button type="button" className="secondary" onClick={onBack}>Voltar ao histórico</button>
      <h2 id="rv-title">Revisão da partida</h2>
      {error && <p role="alert">{error}</p>}
      {!a && !error && <p role="status">Analisando a partida…</p>}
      {a && (
        <>
          <p>
            Lances analisados: {a.analyzed_moves}. Imprecisões: {a.counts.inaccuracy ?? 0}, erros:{" "}
            {a.counts.mistake ?? 0}, erros graves: {a.counts.blunder ?? 0}.
          </p>
          {a.truncated && <p>A análise foi limitada aos lances mais relevantes.</p>}
          {a.moments.length === 0 && <p>Nenhum lance crítico encontrado. Bom jogo!</p>}
          <ol aria-label="Momentos críticos">
            {a.moments.map((m) => (
              <li key={m.ply} className="card">
                <h3>Lance {m.move_number}: {SEVERITY[m.severity] ?? m.severity}</h3>
                <PositionBoard gameId={a.game_id} position={m.position} playable={[]} onPlay={() => undefined} />
                <p>{m.explanation}</p>
                <p>Conceito: {m.concept_title}</p>
              </li>
            ))}
          </ol>
          <p><small>{a.caveat}</small></p>
        </>
      )}
    </section>
  );
}
