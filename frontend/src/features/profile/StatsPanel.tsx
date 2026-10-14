import { useEffect, useState } from "react";
import { api, errorMessage } from "../../services/api";
import type { GameStats, ModeStats, RatingInfo, Stats } from "../../services/types";

const MODE_LABELS: Record<ModeStats["mode"], string> = {
  ai: "Contra a IA",
  online_casual: "Online casual",
  online_ranked: "Online ranqueada",
};

// [singular, plural, "seguida" concordando em gênero] de cada tipo de sequência.
const STREAK_LABELS = {
  win: ["vitória", "vitórias", "seguida", "seguidas"],
  loss: ["derrota", "derrotas", "seguida", "seguidas"],
  draw: ["empate", "empates", "seguido", "seguidos"],
} as const;
const HISTORY_SHOWN = 10;

const percent = (rate: number | null): string => (rate === null ? "—" : `${Math.round(rate * 100)}%`);
const signed = (n: number): string => (n > 0 ? `+${n}` : String(n));

export function streakText(s: GameStats["streak"]): string {
  if (s.kind === "none") return "Sem partidas concluídas.";
  const [one, many, followOne, followMany] = STREAK_LABELS[s.kind];
  const plural = s.length !== 1;
  return `${s.length} ${plural ? many : one} ${plural ? followMany : followOne}.`;
}

export function ratingText(r: RatingInfo): string {
  const base = `Rating ${r.rating}${r.provisional ? " (provisório)" : ""}, ${r.games_played} partida(s) ranqueada(s).`;
  if (r.listed) return `${base} Você aparece no ranking.`;
  return r.games_until_listed > 0
    ? `${base} Faltam ${r.games_until_listed} partida(s) para entrar no ranking.`
    : `${base} Você não aparece no ranking (perfil privado ou oculto).`;
}

function RatingHistory({ rating, name }: { rating: RatingInfo; name: string }) {
  const rows = rating.history.slice(-HISTORY_SHOWN).reverse();
  if (rows.length === 0) return null;
  return (
    <table>
      <caption>Últimas variações de rating em {name}</caption>
      <thead>
        <tr><th scope="col">Data</th><th scope="col">Antes</th><th scope="col">Depois</th><th scope="col">Variação</th></tr>
      </thead>
      <tbody>
        {rows.map((h) => (
          <tr key={h.match_id}>
            <td>{new Date(h.created_at).toLocaleDateString("pt-BR")}</td>
            <td>{h.before}</td>
            <td>{h.after}</td>
            <td>{signed(h.delta)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function GameCard({ g }: { g: GameStats }) {
  return (
    <section className="card" aria-labelledby={`stats-${g.game_id}`}>
      <h4 id={`stats-${g.game_id}`}>{g.name}</h4>
      {g.played === 0 ? <p>Nenhuma partida concluída ainda.</p> : (
        <>
          <p>
            {g.played} partida(s): {g.wins} vitória(s), {g.losses} derrota(s), {g.draws} empate(s)
            {" "}({percent(g.win_rate)} de vitórias).
          </p>
          <p>Sequência atual: {streakText(g.streak)}</p>
          <table>
            <caption>Resultados por modo em {g.name}</caption>
            <thead>
              <tr>
                <th scope="col">Modo</th><th scope="col">Partidas</th><th scope="col">Vitórias</th>
                <th scope="col">Derrotas</th><th scope="col">Empates</th><th scope="col">% vitórias</th>
              </tr>
            </thead>
            <tbody>
              {g.by_mode.map((m) => (
                <tr key={m.mode}>
                  <th scope="row">{MODE_LABELS[m.mode]}</th>
                  <td>{m.played}</td><td>{m.wins}</td><td>{m.losses}</td><td>{m.draws}</td>
                  <td>{percent(m.win_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {g.rating && (
        <>
          <p>{ratingText(g.rating)}</p>
          <RatingHistory rating={g.rating} name={g.name} />
        </>
      )}
    </section>
  );
}

/** Estatísticas e rating do próprio usuário (RF-021), recontados pelo servidor. */
export function StatsPanel() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Stats>("GET", "/me/stats").then(setStats, (e: unknown) => setError(errorMessage(e)));
  }, []);

  return (
    <section aria-labelledby="stats-title">
      <h3 id="stats-title">Estatísticas</h3>
      <p>Partidas locais não entram na contagem.</p>
      {error && <p role="alert">{error}</p>}
      {!stats && !error && <p role="status">Carregando estatísticas…</p>}
      {stats?.games.map((g) => <GameCard key={g.game_id} g={g} />)}
    </section>
  );
}
