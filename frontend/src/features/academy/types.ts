/** Contratos da Academy e da análise pós-partida (espelham backend/app/schemas/academy.py). */

export type SkillStatus = "not_started" | "in_practice" | "mastered" | "in_review";

export interface Position {
  board?: string; // jogo da velha
  squares?: string[]; // damas
  fen?: string; // xadrez
  to_move?: string;
}

export interface Track {
  game_id: string;
  game_name: string;
  title: string;
  description: string;
  lessons_count: number;
  exercises_count: number;
  concepts_total: number;
  concepts_mastered: number;
}

export interface Concept {
  key: string;
  title: string;
  summary: string;
  prerequisites: string[];
  mastery: number;
  status: SkillStatus;
  review_due: boolean;
}

export interface ExerciseStub {
  id: string;
  type: "best_move" | "rule_quiz";
  difficulty: number;
  solved: boolean;
}

export interface Lesson {
  id: string;
  concept_key: string;
  concept_title: string;
  title: string;
  summary: string;
  body: string[];
  completed: boolean;
  exercises: ExerciseStub[];
}

export interface LessonsResponse {
  game_id: string;
  content_version: string;
  title: string;
  description: string;
  concepts: Concept[];
  lessons: Lesson[];
}

export interface Exercise {
  id: string;
  game_id: string;
  lesson_id: string;
  concept_key: string;
  concept_title: string;
  type: "best_move" | "rule_quiz";
  difficulty: number;
  prompt: string;
  position: Position | null;
  legal_moves: string[];
  options: { id: string; text: string }[];
  hints_used: number;
  hints_available: number;
}

export interface Hint {
  level: number;
  text: string;
  hints_used: number;
}

export interface Attempt {
  correct: boolean;
  feedback: string;
  explanation: string | null;
  hint_level: number;
  concept_key: string;
  mastery: number;
  status: SkillStatus;
  mastered_now: boolean;
  next_review_at: string | null;
}

export interface PlacementResponse {
  done: boolean;
  answered: number;
  total: number;
  next_exercise: Exercise | null;
  result: {
    suggested_ai_level: number;
    concepts: { concept_key: string; title: string; mastery: number }[];
  } | null;
}

export interface ConceptStatus {
  game_id: string;
  concept_key: string;
  title: string;
  mastery: number;
  status: SkillStatus;
  review_due: boolean;
  next_review_at: string | null;
}

export interface Moment {
  ply: number;
  move_number: number;
  severity: "inaccuracy" | "mistake" | "blunder" | string;
  kind: string;
  played: string;
  played_label: string;
  best: string;
  best_label: string;
  reply: string | null;
  reply_label: string | null;
  explanation: string;
  explanation_source: "template" | "llm";
  concept_key: string;
  concept_title: string;
  lesson_id: string | null;
  position: Position;
}

export interface Analysis {
  match_id: string;
  game_id: string;
  engine_version: string;
  analyzed_moves: number;
  user_moves: number;
  truncated: boolean;
  counts: Record<string, number>;
  moments: Moment[];
  caveat: string;
}
