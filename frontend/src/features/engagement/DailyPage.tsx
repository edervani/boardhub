import { useEffect, useState } from "react";
import { api, errorMessage } from "../../services/api";
import { ExerciseView } from "../academy/ExerciseView";
import type { DailyAttempt, DailyChallenge, DailyChallenges } from "./types";

/** Desafio diário (RF-027): um exercício por jogo e por dia, igual para todos. Sem sequência nem pressão. */
export function DailyPage() {
  const [data, setData] = useState<DailyChallenges | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<Record<string, DailyAttempt>>({});

  useEffect(() => {
    api<DailyChallenges>("GET", "/daily-challenge")
      .then(setData)
      .catch((e: unknown) => setError(errorMessage(e)));
  }, []);

  async function answer(c: DailyChallenge, value: string) {
    setBusy(true); setError("");
    try {
      const r = await api<DailyAttempt>("POST", `/daily-challenge/${c.game_id}/attempt`, { answer: value });
      setResults((prev) => ({ ...prev, [c.game_id]: r }));
      setData((d) => d && {
        ...d, completed_total: r.completed_total,
        challenges: d.challenges.map((x) => (x.game_id === c.game_id
          ? { ...x, status: "answered" as const, correct: r.correct, explanation: r.explanation } : x)),
      });
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="daily-title">
      <h2 id="daily-title">Desafio do dia</h2>
      {error && <p role="alert">{error}</p>}
      {!data && !error && <p role="status">Carregando…</p>}
      {data && (
        <>
          <p>
            Um desafio por jogo, igual para todo mundo, que muda todo dia à meia-noite (horário de Brasília).
            Se você faltar um dia, nada se perde. Desafios respondidos até agora: {data.completed_total}.
          </p>
          {data.challenges.map((c) => (
            <article key={c.game_id} aria-labelledby={`daily-${c.game_id}`}>
              <h3 id={`daily-${c.game_id}`}>{c.game_name}</h3>
              <ExerciseView exercise={c.exercise} locked={busy || c.status === "answered"}
                onAnswer={(v) => void answer(c, v)} />
              {c.status === "answered" && (
                <div role="status">
                  <p>{results[c.game_id]?.feedback ?? (c.correct ? "Você acertou." : "Você já respondeu hoje.")}</p>
                  {c.explanation && <p>{c.explanation}</p>}
                  <p>Volte amanhã para um novo desafio. Para treinar mais, use a Academy.</p>
                </div>
              )}
            </article>
          ))}
        </>
      )}
    </section>
  );
}
