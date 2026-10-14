import { Board } from "../tictactoe/Board";
import { CheckersBoard } from "../tictactoe/CheckersBoard";
import { ChessBoard } from "../tictactoe/ChessBoard";
import type { Position } from "./types";

interface Props {
  gameId: string;
  position: Position;
  playable: string[]; // vazio = tabuleiro somente leitura (revisão)
  onPlay: (move: string) => void;
}

/** Escolhe o tabuleiro existente do jogo; só apresenta, a legalidade é do servidor. */
export function PositionBoard({ gameId, position, playable, onPlay }: Props) {
  const flipped = position.to_move === "b";
  if (gameId === "chess") {
    return <ChessBoard fen={position.fen ?? ""} playable={playable} flipped={flipped} onPlay={onPlay} />;
  }
  if (gameId === "checkers") {
    return <CheckersBoard squares={position.squares ?? []} playable={playable} flipped={flipped} onPlay={onPlay} />;
  }
  return <Board board={position.board ?? ""} playable={playable} onPlay={(i) => onPlay(String(i))} />;
}
