import { useState } from "react";
import { api, errorMessage } from "../../services/api";
import { ExerciseView } from "./ExerciseView";
import type { PlacementResponse } from "./types";

type Answer = { exercise_id: string; answer: string };

/** Nivelamento adaptativo: o servidor reconstrói o percurso a cada passo (sem estado no cliente). */
export function Placement({ gameId, onClose }: { gameId: string; onClose: () => void }) {
  const [declared, setDeclared] = useState("never");
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [state, setState] = useState<PlacementResponse | null>(null);
  const [error, setError] = useState("");

  async function step(next: Answer[]) {
    setError("");
    try {
      const r = await api<PlacementResponse>("POST", `/academy/${gameId}/placement`, { declared, answers: next });
      setAnswers(next); setState(r);
    } catch (e) { setError(errorMessage(e)); }
  }
  const current = state?.next_exercise ?? null;
  return (
    <section aria-labelledby="pl-title" className="card">
      <h3 id="pl-title">Nivelamento</h3>
      {error && <p role="alert">{error}</p>}
      {!state && (
        <>
          <label>Qual é a sua experiência com o jogo?{" "}
            <select value={declared} onChange={(e) => setDeclared(e.target.value)}>
              <option value="never">Nunca joguei</option>
              <option value="knows_rules">Sei as regras</option>
              <option value="regular">Jogo com frequência</option>
              <option value="competitive">Jogo competitivamente</option>
            </select>
          </label>{" "}
          <button type="button" onClick={() => void step([])}>Começar</button>
        </>
      )}
      {state && !state.done && current && (
        <>
          <p role="status">Pergunta {state.answered + 1} de {state.total}</p>
          <ExerciseView key={current.id} exercise={current} locked={false}
            onAnswer={(a) => void step([...answers, { exercise_id: current.id, answer: a }])} />
        </>
      )}
      {state?.done && state.result && (
        <div role="status">
          <p>Nível sugerido contra a IA: <strong>{state.result.suggested_ai_level}</strong></p>
          <ul>
            {state.result.concepts.map((c) => (
              <li key={c.concept_key}>{c.title}: {Math.round(c.mastery * 100)}%</li>
            ))}
          </ul>
        </div>
      )}
      <button type="button" className="secondary" onClick={onClose}>Fechar</button>
    </section>
  );
}
