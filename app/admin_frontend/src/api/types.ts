export interface DashboardTask {
  id: string;
  title: string | null;
  status: string;
  submitted_at: string | null;
}

export interface DashboardSummary {
  new_requests: number;
  published_today: number;
  ctr_week: number;
  error_count: number;
  tasks: DashboardTask[];
}

export interface UGCPreview {
  title: string | null;
  date_iso: string | null;
  time_24h: string | null;
  venue_name: string | null;
  city: string | null;
  address: string | null;
  price_min: number | null;
  price_max: number | null;
  category: string | null;
  source_url: string | null;
}

export interface UGCButton {
  text: string;
  url: string;
}

export interface UGCItem {
  id: string;
  raw: string;
  payload: Record<string, unknown>;
  submitted_at: string | null;
  images: string[];
  preview: UGCPreview;
  caption: string;
  buttons: UGCButton[][];
}

export interface UGCListResponse {
  total: number;
  items: UGCItem[];
}
