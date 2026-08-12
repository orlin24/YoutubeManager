import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Bot,
  CheckSquare,
  Clapperboard,
  DollarSign,
  Eye,
  Film,
  Rocket,
  TrendingUp,
  Users,
} from "lucide-react";
import { fetchDashboard } from "../../services/api";
import { useChannelStore } from "../../stores/channel";
import type { DashboardData } from "../../types";
import { Badge } from "../../components/common/Badge";
import { Button } from "../../components/common/Button";
import { Card } from "../../components/common/Card";
import { EmptyState } from "../../components/common/EmptyState";
import { ErrorAlert } from "../../components/common/ErrorAlert";
import { SkeletonRow } from "../../components/common/SkeletonRow";
import { StatCard } from "../../components/common/StatCard";
import { formatDateTime, formatMoney, formatNumber, timeAgo } from "../../utils/format";
import SystemHealth from "./SystemHealth";

export default function DashboardPage() {
  const selectedChannelId = useChannelStore((s) => s.selectedChannelId);
  const channels = useChannelStore((s) => s.channels);
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchDashboard(selectedChannelId)
      .then(setData)
      .catch((e) => setError(e.message ?? "Failed to load dashboard."))
      .finally(() => setLoading(false));
  }, [selectedChannelId]);

  useEffect(() => {
    load();
  }, [load]);

  if (channels.length === 0 && !loading) {
    return (
      <div className="mx-auto max-w-2xl pt-10">
        <EmptyState
          icon={Rocket}
          title="Hubungkan channel YouTube untuk mulai"
          description="AI YouTube Manager menganalisis channel kamu, membuat content plan, menulis judul dan deskripsi, dan merekomendasikan waktu tayang terbaik."
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <a href="http://localhost:5000/api/auth/google" className="btn-primary">
                Connect YouTube
              </a>
              <Link to="/tutorial" className="btn-secondary">
                Buka Tutorial
              </Link>
            </div>
          }
        />
      </div>
    );
  }

  if (loading && !data) return <SkeletonRow rows={6} />;
  if (error) return <ErrorAlert message={error} onRetry={load} />;
  if (!data) return null;

  const s = data.summary;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-zinc-100">Dashboard</h1>
          <p className="text-sm text-zinc-500">Channel health at a glance</p>
        </div>
        <SystemHealth />
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        <StatCard icon={Clapperboard} label="Channels" value={String(s.channels)} />
        <StatCard icon={Film} label="Videos" value={formatNumber(s.videos)} />
        <StatCard
          icon={Eye}
          label="Views (28d)"
          value={formatNumber(s.views)}
          delta={data.growth?.views_pct}
          deltaLabel="vs prev period"
        />
        <StatCard
          icon={Users}
          label="Subscribers"
          value={formatNumber(s.subscribers)}
          delta={data.growth?.subscribers_pct}
          deltaLabel="vs prev period"
        />
        <StatCard
          icon={TrendingUp}
          label="Watch time"
          value={`${Math.round(s.watch_time_seconds / 3600)}h`}
        />
        <StatCard icon={DollarSign} label="Revenue est." value={formatMoney(s.revenue)} />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Top videos" subtitle="By views (last 28d)">
          {data.top_videos.length === 0 ? (
            <p className="py-6 text-center text-sm text-zinc-600">
              No public videos synced yet. Refresh the channel to pull videos.
            </p>
          ) : (
            <ul className="space-y-3">
              {data.top_videos.slice(0, 5).map((v) => (
                <li key={v.id} className="flex items-center gap-3">
                  {v.thumbnail_url ? (
                    <img src={v.thumbnail_url} alt="" className="h-12 w-20 rounded object-cover" />
                  ) : (
                    <div className="h-12 w-20 rounded bg-zinc-800" />
                  )}
                  <div className="min-w-0 flex-1">
                    <Link
                      to={`/videos/${v.id}`}
                      className="block truncate text-sm font-medium text-zinc-200 hover:text-brand-300"
                    >
                      {v.title}
                    </Link>
                    <p className="text-xs text-zinc-500">
                      {formatNumber(v.view_count)} views · {timeAgo(v.published_at)}
                    </p>
                  </div>
                  {v.ai_score !== null && v.ai_score !== undefined && (
                    <Badge tone={v.ai_score >= 60 ? "green" : v.ai_score >= 40 ? "amber" : "red"}>
                      AI {Math.round(v.ai_score)}
                    </Badge>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Underperforming videos" subtitle="Worst performers by views">
          {data.underperforming_videos.length === 0 ? (
            <p className="py-6 text-center text-sm text-zinc-600">
              No data yet. Sync analytics to see underperformers.
            </p>
          ) : (
            <ul className="space-y-3">
              {data.underperforming_videos.slice(0, 5).map((v) => (
                <li key={v.id} className="flex items-center gap-3">
                  {v.thumbnail_url ? (
                    <img src={v.thumbnail_url} alt="" className="h-12 w-20 rounded object-cover" />
                  ) : (
                    <div className="h-12 w-20 rounded bg-zinc-800" />
                  )}
                  <div className="min-w-0 flex-1">
                    <Link
                      to={`/videos/${v.id}`}
                      className="block truncate text-sm font-medium text-zinc-200 hover:text-brand-300"
                    >
                      {v.title}
                    </Link>
                    <p className="text-xs text-zinc-500">{formatNumber(v.view_count)} views</p>
                  </div>
                  <Link to={`/ai?prompt=${encodeURIComponent(`Optimize the video "${v.title}"`)}`}>
                    <Button variant="ghost" className="text-xs">
                      <Bot className="h-3.5 w-3.5" /> Optimize
                    </Button>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <Card title="AI recommendations" className="xl:col-span-1">
          <ul className="space-y-3">
            {data.ai_recommendations.map((r, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-zinc-300">
                <Bot className="mt-0.5 h-4 w-4 shrink-0 text-brand-400" />
                <span>{r.text}</span>
              </li>
            ))}
            {data.ai_recommendations.length === 0 && (
              <li className="text-sm text-zinc-600">No recommendations yet.</li>
            )}
          </ul>
        </Card>

        <Card title="Recent actions" subtitle="Audit trail" className="xl:col-span-1">
          <ul className="space-y-2.5">
            {data.recent_actions.map((a) => (
              <li key={a.id} className="flex items-start gap-2 text-sm">
                <CheckSquare className="mt-0.5 h-3.5 w-3.5 shrink-0 text-zinc-600" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-zinc-300">
                    <span className="text-zinc-400">{a.action.replace(/_/g, " ")}</span>
                    {a.target ? <span className="text-zinc-500"> · {a.target}</span> : null}
                  </p>
                  <p className="text-xs text-zinc-600">{formatDateTime(a.created_at)}</p>
                </div>
              </li>
            ))}
            {data.recent_actions.length === 0 && (
              <li className="text-sm text-zinc-600">No actions recorded yet.</li>
            )}
          </ul>
        </Card>
      </div>
    </div>
  );
}
