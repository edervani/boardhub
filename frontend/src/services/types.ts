export type AgeBand = "under_12" | "12_15" | "16_17" | "18_plus";

export interface Me {
  id: string;
  email: string;
  display_name: string;
  email_verified: boolean;
  age_band: AgeBand;
  role: string;
  supervised: boolean;
  /** RF-030: data prevista da exclusão, enquanto a conta está em período de arrependimento. */
  deletion_scheduled_for?: string | null;
  deletion_by_guardian?: boolean;
}

// ---- RF-031 / RF-032: social e moderação (só apelido, nunca e-mail nem id de conta alheia) ----
export interface Person { display_name: string; avatar_key: string }
export interface Friend extends Person { friendship_id: string; since: string }
export interface FriendRequest extends Person { friendship_id: string; created_at: string }
export interface FriendRequests { incoming: FriendRequest[]; outgoing: FriendRequest[] }
export interface BlockedUser extends Person { block_id: string; created_at: string }
export interface DirectInvitation {
  id: string; game_id: string; status: string; created_at: string;
  expires_at: string | null; match_id: string | null; other: Person;
}
export type ReportReason = "offensive_name" | "offensive_bio" | "cheating" | "harassment" | "other";
export interface ReportQueueItem {
  id: string; status: string; target_type: string; reason: ReportReason; note: string | null;
  created_at: string; target_user_id: string; target_display_name: string | null;
  target_bio: string | null; target_status: string; match_id: string | null;
  open_reports_on_target: number; resolution_action: string | null; resolved_at: string | null;
}
export interface ReportQueue { items: ReportQueueItem[]; total: number }

export interface DataExport {
  id: string;
  status: string;
  created_at: string;
  expires_at: string;
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

export type MoveNotation = "algebraic_pt" | "san" | "uci";

export interface Preferences {
  theme: "light" | "dark" | "system";
  motion: "full" | "reduced" | "none" | "system";
  sound: boolean;
  move_confirmation: boolean;
  /** RF-007: só exibição (xadrez); o servidor segue em UCI. */
  move_notation: MoveNotation;
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
  /** Xadrez: lances já jogados em SAN internacional (K, Q, R, B, N), para exibição. */
  san_moves?: string[];
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

export interface ChildSettings {
  allow_open_matchmaking: boolean;
  profile_public: boolean;
  show_in_ranking: boolean;
  daily_minutes_limit: number | null;
}

/** Tempo de jogo de hoje (dia de America/Sao_Paulo); `resets_at` é quando o dia vira. */
export interface ChildUsage {
  used_seconds: number;
  limit_seconds: number | null;
  resets_at: string;
}

export interface Child {
  id: string;
  display_name: string;
  age_band: AgeBand;
  settings: ChildSettings;
  usage_today: ChildUsage;
  deletion_scheduled_for?: string | null;
}
