// Types partagés avec le backend (schemas.py).
export type User = { id: number; email: string; display_name: string };

export type Token = { access_token: string; token_type: string; user: User };

export type Theme = {
  id: number;
  name: string;
  description: string;
  scan_interval_hours: number;
  lookback_hours: number;
  is_active: boolean;
  last_scanned_at: string | null;
  created_at: string;
};

export type Article = {
  id: number;
  url: string;
  title: string;
  source: string;
  image_url: string | null;
  published_at: string | null;
};

export type Cluster = {
  id: number;
  theme_id: number;
  title: string;
  summary: string;
  score: number;
  created_at: string;
  updated_at: string;
  articles: Article[];
};
