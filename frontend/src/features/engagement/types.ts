/** Contratos de conquistas, desafio diário e notificações (espelham backend/app/schemas/engagement.py). */
import type { Exercise } from "../academy/types";

export interface Achievement {
  key: string;
  title: string;
  description: string;
  game_id: string | null;
  earned: boolean;
  earned_at: string | null;
  progress: number;
  target: number;
}

export interface Achievements {
  definition_version: string;
  earned_count: number;
  items: Achievement[];
}

export interface DailyChallenge {
  game_id: string;
  game_name: string;
  day: string;
  resets_at: string;
  status: "pending" | "answered";
  correct: boolean | null;
  exercise: Exercise;
  explanation: string | null;
}

export interface DailyChallenges {
  day: string;
  resets_at: string;
  completed_total: number;
  challenges: DailyChallenge[];
}

export interface DailyAttempt {
  correct: boolean;
  feedback: string;
  explanation: string | null;
  completed_total: number;
}

export interface AppNotification {
  id: string;
  kind: string;
  title: string;
  body: string;
  created_at: string;
  read: boolean;
}

export interface NotificationList {
  items: AppNotification[];
  unread_count: number;
}

export interface NotificationPreference {
  kind: string;
  label: string;
  enabled: boolean;
}
