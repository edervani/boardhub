import type { MatchView } from "../../services/types";
import { Board } from "./Board";
import { CheckersBoard } from "./CheckersBoard";
import { ChessBoard } from "./ChessBoard";

interface Props {
  match: MatchView;
  /** Lances que o usuário pode jogar agora (vazio = tabuleiro somente leitura). */
  playable: string[];
  onPlay: (move: string) => void;
}

/** Tabuleiro do jogo da partida, orientado conforme o assento do usuário. */
export function MatchBoard({ match, playable, onPlay }: Props) {
  const mySeat = match.seats.find((s) => s.is_you)?.seat ?? 1;
  const flipped = match.mode !== "local" && mySeat === 2;
  if (match.game_id === "chess") {
    return <ChessBoard fen={match.state.fen ?? ""} playable={playable} flipped={flipped} onPlay={onPlay} />;
  }
  if (match.game_id === "checkers") {
    return <CheckersBoard squares={match.state.squares ?? []} playable={playable} flipped={flipped} onPlay={onPlay} />;
  }
  return <Board board={match.state.board ?? ""} playable={playable} onPlay={(i) => onPlay(String(i))} />;
}
