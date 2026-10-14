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

export interface Player {
  seat: number;
  display_name: string | null;
  connected: boolean;
  grace_deadline: string | null;
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
  // Partidas online (Fase 2c); ausentes nas respostas das partidas locais e contra a IA.
  players?: Player[];
  invite_code?: string | null;
  invite_expires_at?: string | null;
  draw_offer_by_seat?: number | null;
  // Partida ranqueada liquidada (RF-019): rating de cada assento antes e depois.
  rating_changes?: RatingChange[];
}

export interface RatingChange {
  seat: number;
  before: number;
  after: number;
}

export interface ActiveMatch {
  id: string;
  game_id: string;
  mode: string;
  status: string;
  ply: number;
  your_seat: number | null;
  your_turn: boolean;
  opponent_name: string | null;
  invite_expires_at: string | null;
  created_at: string;
}

export interface QueueStatus {
  state: "idle" | "queued" | "matched";
  game_id: string | null;
  waited_seconds: number;
  offer_ai: boolean;
  match_id: string | null;
  ranked?: boolean;
  rating_window?: number | null;
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

export interface LeaderboardEntry {
  rank: number;
  display_name: string;
  avatar_key: string;
  rating: number;
  games_played: number;
}

export interface LeaderboardPage {
  game_id: string;
  min_games: number;
  items: LeaderboardEntry[];
  next_cursor: string | null;
}

export interface ModeStats {
  mode: "ai" | "online_casual" | "online_ranked";
  played: number;
  wins: number;
  losses: number;
  draws: number;
  win_rate: number | null;
}

export interface RatingPoint {
  match_id: string;
  created_at: string;
  before: number;
  after: number;
  delta: number;
}

export interface RatingInfo {
  rating: number;
  games_played: number;
  provisional: boolean;
  listed: boolean;
  games_until_listed: number;
  history: RatingPoint[];
}

export interface GameStats {
  game_id: string;
  name: string;
  played: number;
  wins: number;
  losses: number;
  draws: number;
  win_rate: number | null;
  by_mode: ModeStats[];
  streak: { kind: "win" | "loss" | "draw" | "none"; length: number };
  rating: RatingInfo | null;
}

export interface Stats {
  games: GameStats[];
}
