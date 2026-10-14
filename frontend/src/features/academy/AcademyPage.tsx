import { useEffect, useRef, useState } from "react";
import { api, errorMessage } from "../../services/api";
import { LessonExercise, STATUS_TEXT } from "./LessonExercise";
import { Placement } from "./Placement";
import type { LessonsResponse, Track } from "./types";

export function AcademyPage() {
  const [tracks, setTracks] = useState<Track[] | null>(null);
  const [game, setGame] = useState<string | null>(null);
  const [data, setData] = useState<LessonsResponse | null>(null);
  const [lessonId, setLessonId] = useState<string | null>(null);
  const [exId, setExId] = useState<string | null>(null);
  const [placing, setPlacing] = useState(false);
  const [error, setError] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    api<Track[]>("GET", "/academy/tracks").then(setTracks).catch((e: unknown) => setError(errorMessage(e)));
  }, []);
  useEffect(() => { heading.current?.focus(); }, [lessonId, game]);

  async function load(g: string) {
    try { setData(await api<LessonsResponse>("GET", `/academy/${g}/lessons`)); }
    catch (e) { setError(errorMessage(e)); }
  }
  function open(g: string) {
    setGame(g); setData(null); setLessonId(null); setExId(null); setPlacing(false);
    void load(g);
  }

  if (error) return <p role="alert">{error}</p>;
  if (!tracks) return <p role="status">Carregando Academy…</p>;
  const lesson = data?.lessons.find((l) => l.id === lessonId) ?? null;
  const idx = lesson && exId ? lesson.exercises.findIndex((e) => e.id === exId) : -1;
  const nextId = lesson && idx >= 0 ? lesson.exercises[idx + 1]?.id : undefined;

  return (
    <section aria-labelledby="ac-title">
      <h2 id="ac-title" tabIndex={-1} ref={heading}>Academy</h2>
      <ul aria-label="Trilhas">
        {tracks.map((t) => (
          <li key={t.game_id} className="card">
            <h3>{t.title}</h3>
            <p>{t.description}</p>
            <p>
              {t.lessons_count} lições · {t.exercises_count} exercícios ·{" "}
              {t.concepts_mastered} de {t.concepts_total} conceitos dominados
            </p>
            <button type="button" onClick={() => open(t.game_id)} aria-label={`Abrir trilha ${t.title}`}>
              Abrir
            </button>
          </li>
        ))}
      </ul>
      {game && !data && <p role="status">Carregando trilha…</p>}
      {data && !lesson && (
        <section aria-labelledby="tr-title">
          <h3 id="tr-title">{data.title}</h3>
          <button type="button" className="secondary" onClick={() => setPlacing(true)}>Fazer nivelamento</button>
          {placing && game && <Placement gameId={game} onClose={() => { setPlacing(false); void load(game); }} />}
          <ol aria-label="Lições">
            {data.lessons.map((l) => {
              const c = data.concepts.find((x) => x.key === l.concept_key);
              return (
                <li key={l.id}>
                  <button type="button" onClick={() => { setLessonId(l.id); setExId(null); }}>{l.title}</button>{" "}
                  <span className="badge">
                    {c ? STATUS_TEXT[c.status] : ""}{c?.review_due ? " · revisão pendente" : ""}
                  </span>
                  {l.completed ? " (concluída)" : ""}
                </li>
              );
            })}
          </ol>
        </section>
      )}
      {lesson && game && (
        <article aria-labelledby="ls-title">
          <button type="button" className="secondary"
            onClick={() => { setLessonId(null); setExId(null); void load(game); }}>
            Voltar às lições
          </button>
          <h3 id="ls-title">{lesson.title}</h3>
          {lesson.body.map((p, i) => <p key={i}>{p}</p>)}
          {!exId && (
            <>
              <h4>Exercícios</h4>
              <ul>
                {lesson.exercises.map((e, i) => (
                  <li key={e.id}>
                    <button type="button" onClick={() => setExId(e.id)}>
                      Exercício {i + 1} (dificuldade {e.difficulty}){e.solved ? " — resolvido" : ""}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
          {exId && (
            <LessonExercise exerciseId={exId} onDone={() => undefined}
              onNext={nextId ? () => setExId(nextId) : () => { setExId(null); void load(game); }} />
          )}
        </article>
      )}
    </section>
  );
}
