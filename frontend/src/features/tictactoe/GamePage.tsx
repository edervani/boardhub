import { useState, type FormEvent } from "react";
import type { Me } from "../../services/types";
import { Board } from "./Board";
import { MatchBoard } from "./MatchBoard";
import { LEVEL_LABELS, statusText } from "./status";
import { useGuestLocalMatch, useServerMatch } from "./useGame";

function GuestGame() {
  const g = useGuestLocalMatch();
  const over = g.outcome !== null;
  const text = over
    ? g.outcome?.winner ? `${g.outcome.winner} venceu.` : "Empate."
    : `Vez de ${g.state.to_move}.`;
  return (
    <section aria-labelledby="guest-title">
      <h2 id="guest-title">Jogo da velha — dois jogadores</h2>
      <p>Sem conta, a partida fica só neste navegador e não conta para estatísticas.</p>
      <p role="status" aria-live="polite">{text}</p>
      <Board board={(g.state.board ?? "")} playable={over ? [] : g.legal} onPlay={(i) => void g.play(i)} />
      {g.error && <p role="alert">{g.error}</p>}
      <p><button type="button" onClick={g.reset}>Nova partida</button></p>
    </section>
  );
}

type GameId = "tictactoe" | "checkers" | "chess";
const TITLES: Record<string, string> = { tictactoe: "Jogo da velha", checkers: "Damas", chess: "Xadrez" };

function SetupForm({ onStart }: { onStart: (body: Record<string, unknown>) => void }) {
  const [mode, setMode] = useState<"ai" | "local">("ai");
  const [game, setGame] = useState<GameId>("tictactoe");
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    onStart(mode === "ai"
      ? { game_id: game, mode, ai_level: Number(f.get("level")), preferred_seat: Number(f.get("seat")) }
      : { game_id: game, mode });
  }
  return (
    <form onSubmit={submit} aria-labelledby="setup-title">
      <h2 id="setup-title">Nova partida</h2>
      <label htmlFor="game">Jogo</label>
      <select id="game" value={game} onChange={(e) => setGame(e.target.value as GameId)}>
        <option value="tictactoe">Jogo da velha</option>
        <option value="checkers">Damas</option>
        <option value="chess">Xadrez</option>
      </select>
      <label htmlFor="mode">Modo</label>
      <select id="mode" value={mode} onChange={(e) => setMode(e.target.value as "ai" | "local")}>
        <option value="ai">Contra a IA</option>
        <option value="local">Dois jogadores neste dispositivo</option>
      </select>
      {mode === "ai" && (
        <>
          <label htmlFor="level">Nível da IA</label>
          <select id="level" name="level" defaultValue="3">
            {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{LEVEL_LABELS[n]}</option>)}
          </select>
          <label htmlFor="seat">Você joga</label>
          <select id="seat" name="seat" defaultValue="1">
            <option value="1">Primeiro ({game === "tictactoe" ? "X" : "brancas"})</option>
            <option value="2">Segundo ({game === "tictactoe" ? "O" : "pretas"})</option>
          </select>
        </>
      )}
      <p><button type="submit">Começar</button></p>
    </form>
  );
}

export function GamePage({ me }: { me: Me | null }) {
  const m = useServerMatch();
  if (!me) return <GuestGame />;
  if (!m.match) {
    return (
      <>
        <SetupForm onStart={(b) => void m.start(b)} />
        {m.error && <p role="alert">{m.error}</p>}
      </>
    );
  }
  const match = m.match;
  const playable = match.status === "in_progress" && !m.busy &&
    (match.mode === "local" || match.seats.find((s) => s.seat === match.to_move_seat)?.is_you)
    ? match.legal_moves : [];
  return (
    <section aria-labelledby="game-title">
      <h2 id="game-title">{TITLES[match.game_id] ?? match.game_id}{match.ai_level ? ` — IA nível ${match.ai_level}` : ""}</h2>
      <p role="status" aria-live="polite">{statusText(match)}</p>
      <MatchBoard match={match} playable={playable} onPlay={(mv) => void m.play(mv)} />
      {m.error && <p role="alert">{m.error}</p>}
      {match.status === "in_progress" && match.can_claim_draw === true && (
        <div className="card" role="group" aria-label="Reivindicação de empate">
          <p role="status" aria-live="polite">
            Você pode reivindicar empate: a mesma posição se repete pela terceira vez ou há 50 lances sem captura nem movimento de peão.
          </p>
          <button type="button" onClick={() => void m.claimDraw()}>Reivindicar empate</button>
        </div>
      )}
      <p>
        {match.status === "in_progress" && (
          <button type="button" className="secondary" onClick={() => void m.resign()}>Desistir</button>
        )}{" "}
        <button type="button" onClick={m.reset}>Nova partida</button>
      </p>
    </section>
  );
}
