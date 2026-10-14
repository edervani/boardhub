import { useEffect, useRef, useState } from "react";
import { api, errorMessage } from "../../services/api";
import { ExerciseView } from "./ExerciseView";
import type { Attempt, Exercise, Hint, SkillStatus } from "./types";

export const STATUS_TEXT: Record<SkillStatus, string> = {
  not_started: "Não iniciado", in_practice: "Em prática", mastered: "Dominado", in_review: "Em revisão",
};

interface Props {
  exerciseId: string;
  onNext: (() => void) | null;
  onDone: (a: Attempt) => void;
}

export function LessonExercise({ exerciseId, onNext, onDone }: Props) {
  const [ex, setEx] = useState<Exercise | null>(null);
  const [hints, setHints] = useState<Hint[]>([]);
  const [result, setResult] = useState<Attempt | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [round, setRound] = useState(0);
  const started = useRef(Date.now());
  const title = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    setEx(null); setHints([]); setResult(null); setError("");
    api<Exercise>("GET", `/academy/exercises/${exerciseId}`)
      .then((e) => { setEx(e); started.current = Date.now(); })
      .catch((e: unknown) => setError(errorMessage(e)));
  }, [exerciseId]);
  useEffect(() => { if (ex) title.current?.focus(); }, [ex]);

  async function submit(answer: string) {
    if (busy || result) return;
    setBusy(true); setError("");
    try {
      const a = await api<Attempt>("POST", `/academy/exercises/${exerciseId}/attempts`,
        { answer, duration_ms: Date.now() - started.current });
      setResult(a); onDone(a);
    } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }

  async function hint() {
    try {
      const h = await api<Hint>("POST", `/academy/exercises/${exerciseId}/hints`, { level: hints.length + 1 });
      setHints((prev) => [...prev, h]);
    } catch (e) { setError(errorMessage(e)); }
  }

  if (error && !ex) return <p role="alert">{error}</p>;
  if (!ex) return <p role="status">Carregando exercício…</p>;
  return (
    <section aria-labelledby="ex-title" className="card">
      <h3 id="ex-title" tabIndex={-1} ref={title}>{ex.concept_title}: exercício</h3>
      <ExerciseView key={round} exercise={ex} locked={busy || result !== null} onAnswer={(a) => void submit(a)} />
      <ul aria-label="Dicas">
        {hints.map((h) => <li key={h.level}>Dica {h.level}: {h.text}</li>)}
      </ul>
      {!result?.correct && hints.length < ex.hints_available && (
        <button type="button" className="secondary" onClick={() => void hint()}>Pedir dica</button>
      )}
      <div role="status" aria-live="polite">
        {result && (
          <>
            <p><strong>{result.correct ? "Correto." : "Ainda não."}</strong> {result.feedback}</p>
            {result.explanation && <p>{result.explanation}</p>}
            <p>
              Domínio de “{ex.concept_title}”: {Math.round(result.mastery * 100)}% ·{" "}
              {STATUS_TEXT[result.status]}{result.mastered_now ? " (conquistado agora!)" : ""}
            </p>
          </>
        )}
      </div>
      {error && <p role="alert">{error}</p>}
      {result && !result.correct && (
        <button type="button" onClick={() => { setResult(null); setRound((r) => r + 1); started.current = Date.now(); }}>
          Tentar de novo
        </button>
      )}
      {result?.correct && onNext && <button type="button" onClick={onNext}>Próximo</button>}
    </section>
  );
}
