import { useEffect, useState } from "react";
import { api, errorMessage } from "../../services/api";
import type { MatchSummary } from "../../services/types";

const RESULT: Record<string, string> = { p1_win: "Vitória do 1º jogador (X)", p2_win: "Vitória do 2º jogador (O)", draw: "Empate" };
const MODE: Record<string, string> = { ai: "Contra a IA", local: "Local" };

export function History() {
  const [items, setItems] = useState<MatchSummary[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function load(next: string | null) {
    try {
      const page = await api<{ items: MatchSummary[]; next_cursor: string | null }>(
        "GET", `/me/matches?limit=20${next ? `&cursor=${encodeURIComponent(next)}` : ""}`);
      setItems((prev) => [...(prev ?? []), ...page.items]);
      setCursor(page.next_cursor);
    } catch (e) { setError(errorMessage(e)); }
  }
  useEffect(() => { void load(null); }, []);

  if (error) return <p role="alert">{error}</p>;
  if (items === null) return <p role="status">Carregando histórico…</p>;
  if (items.length === 0) return <p>Você ainda não jogou nenhuma partida.</p>;
  return (
    <section aria-labelledby="hist-title">
      <h2 id="hist-title">Histórico de partidas</h2>
      <ul>
        {items.map((m) => (
          <li key={m.id} className="card">
            {MODE[m.mode] ?? m.mode} · {new Date(m.created_at).toLocaleString("pt-BR")} ·{" "}
            {m.status === "finished" ? (m.result ? RESULT[m.result] : "Encerrada") : "Em andamento"}
          </li>
        ))}
      </ul>
      {cursor && <button type="button" onClick={() => void load(cursor)}>Carregar mais</button>}
    </section>
  );
}
