import { useEffect, useState } from "react";
import { api, errorMessage } from "../../services/api";
import type { Game } from "../../services/types";

export function GameList() {
  const [games, setGames] = useState<Game[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api<Game[]>("GET", "/games").then(setGames, (e: unknown) => setError(errorMessage(e)));
  }, []);
  if (error) return <p role="alert">{error}</p>;
  if (games === null) return <p role="status">Carregando jogos…</p>;
  if (games.length === 0) return <p>Nenhum jogo disponível para sua idade no momento.</p>;
  return (
    <ul>
      {games.map((g) => (
        <li key={g.id} className="card">
          <strong>{g.name}</strong>{" "}
          <span className="badge" aria-label={`Classificação indicativa: ${g.age_rating_label}`}>
            {g.age_rating_label}
          </span>
        </li>
      ))}
    </ul>
  );
}
