import { useEffect, useState, type ReactNode } from "react";
import type { MatchView } from "../../services/types";
import {
  DRAW_AGREEMENT_GAMES,
  GAME_TITLES,
  mySeat,
  onlineStatusText,
  ratingChangeText,
} from "./onlineStatus";
import { ReportButton } from "../social/ReportButton";
import { useOnlineMatch } from "./useOnlineMatch";

/** O lobby não conhece os tabuleiros (features não se importam entre si): a aplicação os injeta. */
export type BoardRenderer = (props: {
  match: MatchView;
  playable: string[];
  onPlay: (move: string) => void;
}) => ReactNode;

const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

/** Contagem regressiva visual por segundo; o leitor de tela recebe um aviso a cada 15 s. */
function Countdown({ deadline }: { deadline: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const remaining = Math.max(0, Math.ceil((Date.parse(deadline) - now) / 1000));
  const spoken = remaining === 0 ? "Você já pode reivindicar a vitória."
    : `Faltam cerca de ${Math.ceil(remaining / 15) * 15} segundos para poder reivindicar a vitória.`;
  return (
    <>
      <span aria-hidden="true">{mmss(remaining)}</span>
      <span className="sr-only" role="status" aria-live="polite">{spoken}</span>
    </>
  );
}

function ConnectionBanner({ state, attempt }: { state: string; attempt: number }) {
  if (state === "open" || state === "connecting") return null;
  if (state === "closed") {
    return <p role="alert">Conexão encerrada. Entre novamente para continuar a partida.</p>;
  }
  return <p role="alert">Conexão perdida. Tentando reconectar… (tentativa {attempt})</p>;
}

interface Props {
  matchId: string;
  renderBoard: BoardRenderer;
  onLeave: () => void;
}

export function OnlineMatch({ matchId, renderBoard, onLeave }: Props) {
  const m = useOnlineMatch(matchId);
  const [confirmResign, setConfirmResign] = useState(false);
  const match = m.match;
  if (!match) {
    return m.error ? <p role="alert">{m.error}</p> : <p role="status">Carregando partida…</p>;
  }
  const seat = mySeat(match);
  const inProgress = match.status === "in_progress";
  const myTurn = inProgress && match.to_move_seat === seat;
  const playable = m.connection === "open" && !m.pending && myTurn ? match.legal_moves : [];
  const opponent = (match.players ?? []).find((p) => p.seat !== seat);
  const opponentToMove = inProgress && match.to_move_seat !== seat;
  const offer = match.draw_offer_by_seat ?? null;
  const title = (GAME_TITLES[match.game_id] ?? match.game_id) + (match.mode === "online_ranked" ? " (ranqueada)" : "");
  const ratingText = ratingChangeText(match);

  return (
    <section aria-labelledby="online-title">
      <h2 id="online-title">{title} — contra {opponent?.display_name ?? "o oponente"}</h2>
      <ConnectionBanner state={m.connection} attempt={m.attempt} />
      <p>{onlineStatusText(match)}</p>
      {ratingText && <p role="status">{ratingText}</p>}
      <p role="status" aria-live="polite">{m.polite}</p>
      <p role="alert" aria-live="assertive">{m.assertive}</p>

      {renderBoard({ match, playable, onPlay: m.play })}
      {m.error && <p role="alert">{m.error}</p>}
      {opponent && <ReportButton targetType="match" targetId={match.id} label="Denunciar o oponente" />}

      {inProgress && opponent && !opponent.connected && (
        <div className="card" role="group" aria-label="Adversário desconectado">
          <p>O adversário está desconectado.</p>
          {opponentToMove && opponent.grace_deadline ? (
            <p>Você poderá reivindicar a vitória em <Countdown deadline={opponent.grace_deadline} />.</p>
          ) : (
            <p>A tolerância conta só no turno dele.</p>
          )}
          {opponentToMove && (
            <button type="button" className="secondary" onClick={m.claimAbandon}>
              Reivindicar vitória por abandono
            </button>
          )}
        </div>
      )}

      {inProgress && offer !== null && offer !== seat && (
        <div className="card" role="group" aria-label="Proposta de empate">
          <p>O adversário propôs empate.</p>
          <button type="button" onClick={() => m.respondDraw(true)}>Aceitar empate</button>{" "}
          <button type="button" className="secondary" onClick={() => m.respondDraw(false)}>Recusar</button>
        </div>
      )}

      <p>
        {inProgress && DRAW_AGREEMENT_GAMES.has(match.game_id) && offer === null && (
          <><button type="button" className="secondary" onClick={m.offerDraw}>Propor empate</button>{" "}</>
        )}
        {inProgress && !confirmResign && (
          <><button type="button" className="secondary" onClick={() => setConfirmResign(true)}>Desistir</button>{" "}</>
        )}
        {inProgress && confirmResign && (
          <>
            <button type="button" onClick={() => { setConfirmResign(false); m.resign(); }}>Confirmar desistência</button>{" "}
            <button type="button" className="secondary" onClick={() => setConfirmResign(false)}>Continuar jogando</button>{" "}
          </>
        )}
        <button type="button" onClick={onLeave}>Voltar ao lobby</button>
      </p>
    </section>
  );
}
