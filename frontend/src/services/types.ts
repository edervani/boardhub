export type AgeBand = "under_12" | "12_15" | "16_17" | "18_plus";

export interface Me {
  id: string;
  email: string;
  display_name: string;
  email_verified: boolean;
  age_band: AgeBand;
  role: string;
  supervised: boolean;
}

export interface Game {
  id: string;
  name: string;
  age_rating: string;
  age_rating_label: string;
  ranked_enabled: boolean;
}

export interface Profile {
  display_name: string;
  avatar_key: string;
  bio: string | null;
  is_public: boolean;
  show_in_ranking: boolean;
  display_name_change_allowed_at: string | null;
}

export interface Preferences {
  theme: "light" | "dark" | "system";
  motion: "full" | "reduced" | "none" | "system";
  sound: boolean;
  move_confirmation: boolean;
  piece_styles: Record<string, "infantil" | "intermediario" | "classico">;
  locale: "pt-BR";
}

export interface Seat {
  seat: number;
  is_ai: boolean;
  is_you: boolean;
}

export interface MatchState {
  schema_version: number;
  board?: string; // jogo da velha
  squares?: string[]; // damas
  to_move?: "X" | "O" | "w" | "b"; // ausente no xadrez
  fen?: string; // xadrez
  moves?: string[]; // xadrez: lances UCI já jogados
}

export interface MatchView {
  id: string;
  game_id: string;
  mode: "ai" | "local" | string;
  status: "in_progress" | "finished" | "aborted" | string;
  ply: number;
  state: MatchState;
  to_move_seat: number | null;
  legal_moves: string[];
  result: "p1_win" | "p2_win" | "draw" | null;
  end_reason: string | null;
  ai_level: number | null;
  seats: Seat[];
  created_at: string;
  finished_at: string | null;
}

export interface MatchSummary {
  id: string;
  game_id: string;
  mode: string;
  status: string;
  result: string | null;
  ply: number;
  created_at: string;
  finished_at: string | null;
}

export interface EngineApply {
  state: MatchState;
  outcome: { winner: string | null; reason: string } | null;
  legal_moves: string[];
}
