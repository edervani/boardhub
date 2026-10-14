import { useState } from "react";
import { PositionBoard } from "./PositionBoard";
import type { Exercise } from "./types";

interface Props {
  exercise: Exercise;
  locked: boolean;
  onAnswer: (answer: string) => void;
}

/** Apresenta o enunciado e coleta a resposta; a correção é sempre do servidor. */
export function ExerciseView({ exercise: ex, locked, onAnswer }: Props) {
  const [choice, setChoice] = useState("");
  return (
    <div>
      <p>{ex.prompt}</p>
      {ex.type === "best_move" && ex.position && (
        <PositionBoard gameId={ex.game_id} position={ex.position}
          playable={locked ? [] : ex.legal_moves} onPlay={onAnswer} />
      )}
      {ex.type === "rule_quiz" && (
        <form onSubmit={(e) => { e.preventDefault(); if (choice) onAnswer(choice); }}>
          <fieldset disabled={locked}>
            <legend>Escolha uma resposta</legend>
            {ex.options.map((o) => (
              <p key={o.id}>
                <label>
                  <input type="radio" name={`opt-${ex.id}`} value={o.id} checked={choice === o.id}
                    onChange={() => setChoice(o.id)} /> {o.text}
                </label>
              </p>
            ))}
          </fieldset>
          <button type="submit" disabled={!choice || locked}>Responder</button>
        </form>
      )}
    </div>
  );
}
