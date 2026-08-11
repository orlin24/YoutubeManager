import axios, { AxiosError } from "axios";
import type {
  AiChatResponse,
  AnalyticsResponse,
  Approval,
  AuditEntry,
  Channel,
  ChannelProfile,
  Comment,
  ContentPlanItem,
  DashboardData,
  HealthCheck,
  Paginated,
  Playlist,
  PlaylistItem,
  Settings,
  User,
  Video,
} from "../types";

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(code: string, message: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

export const client = axios.create({
  baseURL: (import.meta.env.VITE_API_URL as string) || "/api",
  withCredentials: true,
  timeout: 120_000,
});

// silent session refresh: when the access token expires (60 min) any 401 first
// tries POST /auth/refresh (refresh cookie, 30 days) before giving up.
let _refreshing: Promise<boolean> | null = null;

function tryRefreshSession(): Promise<boolean> {
  if (!_refreshing) {
    _refreshing = axios
      .post("/api/auth/refresh", {}, { withCredentials: true, timeout: 15_000 })
      .then(() => true)
      .catch(() => false)
      .finally(() => {
        _refreshing = null;
      });
  }
  return _refreshing;
}

client.interceptors.response.use(
  (resp) => resp,
  async (error: AxiosError) => {
    const status = error.response?.status ?? 0;
    const url = error.config?.url ?? "";
    const retried = (error.config as { _retried?: boolean } | undefined)?._retried;
    if (status === 401 && !retried && !url.includes("/auth/login") && !url.includes("/auth/refresh")) {
      const ok = await tryRefreshSession();
      if (ok) {
        const cfg = { ...error.config, _retried: true };
        return client.request(cfg);
      }
      // refresh failed -> session really expired
      window.dispatchEvent(new CustomEvent("auth:expired"));
    }
    const body = error.response?.data as { error?: { code?: string; message?: string } } | undefined;
    const code = body?.error?.code ?? (status === 0 ? "NETWORK_ERROR" : "REQUEST_FAILED");
    const message =
      body?.error?.message ??
      (status === 0 ? "Cannot reach the server." : `Request failed (${status}).`);
    return Promise.reject(new ApiError(code, message, status));
  }
);

async function unwrap<T>(promise: Promise<{ data: T }>): Promise<T> {
  const resp = await promise;
  return resp.data;
}

export const api = {
  get: <T>(path: string, params?: Record<string, unknown>) =>
    unwrap<T>(client.get(path, { params })),
  post: <T>(path: string, body?: unknown, config?: { headers?: Record<string, string> }) =>
    unwrap<T>(client.post(path, body, config)),
  patch: <T>(path: string, body?: unknown) => unwrap<T>(client.patch(path, body)),
  delete: <T>(path: string) => unwrap<T>(client.delete(path)),
};

// ---- health ----
export const fetchHealth = () => api.get<HealthCheck>("/health");

// ---- auth ----
export const login = (email: string, password: string) =>
  api.post<{ user: User; access_token: string }>("/auth/login", { email, password });
export const fetchSetupStatus = () => api.get<{ setup_required: boolean }>("/auth/setup-status");
export const setupAccount = (name: string, email: string, password: string) =>
  api.post<{ user: User; access_token: string }>("/auth/setup", { name, email, password });
export const logout = () => api.post<{ success: boolean }>("/auth/logout");
export const fetchMe = () =>
  api.get<{ user: User; accounts: Array<{ id: string; channel_id: string; channel_title: string; channel_thumbnail: string; google_account_email: string; connected_at: string | null }> }>("/auth/me");

// ---- dashboard ----
export const fetchDashboard = (channelId?: string | null) =>
  api.get<DashboardData>("/dashboard", { channel_id: channelId ?? undefined });

// ---- channels ----
export const fetchChannels = () => api.get<Paginated<Channel>>("/channels");
export const fetchChannel = (id: string) => api.get<Channel>(`/channels/${id}`);
export const refreshChannel = (id: string) => api.post<{ success: boolean; synced_at: string }>(`/channels/${id}/refresh`);
export const fetchChannelVideos = (id: string, q?: Record<string, unknown>) =>
  api.get<Paginated<Video>>(`/channels/${id}/videos`, q);
export const fetchChannelProfile = (id: string) => api.get<ChannelProfile>(`/channels/${id}/profile`);
export const updateChannelProfile = (id: string, data: Partial<ChannelProfile>) =>
  api.patch<ChannelProfile>(`/channels/${id}/profile`, data);
export const disconnectAccount = (accountId: string) =>
  api.post<{ success: boolean }>("/youtube/disconnect", { account_id: accountId });

// ---- videos ----
export const fetchVideos = (q?: Record<string, unknown>) => api.get<Paginated<Video>>("/videos", q);
export const fetchVideo = (id: string) => api.get<Video>(`/videos/${id}`);
export const updateVideo = (id: string, data: Partial<Video>) =>
  api.patch<Video | { requires_approval: boolean; approval_id: string }>(`/videos/${id}`, data);
export const analyzeVideo = (id: string) =>
  api.post<{ score: number | null; strengths: string[]; weaknesses: string[]; explanation: string; ai: boolean; video: Video }>(`/videos/${id}/analyze`);
export const analyzeAllVideos = (channelId?: string) =>
  api.post<{ scored: number; with_score: number; without: number }>(
    `/videos/analyze-all${channelId ? `?channel_id=${encodeURIComponent(channelId)}` : ""}`
  );
export const uploadVideo = (formData: FormData) =>
  api.post<Video | { requires_approval: boolean; approval_id: string; video?: Video }>(
    "/videos/upload",
    formData,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
export const deleteVideo = (id: string) => api.delete<{ success: boolean; deleted: boolean }>(`/videos/${id}`);
export const uploadThumbnail = (id: string, formData: FormData) =>
  api.post<{ success: boolean; video: Video }>(`/videos/${id}/thumbnail`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });

export interface UploadStatus {
  status: "queued" | "receiving" | "preparing" | "uploading" | "finalizing" | "completed" | "failed" | "paused";
  progress: number;
  message: string;
  received_bytes?: number;
  total_bytes?: number;
  result?:
    | Video
    | { requires_approval: boolean; approval_id: string; video?: Video; thumbnail_warning?: string };
  error_code?: string;
  error?: string;
}

export const uploadVideoWithProgress = (
  formData: FormData,
  onProgress: (percent: number) => void
): Promise<{ upload_id: string; queued: boolean }> =>
  client
    .post<{ upload_id: string; queued: boolean }>("/videos/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 0, // long uploads - no client timeout
      onUploadProgress: (e) => {
        if (e.total) onProgress(Math.round((e.loaded / e.total) * 100));
      },
    })
    .then((r) => r.data);

// ---- resumable (chunked) upload ----
export const uploadVideoInit = (formData: FormData) =>
  client
    .post<{ upload_id: string; received_bytes: number }>("/videos/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 0,
    })
    .then((r) => r.data);

export const uploadVideoChunk = (uploadId: string, chunk: Blob) => {
  const form = new FormData();
  form.append("upload_id", uploadId);
  form.append("chunk", chunk, "chunk.bin");
  return client
    .post<{ upload_id: string; received_bytes: number; total_bytes: number }>(
      "/videos/upload-chunk",
      form,
      { headers: { "Content-Type": "multipart/form-data" }, timeout: 0 }
    )
    .then((r) => r.data);
};

export const uploadVideoFinalize = (uploadId: string) =>
  api.post<{ upload_id: string; started: boolean }>("/videos/upload-finalize", { upload_id: uploadId });

export const uploadVideoResume = (uploadId: string) =>
  api.post<{ upload_id: string; resumed: boolean }>("/videos/upload-resume", { upload_id: uploadId });

export const uploadVideoCancel = (uploadId: string) =>
  api.post<{ success: boolean }>("/videos/upload-cancel", { upload_id: uploadId });

export const fetchUploadStatus = (uploadId: string) =>
  api.get<UploadStatus>(`/videos/upload-status/${uploadId}`);

// ---- analytics ----
export const fetchAnalytics = (channelId: string, range: string, start?: string, end?: string) =>
  api.get<AnalyticsResponse>("/analytics/channel", { channel_id: channelId, range, start, end });
export const fetchVideoAnalytics = (videoId: string) =>
  api.get<{ overview: Record<string, unknown>; timeseries: unknown[]; video: Record<string, unknown> }>(
    `/analytics/video/${videoId}`
  );
export const fetchRealtimeViews = (channelId: string) =>
  api.get<{
    items: Array<{ date: string; views: number; watch_time_seconds: number }>;
    disclaimer: string;
  }>("/analytics/realtime", { channel_id: channelId });
export const fetchTrafficSources = (channelId: string) =>
  api.get<{
    items: Array<{ source: string; label: string; views: number; percent: number }>;
    total_views: number;
  }>("/analytics/traffic-sources", { channel_id: channelId });

// ---- comments ----
export const fetchComments = (q?: Record<string, unknown>) => api.get<Paginated<Comment>>("/comments", q);
export const replyComment = (commentId: string, channelId: string, text: string) =>
  api.post<{ id: string; text: string }>(`/comments/${commentId}/reply?channel_id=${channelId}`, { text });

export const aiCommentDraft = (
  channelId: string,
  commentText: string,
  author: string,
  videoTitle?: string
) =>
  api.post<{ draft: string }>("/comments/ai-draft", {
    channel_id: channelId,
    comment_text: commentText,
    author,
    video_title: videoTitle ?? "",
  });

// ---- playlists ----
export const fetchPlaylists = (channelId: string) =>
  api.get<Paginated<Playlist>>("/playlists", { channel_id: channelId });
export const createPlaylist = (channelId: string, title: string, description: string) =>
  api.post<Playlist>(`/playlists?channel_id=${channelId}`, { title, description });
export const updatePlaylist = (playlistId: string, channelId: string, data: { title?: string; description?: string }) =>
  api.patch<Playlist>(`/playlists/${playlistId}?channel_id=${channelId}`, data);
export const fetchPlaylistItems = (playlistId: string, channelId: string) =>
  api.get<Paginated<PlaylistItem>>(`/playlists/${playlistId}/items`, { channel_id: channelId });
export const addPlaylistItem = (playlistId: string, channelId: string, videoId: string) =>
  api.post<{ added: boolean }>(`/playlists/${playlistId}/items?channel_id=${channelId}`, { video_id: videoId });

// ---- AI ----
export const sendAiChat = (channelId: string, message: string) =>
  api.post<AiChatResponse>("/ai/chat", { channel_id: channelId, message });

export const executeAiAction = (
  channelId: string,
  actionId: string,
  params: Record<string, unknown> = {}
) =>
  api.post<{ approved: boolean; approval_id?: string; message?: string; result?: unknown }>(
    "/ai/actions/execute",
    { channel_id: channelId, action_id: actionId, params }
  );
export const analyzeChannel = (channelId: string, instruction?: string) =>
  api.post<Record<string, unknown>>("/ai/analyze-channel", { channel_id: channelId, instruction });
export const analyzeVideoAi = (videoId: string) =>
  api.post<Record<string, unknown>>("/ai/analyze-video", { video_id: videoId });
export const generateTitles = (payload: { video_id?: string; topic?: string; channel_id?: string }) =>
  api.post<{ titles: string[] }>("/ai/generate-titles", payload);
export const generateDescription = (payload: { title?: string; topic?: string; channel_id?: string }) =>
  api.post<{ description: string }>("/ai/generate-description", payload);
export const generateSeo = (payload: { title?: string; description?: string; channel_id?: string }) =>
  api.post<{ keywords: string[]; tags: string[]; ai: boolean }>("/ai/generate-seo", payload);
export const generateContentPlan = (payload: { channel_id: string; days?: number; instruction?: string }) =>
  api.post<{ summary: string; items: Array<{ id: string; title: string }> }>("/ai/content-plan", payload);

export interface ContentPatternRec {
  title: string;
  description: string;
  target_keyword: string;
  reason: string;
}

export const generateContentPatterns = (channelId: string, days = 28) =>
  api.post<{
    analysis: string;
    recommendations: ContentPatternRec[];
    saved: Array<{ id: string; title: string; status: string; publish_date: string }>;
  }>("/ai/content-patterns", { channel_id: channelId, days });
export const fetchDailyReport = (channelId?: string) =>
  api.post<Record<string, unknown>>("/ai/daily-report", { channel_id: channelId });
export const fetchAiTasks = (q?: Record<string, unknown>) => api.get<Paginated<Record<string, unknown>>>("/ai/tasks", q);

// ---- approvals ----
export const fetchApprovals = (q?: Record<string, unknown>) => api.get<Paginated<Approval>>("/approvals", q);
export const getApproval = (id: string) => api.get<Approval>(`/approvals/${id}`);
export const approveApproval = (id: string) => api.post<{ success: boolean }>(`/approvals/${id}/approve`);
export const rejectApproval = (id: string) => api.post<{ success: boolean }>(`/approvals/${id}/reject`);

// ---- audit ----
export const fetchAudit = (q?: Record<string, unknown>) => api.get<Paginated<AuditEntry>>("/audit", q);

// ---- content plan ----
export const fetchContentPlan = (q?: Record<string, unknown>) =>
  api.get<Paginated<ContentPlanItem>>("/content-plan", q);
export const createContentPlan = (data: Partial<ContentPlanItem> & { channel_id: string }) =>
  api.post<ContentPlanItem>("/content-plan", data);
export const updateContentPlan = (id: string, data: Partial<ContentPlanItem>) =>
  api.patch<ContentPlanItem>(`/content-plan/${id}`, data);
export const deleteContentPlan = (id: string) => api.delete<{ success: boolean }>(`/content-plan/${id}`);

// ---- settings ----
export const fetchSettings = () => api.get<Settings>("/settings");
export const updateSettings = (data: Partial<Settings>) => api.patch<Settings>("/settings", data);

export interface CredentialsStatus {
  google: { configured: boolean; source: "web" | "env" | "none"; has_client_id: boolean };
  ai: { configured: boolean; source: "web" | "env" | "none"; has_api_key: boolean };
  note: string;
}

export const fetchCredentialsStatus = () => api.get<CredentialsStatus>("/settings/credentials/status");
export const saveGoogleCredentials = (clientId: string, clientSecret: string) =>
  api.patch<{ success: boolean; configured: boolean; message: string }>("/settings/credentials/google", {
    client_id: clientId,
    client_secret: clientSecret,
  });
export const saveAiCredentials = (data: { api_key: string; model?: string; base_url?: string }) =>
  api.patch<{ success: boolean; configured: boolean; message: string }>("/settings/credentials/ai", data);

export const googleAuthUrl = () => "/api/auth/google";

// ---- Telegram ----
export const saveTelegramCredentials = (botToken: string, chatId: string) =>
  api.patch<{ success: boolean; message: string }>("/settings/credentials/telegram", {
    bot_token: botToken,
    chat_id: chatId,
  });

export const testTelegram = () =>
  api.post<{ success: boolean; message: string }>("/settings/telegram/test");

// ---- backup & restore ----
export interface BackupRestoreResult {
  success: boolean;
  restored: Record<string, number>;
  note?: string;
}

export const exportBackup = async (password?: string): Promise<{ blob: Blob; filename: string }> => {
  const resp = await client.post<Blob>(
    "/backup/export",
    { password: password ?? "" },
    { responseType: "blob" }
  );
  const cd = (resp.headers["content-disposition"] as string) ?? "";
  const match = /filename="?([^";]+)"?/.exec(cd);
  const filename = match?.[1] ?? "ai-youtube-manager-backup.json";
  return { blob: resp.data, filename };
};

export const restoreBackup = (file: File, password?: string) => {
  const form = new FormData();
  form.append("file", file);
  form.append("password", password ?? "");
  return api.post<BackupRestoreResult>("/backup/restore", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};

// ---- channel lifecycle / portfolio ----
export interface LifecycleWinner {
  category: string;
  title: string;
  data: Record<string, unknown>;
  confidence: string;
  note?: string;
}

export interface LifecycleRisk {
  level: string;
  reason: string;
  duplicate_titles: string[];
}

export interface LifecyclePriority {
  priority: string;
  title: string;
  reason: string;
}

export interface LifecycleData {
  detected: boolean;
  channel_id: string;
  mode: string;
  mode_label: string;
  objective: string;
  health_score: number | null;
  growth_pct: number | null;
  detected_at?: string | null;
  kpis?: {
    subscribers: number;
    views_28d: number;
    growth_pct: number | null;
    watch_hours_28d?: number | null;
    likes_28d: number;
    comments_28d: number;
    videos_total: number;
    estimated_revenue?: number;
  };
  winners?: LifecycleWinner[];
  risk?: LifecycleRisk;
  priorities?: LifecyclePriority[];
}

export interface PortfolioChannel {
  channel_id: string;
  title: string;
  mode: string;
  mode_label: string;
  health_score: number | null;
  growth_pct: number | null;
  subscribers: number | null;
  views_28d: number | null;
  detected_at?: string | null;
}

export interface PortfolioOverview {
  by_mode: Record<string, number>;
  total: number;
  channels: PortfolioChannel[];
  labels: Record<string, string>;
  objectives: Record<string, string>;
}

export const fetchChannelLifecycle = (channelId: string) =>
  api.get<LifecycleData>(`/channels/${channelId}/lifecycle`);
export const analyzeChannelLifecycle = (channelId: string) =>
  api.post<LifecycleData>(`/channels/${channelId}/analyze`);
export const fetchChannelPatterns = (channelId: string) =>
  api.get<{ items: Array<{ pattern_type: string; title: string; confidence: string; data: unknown; created_at: string }> }>(
    `/channels/${channelId}/patterns`
  );
export const fetchPortfolio = () => api.get<PortfolioOverview>("/portfolio/overview");
export const fetchPortfolioPriorities = () =>
  api.get<{ items: Array<{ channel_id: string; channel_title: string; mode: string; priority: string; title: string; reason: string }> }>(
    "/portfolio/priorities"
  );

// ---- autonomous AI employee ----
export interface AutoStatus {
  status: string;
  mode: string;
  enabled: boolean;
  dry_run: boolean;
  emergency_stop: boolean;
  check_interval_minutes: number;
  max_actions_per_day: number;
  last_cycle: string | null;
  tasks_today: number;
  completed_today: number;
  failed_today: number;
  waiting_approvals: number;
  pending: number;
}

export const fetchAutoStatus = () => api.get<AutoStatus>("/ai/autonomous/status");
export const setAutoMode = (mode: string) =>
  api.post<{ success: boolean; mode: string }>("/ai/autonomous/mode", { mode });
export const setAutoDryRun = (dryRun: boolean) =>
  api.post<{ success: boolean; dry_run: boolean }>("/ai/autonomous/dry-run", { dry_run: dryRun });
export const runAutoNow = () => api.post<{ status: string; tasks_created: number; tasks_executed: number }>("/ai/autonomous/run-now");
export const emergencyStop = () => api.post<{ success: boolean; status: string }>("/ai/emergency-stop");
export const emergencyResume = () => api.post<{ success: boolean; status: string }>("/ai/emergency-resume");
export const fetchAutoTasks = (status = "") =>
  api.get<{ items: Array<{ id: string; channel_id: string; task_type: string; instruction: string; priority: number; risk_level: string; status: string; error?: string | null; created_at?: string | null }> }>(
    `/ai/autonomous/tasks${status ? `?status=${status}` : ""}`
  );

// ---- content factory + CEO ----
export const runContentPipeline = (channelId: string, count = 3, dryRun = false) =>
  api.post<{ ideas: Array<{ idea: string; quality: string; score: number; queue_id: string | null }>; queued: number; dry_run: boolean; note?: string }>(
    "/content-factory/pipeline",
    { channel_id: channelId, count, dry_run: dryRun }
  );
export const generateIdeas = (channelId: string, count = 6) =>
  api.post<{ ideas: Array<{ id: string; topic: string; angle: string; format: string; reason: string; confidence: string; content_type: string; priority: number }> }>(
    "/content-factory/ideas",
    { channel_id: channelId, count }
  );
export const fetchFactoryQueue = (channelId: string) =>
  api.get<{ items: Array<{
    id: string;
    title: string;
    content_type: string;
    status: string;
    priority: number;
    publish_date?: string | null;
    notes: string;
    brief: {
      title_variants?: string[];
      thumbnail_concept?: string;
      thumbnail_variants?: string[];
      script_title?: string;
      script_hook?: string;
      script_outline?: unknown;
      keywords?: string[];
      hook?: string;
      audience?: string;
      duration?: string;
      quality_score?: number | null;
      quality_result?: string | null;
    };
  }> }>(
    `/content-factory/queue?channel_id=${channelId}`
  );
export const advanceQueueItem = (queueId: string) =>
  api.post<{ id: string; status: string; publish_date?: string | null }>(
    `/content-factory/queue/${queueId}/advance`
  );
export const buildCalendar = (channelId: string, days = 7) =>
  api.post<{ plan: Array<{ date: string; title: string; content_type: string; status: string; priority: number; queue_id: string }> }>(
    "/content-factory/calendar",
    { channel_id: channelId, days }
  );
export const fetchProviders = () =>
  api.get<{ music: unknown; image: unknown; video: unknown; voice: unknown; storage: unknown }>("/content-factory/providers");
export const fetchCeoOverview = () =>
  api.get<{ total_channels: number; by_mode: Record<string, number>; monetized: number; revenue: number | null; views: number; subscribers: number; content_produced: number; content_published: number; ai_actions: number }>("/ceo/overview");
export const fetchCeoPriorities = () => api.get<{ items: Array<{ channel: string; priority: string; title: string; reason: string }> }>("/ceo/priorities");
export const fetchCeoOpportunities = () => api.get<{ items: Array<{ channel: string; type: string; title: string; confidence: string }> }>("/ceo/opportunities");
export const fetchCeoRisks = () => api.get<{ items: Array<{ channel: string; level: string; title: string }> }>("/ceo/risks");
export const fetchCeoRecommendation = () => api.get<{ channel: string; decision: string; reason: string; confidence: string }>("/ceo/recommendation");
export const fetchCeoAllocation = () => api.get<{ items: Array<{ channel: string; mode: string; share: number }> }>("/ceo/allocation");
export const fetchCeoScorecard = () =>
  api.get<{ portfolio_health: number | null; growth: number | null; revenue: number | null; content_efficiency: number | null; experimentation: number | null; risk: string }>("/ceo/scorecard");
export const sendCeoTelegram = () => api.post<{ success: boolean; message: string }>("/ceo/telegram");

// ---- business intelligence ----
export const fetchBiOverview = () =>
  api.get<{ generated_at: string | null; per_channel: Array<Record<string, unknown>>; risks: Array<Record<string, string>>; opportunities: Array<Record<string, unknown>>; allocation: { items?: Array<Record<string, unknown>> } }>("/bi/overview");
export const refreshBi = () => api.post<{ success: boolean; generated_at: string | null }>("/bi/refresh");
export const simulateBi = (payload: { name: string; uploads_per_week?: number | null; capacity_shift_pct?: number; elasticity?: number }) =>
  api.post<{ scenario_name: string; model_estimate: boolean; best_case: { views_delta_pct: number }; base_case: { views_delta_pct: number }; worst_case: { views_delta_pct: number }; production_load_delta_pct: number; risk: string; confidence: number; assumptions: string }>("/bi/simulate", payload);
export const fetchBiStrategy = () => api.get<{ items: Array<{ question: string; answer: string }> }>("/bi/strategy");
export const fetchBiAccuracy = () =>
  api.get<{ status: string; count: number; mape_pct?: number; bias_pct?: number; model_version?: string }>("/bi/accuracy");
