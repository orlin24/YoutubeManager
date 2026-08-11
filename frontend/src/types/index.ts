export interface User {
  id: string;
  email: string;
  name: string;
}

export interface Account {
  id: string;
  channel_id: string;
  channel_title: string;
  channel_thumbnail: string;
  google_account_email: string;
  connected_at: string | null;
  auth_error?: string | null;
}

export interface Channel {
  id: string;
  channel_id: string;
  title: string;
  description: string;
  thumbnail_url: string;
  subscriber_count: number;
  view_count: number;
  video_count: number;
  updated_at: string | null;
  lifecycle_mode?: string | null;
  profile?: ChannelProfile;
  analytics?: AnalyticsOverview;
}

export interface ChannelProfile {
  niche?: string | null;
  target_audience?: string | null;
  language?: string | null;
  country?: string | null;
  content_style?: string | null;
  upload_frequency?: string | null;
  upload_cadence_days?: number | null;
  monetized?: boolean;
  brand_rules?: string | null;
  successful_titles?: string[];
  failed_topics?: string[];
  historical_performance?: Record<string, unknown>;
}

export interface Video {
  id: string;
  youtube_video_id: string;
  title: string;
  description: string;
  thumbnail_url: string;
  published_at: string | null;
  duration_seconds: number | null;
  view_count: number;
  like_count: number;
  comment_count: number;
  privacy_status: string;
  ctr: number | null;
  average_view_duration_seconds: number | null;
  ai_score: number | null;
  channel_id: string;
}

export interface AnalyticsOverview {
  views: number;
  watch_time_seconds: number;
  subscribers_gained: number;
  subscribers_lost: number;
  likes: number;
  comments: number;
  shares: number;
  average_view_duration_seconds: number;
  estimated_revenue: number | null;
}

export interface TimeseriesPoint {
  date: string;
  views: number;
  watch_time_seconds: number;
  subscribers_gained: number;
  estimated_revenue: number | null;
}

export interface Growth {
  views_delta: number;
  subscribers_delta: number;
  views_pct: number | null;
  subscribers_pct: number | null;
}

export interface AnalyticsResponse {
  overview: AnalyticsOverview;
  timeseries: TimeseriesPoint[];
  top_videos: Video[];
  worst_videos: Video[];
  growth: Growth;
}

export interface AiAction {
  id: string;
  label: string;
  permission: string;
  requires_approval: boolean;
  payload: Record<string, unknown>;
}

export interface AiDecision {
  decision_type: string;
  reasoning_summary: string;
  recommendation: Record<string, unknown>;
  confidence: number;
}

export interface AiChatResponse {
  reply: string;
  actions: AiAction[];
  decisions: AiDecision[];
  task_id: string | null;
}

export interface Approval {
  id: string;
  channel_id: string | null;
  action_type: string;
  target_id: string | null;
  proposed_change: Record<string, unknown>;
  reason: string;
  risk_level: string;
  status: string;
  created_at: string | null;
  approved_at: string | null;
}

export interface AuditEntry {
  id: string;
  user_id: string | null;
  channel_id: string | null;
  action: string;
  target: string | null;
  result: string | null;
  metadata: Record<string, unknown>;
  created_at: string | null;
}

export interface ContentPlanItem {
  id: string;
  channel_id: string;
  title: string;
  description: string | null;
  idea: string | null;
  target_keyword: string | null;
  status: string;
  planned_date: string | null;
  publish_date: string | null;
  notes: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface Comment {
  id: string;
  video_id: string;
  video_title: string;
  author: string;
  text: string;
  like_count: number;
  published_at: string | null;
  sentiment: string | null;
}

export interface Playlist {
  id: string;
  title: string;
  description: string;
  item_count: number;
  thumbnail_url: string;
}

export interface PlaylistItem {
  playlist_item_id: string;
  video_id: string;
  title: string;
  thumbnail_url: string;
  published_at: string | null;
}

export interface ScoreWeights {
  ctr: number;
  retention: number;
  views_velocity: number;
  subscriber_conversion: number;
  watch_time: number;
  engagement: number;
}

export interface Settings {
  ai: { model: string; enabled: boolean };
  notifications: { telegram_enabled: boolean };
  score_weights: ScoreWeights;
  ranges_supported: string[];
}

export interface HealthCheck {
  status: string;
  app: string;
  checks: {
    backend: string;
    database: string;
    youtube_api: string;
    ai_provider: string;
    redis: string;
  };
}

export interface DashboardData {
  summary: {
    channels: number;
    videos: number;
    views: number;
    subscribers: number;
    watch_time_seconds: number;
    revenue: number | null;
  };
  growth: Growth;
  top_videos: Video[];
  underperforming_videos: Video[];
  ai_recommendations: Array<{ text: string; action: string }>;
  pending_approvals: Array<{
    id: string;
    action_type: string;
    risk_level: string;
    reason: string;
    created_at: string | null;
  }>;
  recent_actions: Array<{
    id: string;
    action: string;
    target: string | null;
    result: string | null;
    created_at: string | null;
  }>;
  system_health: HealthCheck["checks"];
}

export interface ApiErrorBody {
  success: boolean;
  error?: { code: string; message: string };
}

export interface Paginated<T> {
  items: T[];
  total: number;
  hidden_count?: number;
}
