import { useEffect, useState } from "react";
import { api, errorMessage } from "../../services/api";
import type { Achievements } from "./types";

/** Vitrine de conquistas (RF-026): distintivos sem valor monetário, concedidos só pelo servidor. */
export function AchievementsPage() {
  const [data, setData] = useState<Achievements | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Achievements>("GET", "/me/achievements")
      .then(setData)
      .catch((e: unknown) => setError(errorMessage(e)));
  }, []);

  return (
    <section aria-labelledby="ach-title">
      <h2 id="ach-title">Conquistas</h2>
      {error && <p role="alert">{error}</p>}
      {!data && !error && <p role="status">Carregando…</p>}
      {data && (
        <>
          <p>{data.earned_count} de {data.items.length} conquistas. São só distintivos: não valem dinheiro nem dão vantagem em partidas.</p>
          <ul aria-label="Conquistas">
            {data.items.map((a) => (
              <li key={a.key}>
                <h3>{a.title}{a.earned && <span> (conquistada)</span>}</h3>
                <p>{a.description}</p>
                {a.earned && a.earned_at ? (
                  <p>Conquistada em {new Date(a.earned_at).toLocaleDateString("pt-BR")}.</p>
                ) : (
                  <p>
                    <label htmlFor={`prog-${a.key}`}>Progresso: {a.progress} de {a.target}</label>{" "}
                    <progress id={`prog-${a.key}`} max={a.target} value={a.progress} />
                  </p>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
