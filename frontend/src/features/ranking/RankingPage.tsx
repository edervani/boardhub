import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage } from "../../services/api";
import type { Game, LeaderboardEntry, LeaderboardPage, Me } from "../../services/types";

const PAGE_SIZE = 20;

/** Ranking público por jogo (RF-019). O servidor só devolve apelidos de perfis públicos. */
export function RankingPage({ me }: { me: Me | null }) {
  const [games, setGames] = useState<Game[] | null>(null);
  const [gameId, setGameId] = useState("");
  const [items, setItems] = useState<LeaderboardEntry[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [minGames, setMinGames] = useState(10);
  const [loading, setLoading] = useState(true); // a primeira consulta começa assim que o jogo é conhecido
  const [error, setError] = useState("");
  const seq = useRef(0); // descarta respostas de uma consulta anterior (troca rápida de jogo)

  useEffect(() => {
    api<Game[]>("GET", "/games").then(
      (all) => {
        const ranked = all.filter((g) => g.ranked_enabled);
        setGames(ranked);
        if (ranked[0]) setGameId(ranked[0].id);
      },
      (e: unknown) => setError(errorMessage(e)),
    );
  }, []);

  const load = useCallback(async (game: string, cursor: string | null) => {
    const mine = ++seq.current;
    setError(""); setLoading(true);
    try {
      const query = `limit=${PAGE_SIZE}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`;
      const page = await api<LeaderboardPage>("GET", `/ranking/${game}?${query}`);
      if (mine !== seq.current) return;
      setItems((cur) => (cursor ? [...cur, ...page.items] : page.items));
      setNext(page.next_cursor);
      setMinGames(page.min_games);
    } catch (e) {
      if (mine === seq.current) setError(errorMessage(e));
    } finally {
      if (mine === seq.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!gameId) return;
    setItems([]); setNext(null);
    void load(gameId, null);
  }, [gameId, load]);

  if (games === null) return error ? <p role="alert">{error}</p> : <p role="status">Carregando ranking…</p>;
  if (games.length === 0) return <p>Nenhum jogo tem ranking no momento.</p>;

  const title = games.find((g) => g.id === gameId)?.name ?? "";
  return (
    <section aria-labelledby="ranking-title">
      <h2 id="ranking-title">Ranking</h2>
      <p>
        Mostra quem tem perfil público, escolheu aparecer e já jogou pelo menos {minGames} partidas
        ranqueadas. Só o nome de exibição é público.
      </p>
      <label htmlFor="ranking-game">Jogo</label>
      <select id="ranking-game" value={gameId} onChange={(e) => setGameId(e.target.value)}>
        {games.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
      </select>
      {error && <p role="alert">{error}</p>}
      <p role="status" aria-live="polite">
        {loading ? "Carregando…" : items.length > 0 ? `${items.length} jogador(es) listado(s).` : ""}
      </p>
      {!loading && !error && items.length === 0 ? (
        <p>Ninguém no ranking de {title} ainda.</p>
      ) : items.length > 0 && (
        <table>
          <caption>Ranking de {title}, do maior para o menor rating</caption>
          <thead>
            <tr>
              <th scope="col">Posição</th>
              <th scope="col">Jogador</th>
              <th scope="col">Rating</th>
              <th scope="col">Partidas</th>
            </tr>
          </thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.rank}>
                <td>{i.rank}º</td>
                <th scope="row">
                  {i.display_name}{me?.display_name === i.display_name ? " (você)" : ""}
                </th>
                <td>{i.rating}</td>
                <td>{i.games_played}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {next && (
        <p>
          <button type="button" className="secondary" disabled={loading} onClick={() => void load(gameId, next)}>
            Carregar mais
          </button>
        </p>
      )}
    </section>
  );
}
