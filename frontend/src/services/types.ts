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
