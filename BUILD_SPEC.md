# BUILD_SPEC.md — AI YouTube Manager (single source of truth)

Project root: `/Users/joss/Documents/YOUTUBE MANAGER` (the app lives directly here:
`backend/`, `frontend/`, `nginx/`, `systemd/`, `scripts/`, `docs/`, plus root-level
`README.md`, `docker-compose.yml`, `.gitignore`, `BUILD_SPEC.md`).

This file pins the API contract, DB model, env vars, frontend contract and AI
system so that multiple parallel workers produce consistent code. Read it fully
before writing any code. Do NOT invent new endpoints/models/naming; if something
is missing, follow the existing conventions and note it in your summary.

---

## 0. GLOBAL CONVENTIONS

- All Python is type-annotated. SQLAlchemy 2.0 style (`Mapped`, `mapped_column`).
- All datetimes are timezone-aware UTC (`datetime.now(timezone.utc)`).
- No hardcoded secrets anywhere. Everything from env (pydantic-settings).
- No fake data pretending to be from YouTube. If YouTube/AI is not configured,
  return a clear error or `null`/`[]`, never invented numbers.
- Error envelope (HTTP 4xx/5xx), ALWAYS:
  ```json
  { "success": false, "error": { "code": "SOME_CODE", "message": "human text" } }
  ```
  Codes use SCREAMING_SNAKE e.g. `YOUTUBE_AUTH_EXPIRED`, `NOT_CONFIGURED`,
  `UNAUTHORIZED`, `NOT_FOUND`, `VALIDATION_ERROR`, `AI_NOT_CONFIGURED`,
  `RATE_LIMITED`, `FORBIDDEN`.
- Success responses return the resource JSON directly (no wrapper), except
  list endpoints which return `{ "items": [...], "total": N }`.
- Never leak tracebacks to clients; log them server-side (structured logging).
- Never log secrets/tokens. Frontend never sees tokens in responses (only
  transiently via httpOnly cookie; `access_token` may also be returned in the
  auth response body for API clients, but the SPA relies on cookies).
- Structured logging module `app/utils/logging.py`: `get_logger(name)` returning
  a stdlib logger configured with JSON-ish structured formatter; INFO/WARNING/ERROR.

## 1. ENV VARS (backend/.env.example must mirror this)

```
APP_NAME=AI YouTube Manager
APP_ENV=development            # development | production
APP_HOST=0.0.0.0
APP_PORT=5000
APP_ORIGINS=http://localhost:5173,http://localhost:5000
DATABASE_URL=postgresql+psycopg://localhost:5432/ai_youtube_manager
SECRET_KEY=                    # required in production; dev generates ephemeral if empty
TOKEN_ENCRYPTION_KEY=          # Fernet key; if empty derive from SECRET_KEY
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=30
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:5000/api/auth/google/callback
AI_API_KEY=
AI_MODEL=gpt-4o-mini
AI_BASE_URL=https://api.openai.com/v1
AI_ENABLED=false               # set true when AI_API_KEY present
REDIS_URL=
FRONTEND_URL=http://localhost:5000
LOG_LEVEL=INFO
```

`config.py` (pydantic-settings, env prefix none) must expose all of these with
sane defaults. `AI_ENABLED` should be computed `AI_ENABLED = bool(AI_API_KEY)`.

## 2. DATABASE MODELS (SQLAlchemy, table names exactly as below)

`app/models/` — one module per table: `user.py, youtube_account.py, channel.py,
video.py, analytics_snapshot.py, ai_task.py, ai_decision.py, approval_request.py,
audit_log.py, content_plan_item.py, channel_profile.py`. Also `base.py` with
`Base(DeclarativeBase)` and `uuid_pk()` helper (use `uuid.uuid4` string PKs for
all tables unless noted). `app/models/__init__.py` imports all so `Base.metadata`
is complete.

- `users`: id (PK, uuid str), email (unique, indexed), name, password_hash,
  created_at, updated_at. Relationship `accounts`, `audit_logs`.
- `youtube_accounts`: id (uuid PK), user_id (FK users, indexed), google_account_email,
  channel_id (unique), channel_title, channel_description, channel_thumbnail,
  access_token_encrypted, refresh_token_encrypted, token_expiry (nullable dt),
  created_at, updated_at. Unique constraint on (user_id, channel_id). Relationship to channel.
- `channels`: id (uuid PK), youtube_account_id (FK youtube_accounts, unique),
  channel_id (str, unique, indexed), title, description, thumbnail_url,
  subscriber_count (int default 0), view_count, video_count, created_at, updated_at.
  Relationships: `videos`, `snapshots`, `profile`, `content_plan_items`.
- `videos`: id (uuid PK), channel_id (FK channels, indexed), youtube_video_id
  (indexed), title, description, published_at (nullable dt), duration_seconds (int
  nullable), view_count, like_count, comment_count, privacy_status (str default
  'private'), ctr (float nullable), average_view_duration_seconds (float nullable),
  ai_score (float nullable, 0-100), thumbnail_url (nullable str), created_at,
  updated_at. Unique constraint (channel_id, youtube_video_id).
- `analytics_snapshots`: id (uuid PK), channel_id (FK), video_id (FK, nullable),
  date (Date), views (int), watch_time_seconds (float), average_view_duration_seconds
  (float), likes (int), comments (int), shares (int), subscribers_gained (int),
  subscribers_lost (int), estimated_revenue (float nullable), created_at.
  Unique constraint (channel_id, video_id, date) — snapshots are upserted
  (INSERT ... ON CONFLICT DO UPDATE), guaranteeing idempotent sync.
- `ai_tasks`: id (uuid PK), channel_id (FK, nullable), task_type (str), instruction
  (Text), status (str: queued|running|completed|failed|cancelled), priority (int
  default 5), result (JSON nullable), created_at, completed_at (nullable).
- `ai_decisions`: id (uuid PK), channel_id (FK, nullable), task_id (FK ai_tasks,
  nullable), decision_type (str), reasoning_summary (Text), recommendation (JSON),
  confidence (float 0-1), created_at. NEVER stores chain-of-thought, only summaries.
- `approval_requests`: id (uuid PK), channel_id (FK, nullable), action_type (str:
  publish_video|delete_video|change_visibility|update_metadata|upload_video|...),
  target_id (str nullable), proposed_change (JSON), reason (Text), risk_level
  (str: LOW|MEDIUM|HIGH), status (str: pending|approved|rejected|cancelled),
  created_at, approved_at (nullable), resolved_by_user_id (FK users nullable).
- `audit_logs`: id (uuid PK), user_id (FK users nullable), channel_id (FK nullable),
  action (str), target (str nullable), result (str nullable), metadata (JSON),
  created_at.
- `content_plan_items`: id (uuid PK), channel_id (FK, indexed), title, description
  (Text nullable), idea (Text nullable), target_keyword (str nullable), status
  (str default 'IDEA'; one of IDEA|DRAFT|READY|APPROVAL|SCHEDULED|PUBLISHED|CANCELLED),
  planned_date (Date nullable), publish_date (Date nullable), notes (Text nullable),
  created_at, updated_at.
- `channel_profiles` (AI memory): id (uuid PK), channel_id (FK, unique), niche,
  target_audience, language, country, content_style, upload_frequency,
  brand_rules (Text nullable), successful_titles (JSON), failed_topics (JSON),
  historical_performance (JSON), updated_at. All str/JSON nullable.

Migration `alembic/versions/0001_initial.py` must create exactly these tables
(hardcoded DDL written from this spec, since it is generated in parallel with models).
Indexes: users.email unique; youtube_accounts.channel_id unique; channels.channel_id
unique; videos (channel_id, youtube_video_id) unique; analytics_snapshots
(channel_id, video_id, date) unique; channel_profiles.channel_id unique; FKs named.

## 3. BACKEND LAYOUT & RESPONSIBILITIES

```
backend/
  requirements.txt          # pinned-ish, Python 3.11+
  .env.example
  pytest.ini
  alembic.ini, alembic/env.py, alembic/versions/0001_initial.py
  app/
    main.py                 # create_app(), mounts routers under /api, serves
                            # frontend/dist statically at / if it exists, CORS,
                            # exception handlers -> error envelope, startup tasks
    config.py               # Settings (pydantic-settings)
    database.py             # engine, SessionLocal, get_db dependency, Base import
    models/... schemas/... security/... utils/...
    auth/                   # jwt.py (encode/decode), deps.py (get_current_user,
                            #   get_current_account), password.py (bcrypt)
    services/               # youtube_service, oauth, analytics_service, audit_service,
                            #   notification_service, encryption, approval_service
    youtube/                # client.py (google build factory + token refresh + error map)
    analytics/              # engine.py (snapshot agg, ranges, top/worst, growth)
    agents/                 # registry.py, tools.py, permissions.py, decision_engine.py
    ai/                     # provider.py, service.py, memory.py, chat.py (command->tools)
    prompts/system/*.txt    # agent system prompts (plain text files)
    routers/                # health, auth, youtube, channels, videos, analytics,
                            #   comments, playlists, ai, approvals, audit,
                            #   dashboard, content_plan, settings
    tasks/                  # scheduler.py (asyncio loop: hourly channel sync,
                            #   6h video analytics sync, daily AI report)
    utils/                  # logging.py, errors.py (AppError), rate_limit.py,
                            #   security_headers middleware helpers
  tests/                    # conftest.py, test_health.py, test_auth.py,
                            #   test_approval_flow.py, test_decision_engine.py,
                            #   test_permissions.py, test_audit.py
```

requirements.txt (worker 0 owns it) must include: fastapi, uvicorn[standard],
gunicorn, sqlalchemy>=2.0, alembic, psycopg[binary], pydantic>=2, pydantic-settings,
PyJWT, bcrypt, cryptography, python-multipart, httpx, google-api-python-client,
google-auth, python-dateutil, apscheduler (or plain asyncio loop), pytest,
pytest-asyncio, httpx (tests use fastapi TestClient). DO NOT add anything exotic.

`main.py` MUST import and include these router modules exactly:
`health, auth, youtube, channels, videos, analytics, comments, playlists, ai,
approvals, audit, dashboard, content_plan, settings` (from `app.routers`).
Router prefixes (all under the global `/api` prefix in main):
- health: `/api/health`
- auth: `/api/auth`
- youtube: `/api/youtube`
- channels: `/api/channels`
- videos: `/api/videos`
- analytics: `/api/analytics`
- comments: `/api/comments`
- playlists: `/api/playlists`
- ai: `/api/ai`
- approvals: `/api/approvals`
- audit: `/api/audit`
- dashboard: `/api/dashboard`
- content_plan: `/api/content-plan`
- settings: `/api/settings`

## 4. AUTH & SECURITY

- Passwords: bcrypt (`bcrypt.hashpw`/`checkpw`, no passlib).
- JWT: PyJWT, HS256, `SECRET_KEY`, claims: sub=user_id, exp, type=access|refresh.
- Cookies: `aym_access` (httpOnly, SameSite=Lax, Secure only when APP_ENV=production,
  path=/), `aym_refresh` (httpOnly, SameSite=Lax, path=/api/auth). Access token
  also returned in auth response body as `access_token`.
- Auth dependency: `get_current_user` reads `Authorization: Bearer <token>` OR the
  `aym_access` cookie. 401 envelope `UNAUTHORIZED` if missing/invalid.
- CSRF: for mutating methods (POST/PATCH/PUT/DELETE) when the request carries the
  cookie AND an `Origin` header, verify Origin is in `APP_ORIGINS`. 403 `FORBIDDEN`
  otherwise. (SameSite=Lax already blocks cross-site POSTs; this is defense in depth.)
- Rate limiting: `app/utils/rate_limit.py` — in-memory sliding window per
  (ip, route) for auth + ai endpoints (e.g. 10/min auth, 30/min ai). Returns 429
  `RATE_LIMITED`.
- Security headers middleware: X-Content-Type-Options, X-Frame-Options DENY,
  Referrer-Policy, and CSP allowing self + inline styles (Tailwind) for the SPA.
- Token encryption: Fernet. Key = TOKEN_ENCRYPTION_KEY or derived from SECRET_KEY
  (sha256). `services/encryption.py`: `encrypt_str/decrypt_str`.
- `app/security/` empty is fine; put auth in `app/auth/` as listed above.

## 5. API ENDPOINTS (exact contract)

### health — GET /api/health
200: `{"status":"ok","app":"AI YouTube Manager","checks":{"backend":"ok",
"database":"ok|error","youtube_api":"configured|not_configured|error",
"ai_provider":"configured|not_configured","redis":"not_configured"}}` — never 500
when credentials missing; report `not_configured`.

### auth
- POST /api/auth/register `{email,name,password}` -> 201 `{user:{id,email,name},
  access_token}` + sets cookies. 409 `EMAIL_EXISTS` on dup.
- POST /api/auth/login `{email,password}` -> 200 same shape. 401 `INVALID_CREDENTIALS`.
- POST /api/auth/logout -> clears cookies, 200 `{success:true}`.
- GET /api/auth/me -> `{user:{id,email,name}, accounts:[{id,channel_id,
  channel_title,channel_thumbnail,google_account_email,connected_at}]}` (accounts
  from youtube_accounts, no tokens ever).

### youtube (Google OAuth + account management)
- GET /api/auth/google -> if GOOGLE_CLIENT_ID empty: 503 envelope `NOT_CONFIGURED`
  message exactly: `Google OAuth is not configured. Please configure
  GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.` Else 302 to Google consent with
  state (random, stored in signed cookie `aym_oauth_state`), scopes:
  `openid email profile`, `https://www.googleapis.com/auth/youtube.readonly`,
  `https://www.googleapis.com/auth/youtube.upload`,
  `https://www.googleapis.com/auth/youtube`,
  `https://www.googleapis.com/auth/yt-analytics.readonly`,
  `https://www.googleapis.com/auth/yt-analytics-monetary.readonly`.
- GET /api/auth/google/callback?code&state -> validate state, exchange code
  (httpx POST to https://oauth2.googleapis.com/token), fetch userinfo
  (https://oauth2.googleapis.com/oauth2/v3/userinfo), fetch channel
  (`https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&mine=true`),
  upsert youtube_account + channel, encrypt+store tokens, audit log, redirect
  (302) to `FRONTEND_URL` + `?connected=1`.
- POST /api/youtube/disconnect `{account_id}` -> deletes account + its channel
  (and related rows), audit log, 200 `{success:true}`.
- GET /api/youtube/accounts -> same list shape as /api/auth/me accounts.
- GET /api/youtube/status -> `{configured: bool}`.

### channels
- GET /api/channels -> `{items:[channel], total}` (channels of current user).
- GET /api/channels/{id} -> channel + profile (AI memory) + latest snapshot stats.
- POST /api/channels/{id}/refresh -> trigger sync (fetch channel stats + recent
  videos + store), 200 `{success:true, synced_at}`.
- GET /api/channels/{id}/videos?limit=&offset= -> `{items,total}`.
- GET /api/channels/{id}/profile -> AI memory object.
- PATCH /api/channels/{id}/profile -> update AI memory fields, audit log.

Channel JSON: `{id, channel_id, title, description, thumbnail_url,
subscriber_count, view_count, video_count, updated_at}`.

### videos
- GET /api/videos?channel_id=&search=&status=&sort=latest|views|ai_score&limit=&offset=
  -> `{items,total}`. Video JSON: `{id, youtube_video_id, title, description,
  thumbnail_url, published_at, duration_seconds, view_count, like_count,
  comment_count, privacy_status, ctr, average_view_duration_seconds, ai_score,
  channel_id}`.
- GET /api/videos/{id} -> single video.
- PATCH /api/videos/{id} `{title?,description?,privacy_status?}` -> WRITE action;
  update YouTube then DB; audit log; returns updated video. 403 if youtube not
  configured. Changing privacy_status to public => route through approval
  (create approval_request HIGH, do NOT apply until approved).
- POST /api/videos/upload (multipart: file, title, description, privacy_status
  default 'private', channel_id, publish_at optional) -> upload via YouTube
  resumable; privacy 'public' => approval flow instead (store draft, create
  approval_request with target upload); else upload immediately. Returns video or
  approval_request `{requires_approval:true, approval_id}`.
- DELETE /api/videos/{id} -> HIGH risk: create approval_request
  action_type=delete_video; do NOT delete until approved.
- POST /api/videos/{id}/analyze -> run AI/decision-engine analysis, store
  ai_score, audit log, return `{score, strengths[], weaknesses[], summary}`.
  If AI not configured, compute heuristic score from metrics and mark
  `ai:false`.

### analytics
- GET /api/analytics/channel?channel_id=&range=7d|28d|90d|365d|custom&start=&end=
  -> `{overview:{views,watch_time_seconds,subscribers_gained,subscribers_lost,
  likes,comments,shares,estimated_revenue,average_view_duration_seconds},
  timeseries:[{date,views,watch_time_seconds,subscribers_gained,estimated_revenue}],
  top_videos:[video...], worst_videos:[video...], growth:{views_delta,
  subscribers_delta, views_pct, subscribers_pct}}` — computed from snapshots;
  empty arrays when no data, never fake numbers.
- GET /api/analytics/video/{id} -> `{overview,timeseries}` for one video.

### comments
- GET /api/comments?channel_id=&video_id=&sort=newest|oldest&limit= -> `{items,total}`
  Comment JSON: `{id, video_id, video_title, author, text, like_count,
  published_at, sentiment?:null}`.
- POST /api/comments/{id}/reply `{text}` -> replies via YouTube, audit log.

### playlists
- GET /api/playlists?channel_id= -> `{items,total}`. Playlist JSON `{id,
  youtube_playlist_id, title, description, item_count, thumbnail_url}`.
- POST /api/playlists `{title,description}` (WRITE, direct).
- PATCH /api/playlists/{id} `{title?,description?}`.
- GET /api/playlists/{id}/items -> `{items:[video refs],total}`.
- POST /api/playlists/{id}/items `{video_id}` -> add video.

### ai
- POST /api/ai/chat `{channel_id, message}` -> AI employee response:
  `{reply, actions:[{id,label,permission,requires_approval,payload}],
  decisions:[{decision_type,reasoning_summary,recommendation,confidence}],
  task_id}`. Non-streaming JSON (streaming support behind AIProvider.stream()).
  AI must know selected channel, pull analytics/videos, analyze, conclude,
  recommend, offer actions. If AI not configured -> 503 `AI_NOT_CONFIGURED`
  with message `AI is not configured. Please set AI_API_KEY.`
- POST /api/ai/analyze-channel `{channel_id, instruction?}` -> channel analysis
  JSON: `{summary, findings[], recommendations[], actions[], confidence}`.
- POST /api/ai/analyze-video `{video_id}` -> same shape + score.
- POST /api/ai/content-plan `{channel_id, days?, instruction?}` -> generates
  content_plan_items rows (status IDEA/DRAFT) + `{summary, items[]}`.
- POST /api/ai/generate-titles `{video_id?, topic?}` -> `{titles:[...]}`.
- POST /api/ai/generate-description `{title?, topic?}` -> `{description}`.
- POST /api/ai/generate-seo `{title?, description?}` -> `{keywords[], tags[]}`.
- POST /api/ai/daily-report `{channel_id?}` -> `{channel_health, views_growth,
  subscriber_growth, top_videos[], worst_videos[], opportunities[], problems[],
  recommended_actions[], pending_approvals_count}`.
- GET /api/ai/tasks?channel_id=&status= -> `{items,total}`.
- GET /api/ai/tasks/{id} -> task incl. result.

### approvals
- GET /api/approvals?status=pending|approved|rejected&channel_id= -> `{items,total}`.
  Approval JSON: `{id, channel_id, action_type, target_id, proposed_change,
  reason, risk_level, status, created_at, approved_at}`.
- GET /api/approvals/{id} -> single.
- POST /api/approvals/{id}/approve -> executes the proposed action via the
  relevant service (e.g. delete video, publish, update metadata), sets status
  approved, audit log. Returns `{success:true, result}`.
- POST /api/approvals/{id}/reject -> status rejected, audit log.

### audit
- GET /api/audit?channel_id=&limit=50 -> `{items:[{id,action,target,result,
  metadata,created_at,user_id,channel_id}],total}`.

### dashboard
- GET /api/dashboard?channel_id= -> `{summary:{channels, videos, views,
  subscribers, watch_time_seconds, revenue}, growth:{...}, top_videos[],
  underperforming_videos[], ai_recommendations[], pending_approvals[],
  recent_actions[], system_health:{...same as /api/health checks}}`.

### content-plan
- GET /api/content-plan?channel_id=&status= -> `{items,total}`.
- POST /api/content-plan `{channel_id,title,description?,idea?,target_keyword?,
  planned_date?,notes?}` -> item.
- PATCH /api/content-plan/{id} `{title?,status?,publish_date?,notes?...}`.
- DELETE /api/content-plan/{id} -> soft? no, hard delete + audit.

### settings
- GET /api/settings -> `{ai:{model,enabled}, notifications:{telegram_enabled:
  false}, score_weights:{ctr,retention,views_velocity,subscriber_conversion,
  watch_time,engagement}, ranges_supported:[...]}`.
- PATCH /api/settings `{ai?:{model}, score_weights?:{...}}` -> save (DB table
  `settings` key/value or env-overridable; simplest: persist JSON to a
  `settings` key/value table you may add to models — allowed addition).

## 6. YOUTUBE SERVICE LAYER (app/services/youtube_service.py)

Class `YouTubeService` with methods (exact names): `get_channel()`,
`get_channels()`, `get_videos()`, `get_video()`, `update_video()`,
`upload_video()`, `delete_video()`, `get_playlists()`, `create_playlist()`,
`update_playlist()`, `get_comments()`, `reply_comment()`. Each takes an
authenticated client + ids. Uses `app/youtube/client.py`:
- `get_authenticated_client(account)`: loads encrypted tokens, builds
  `googleapiclient.discovery.build("youtube","v3",credentials=...)`, refreshes
  token via google.auth when expired (updates stored token_expiry).
- Error mapping -> AppError codes: token expired/revoked ->
  `YOUTUBE_AUTH_EXPIRED` (message: `YouTube authorization has expired. Please
  reconnect your account.`), quota -> `YOUTUBE_QUOTA`, 404 -> `YOUTUBE_NOT_FOUND`,
  network -> `YOUTUBE_UNAVAILABLE`. `services/oauth.py` handles the OAuth flow
  (build url, exchange, upsert account+channel).

## 7. ANALYTICS ENGINE (app/analytics/engine.py + services/analytics_service.py)

- `analytics_service.sync_channel(account)`: fetch channel statistics + recent
  videos, upsert rows, upsert snapshot for today (idempotent via unique
  constraint). `sync_video_analytics(account)`: per-video analytics snapshot
  (watch time, avg view duration, shares, subs gained/lost, revenue if scope).
- `engine.compute_range(channel_id, days)`: aggregate snapshots in window.

## 8. AI SYSTEM (app/ai/ + app/agents/)

- `app/ai/provider.py`: `AIProvider` ABC: `generate(system_prompt, user_prompt,
  json_schema=None) -> str | dict`, `stream(...)`. `OpenAIProvider` via httpx to
  `AI_BASE_URL` (OpenAI-compatible chat completions), `AI_MODEL`, `AI_API_KEY`.
  `get_provider()` factory from settings; raises AppError `AI_NOT_CONFIGURED` if
  no key. `generate_structured` must parse JSON robustly (strip code fences,
  retry once) and validate with Pydantic.
- `app/agents/tools.py`: `Tool` dataclass `{name, description, permission:
  PermissionLevel, handler}`. Allowlist ONLY:
  `get_channel_info, get_channel_videos, get_video_analytics,
  get_channel_analytics, search_channel_videos, get_comments,
  create_video_draft (=> content plan item, WRITE), update_video_metadata (WRITE),
  create_playlist (WRITE), schedule_upload (WRITE), upload_video (HIGH_RISK),
  generate_title, generate_description, generate_seo, analyze_video,
  analyze_channel, create_content_plan`. NO arbitrary python/shell/SQL access.
- `app/agents/permissions.py`: `PermissionLevel(READ, WRITE, HIGH_RISK)` and
  `PermissionGate.can(tool, user_grants)`. HIGH_RISK tools NEVER execute directly:
  they create an `approval_request` and return `{requires_approval:true,
  approval_id}`.
- `app/agents/registry.py`: `AGENTS` dict mapping agent key -> `{name,
  system_prompt_file, description, tools[]}` for: `youtube_manager`,
  `channel_analyst`, `seo_specialist`, `content_strategist`, `title_specialist`,
  `description_specialist`, `analytics_analyst`, `publishing_manager`,
  `comment_assistant`, `decision_engine`.
- `app/prompts/system/*.txt`: one plain-text system prompt file per agent above.
  Each prompt instructs the agent to: use ONLY provided tools, never fabricate
  data, return structured JSON `{summary, findings[], recommendations[],
  actions[]}` when asked, and respect permission level.
- `app/ai/memory.py`: load/save `channel_profiles`; builds AI context block:
  channel profile, recent performance (last 28d snapshot agg), recent videos,
  current task, user instruction, available tools + permission level. Never dump
  the whole DB.
- `app/ai/service.py`: `run_agent(agent_key, channel, instruction)` builds
  context, calls provider, validates JSON, logs `ai_tasks` + `ai_decisions` +
  `audit_logs`, returns the structured response.
- `app/ai/chat.py`: natural-language command router — maps user message to an
  agent + tool sequence (keyword/pattern matching over the tool allowlist, e.g.
  "analisis" -> channel_analyst; "judul" -> title_specialist; "content plan" ->
  content_strategist; "optimasi" -> analytics_analyst; "jadwalkan" ->
  publishing_manager; "balas komentar" -> comment_assistant). Falls back to
  youtube_manager with full context.
- `app/agents/decision_engine.py`: `compute_video_score(video, snapshots) ->
  {score, strengths[], weaknesses[]}`. Formula configurable via settings table
  weights (ctr, retention, views_velocity, subscriber_conversion, watch_time,
  engagement), normalized 0-100. Label it `AI Performance Score`; UI must not
  claim it is official YouTube metrics.

## 9. BACKGROUND TASKS (app/tasks/scheduler.py)

Asyncio loop started in `main.py` lifespan: every 1h sync channel stats; every
6h sync video analytics; daily AI daily-report (creates ai_task). All idempotent.
Guard with a simple `is_running` lock per account. Do not block requests.

## 10. FRONTEND CONTRACT

Stack: React 18, TypeScript, Vite 6, Tailwind CSS 3.4, react-router-dom 6,
zustand 4, recharts 2, lucide-react, axios. Dark mode default. Modern SaaS
dashboard, desktop-first + mobile-friendly, not cluttered.

Layout (frontend/src/layouts/AppLayout.tsx): sidebar with logo
"AI YOUTUBE MANAGER", items: Dashboard, Channels, Videos, Analytics, Content
Plan, AI Assistant, Approvals, Comments, Playlists, Audit Logs, Settings.
Topbar: channel selector (dropdown of connected channels, persisted in zustand),
system health chips (Backend/Database/YouTube/AI from /api/health), user menu.

Routes (frontend/src/App.tsx, react-router):
`/` -> Dashboard, `/channels`, `/videos`, `/videos/:id`, `/analytics`,
`/content-plan`, `/ai`, `/approvals`, `/comments`, `/playlists`, `/audit`,
`/settings`, `/auth/login`, `/auth/register`, `/onboarding`. Protected routes
redirect to /auth/login when unauthenticated. First-run: when user has 0
channels, dashboard shows the Get Started / Connect YouTube onboarding.

Contract files (worker 5 owns these; pages import from them):
- `src/services/api.ts`: axios instance baseURL `/api`, withCredentials true;
  exports `api.get/post/patch/delete(path, body?)` typed helpers that throw
  `ApiError{code,message,status}` and unwrap the error envelope. Also typed
  resource helpers: `fetchHealth, login, register, logout, fetchMe,
  fetchDashboard(channelId), fetchChannels, fetchChannel(id), fetchVideos(q),
  fetchVideo(id), fetchAnalytics(channelId, range), fetchAiChat(channelId, msg),
  analyzeChannel, fetchApprovals(status), approve(id), reject(id),
  fetchAudit(q), fetchContentPlan(q), fetchComments(q), fetchPlaylists(q),
  fetchSettings, updateSettings, fetchChannelProfile(id), updateChannelProfile,
  fetchTasks, fetchDailyReport`.
- `src/stores/auth.ts`: `useAuthStore {user, loading, login, logout, register,
  fetchMe, ensureLoaded}`.
- `src/stores/channel.ts`: `useChannelStore {channels, selectedChannelId,
  setChannels, selectChannel, refreshChannels}` (selectedChannelId persisted to
  localStorage; when unset, pick first channel).
- `src/types/index.ts`: TS interfaces mirroring the API JSON (User, Account,
  Channel, Video, Analytics, AiResponse, Approval, AuditEntry, ContentPlanItem,
  Comment, Playlist, Settings, HealthCheck).
- `src/utils/format.ts`: `formatNumber (1.2K/3.4M), formatDuration (HH:MM:SS),
  formatDate, timeAgo, formatPercent`.

Pages (worker 6 owns: dashboard, channels, videos, analytics; worker 7 owns:
ai, approvals, comments, playlists, content-plan, audit, settings, onboarding):
- Dashboard: header cards (Channels, Videos, Views, Subscribers, Watch Time,
  Revenue), growth chart (recharts Area/Line), Top videos, Underperforming
  videos, AI recommendations list, Pending approvals (with quick Approve/Reject),
  Recent actions, System health chips.
- Channels: card grid with thumbnail, name, subs/views/videos, "Connect
  YouTube" button (GET /api/auth/google), disconnect, view profile (AI memory
  editor), refresh sync.
- Videos: table (Thumbnail, Title, Views, CTR, Watch time, Published, Status,
  AI Score) + search + sort + actions (Analyze, Edit, Optimize, View Analytics).
- Analytics: range picker (7/28/90/365/custom), metric cards, timeseries chart,
  top/worst videos, growth indicators.
- AI Assistant (/ai): chat-style UI, message list, quick-command chips
  ("Analisis channel saya hari ini", "Buatkan 10 ide video", "Buat content plan
  30 hari", "Optimalkan video CTR rendah", "Buatkan 5 judul", "Laporan channel
  hari ini"), response renders recommendations + action buttons (actions
  require approval shown with APPROVE/REJECT card when HIGH_RISK).
- Approvals: pending list with cards (action type, proposed_change, reason,
  risk badge) + Approve/Reject/View Details; history tabs.
- Content Plan: calendar-ish list grouped by status with statuses
  IDEA/DRAFT/READY/APPROVAL/SCHEDULED/PUBLISHED/CANCELLED; create/edit item.
- Comments: list with video title, author, text, like count, reply box.
- Playlists: list + create + add video + items view.
- Audit Logs: timeline list.
- Settings: AI model, score weights editor, notification prefs (disabled badge),
  danger zone (disconnect).
- Onboarding (/onboarding): 5 steps (Create account -> Configure AI -> Connect
  YouTube -> Select channel -> Run first analysis).

Frontend dev: vite dev server on 5173 with proxy `/api` -> `http://localhost:5000`.
Production: `npm run build` outputs `frontend/dist`, served by FastAPI StaticFiles
at `/` (backend already serves it; nginx/docker also available).

## 11. DEPLOYMENT & DOCS (worker 8 owns)

- `scripts/install.sh` (Ubuntu 22.04): apt install python3.11/venv/pip, nodejs
  18+ (nodesource), postgresql, nginx; create db + user; python venv + pip
  install; copy .env; alembic upgrade head; npm ci + build; systemd unit install
  + enable; ufw allow 5000/tcp (with warning it's dev-only).
- `scripts/start.sh`, `scripts/stop.sh`, `scripts/backup.sh` (pg_dump + optional
  S3/rclone note).
- `systemd/ai-youtube-manager.service`: gunicorn/uvicorn workers on
  `127.0.0.1:5000`, env file, Restart=always.
- `nginx/ai-youtube-manager.conf`: server_name youtube-manager.example.com,
  proxy_pass 127.0.0.1:5000, WebSocket upgrade headers, security headers.
- `docker-compose.yml`: services db (postgres:16), backend (build ./backend,
  uvicorn 0.0.0.0:5000), frontend (nginx serving dist) or backend-static;
  redis optional (profile). Include Dockerfiles for backend + frontend.
- `.gitignore`: node_modules, dist, .venv, __pycache__, .env, *.pyc, .DS_Store,
  uploads/.
- `README.md`: sections 1-18 exactly as the master prompt asks (Requirements,
  Ubuntu install, Postgres setup, Env vars, Google Cloud project, YouTube API
  activation, OAuth config, AI API config, Migration, Dev server, Production,
  Nginx, SSL, Firewall, Troubleshooting, Backup, Security, Connect channel).
- `docs/GOOGLE_CLOUD_SETUP.md`: step-by-step Google Cloud console setup with the
  exact redirect URI `http://IP-VPS:5000/api/auth/google/callback` for dev and
  HTTPS guidance for prod. Do not invent Google console details beyond documented
  reality.

## 12. TESTING (worker 4 owns backend tests)

pytest, fastapi TestClient, SQLite in-memory (`sqlite://` + `create_all`) so tests
run without Postgres. Files: test_health, test_auth (register/login/me/logout +
password hashing), test_approval_flow (create -> reject/approve, audit written),
test_decision_engine (score 0-100, strengths/weaknesses), test_permissions
(READ/WRITE/HIGH_RISK gating; HIGH_RISK never auto-executes), test_audit
(log entries created). Also verify /api/health returns the documented shape and
that OAuth-not-configured returns the exact documented 503 message.

## 13. WORKER RULES

- Files are DISJOINT per worker (see ownership lists). Do not edit files owned
  by another worker. Do not run `pip install`/`npm install`/servers/builds
  (integration happens centrally). You MAY run `python3 -m py_compile <file>` on
  your own backend files to catch syntax errors.
- Verify your own code by reading it back; report anything you could not verify.
- When done, your summary must list: files created, what was verified, and any
  deviations/assumptions.
