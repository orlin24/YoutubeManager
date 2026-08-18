import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { DollarSign, Eye, MessageSquare, ThumbsUp, TrendingDown, TrendingUp, Users } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchAnalytics } from "../../services/api";
import { useChannelStore } from "../../stores/channel";
import type { AnalyticsResponse } from "../../types";
import { Badge } from "../../components/common/Badge";
import { Card } from "../../components/common/Card";
import { EmptyState } from "../../components/common/EmptyState";
import { ErrorAlert } from "../../components/common/ErrorAlert";
import { SkeletonRow } from "../../components/common/SkeletonRow";
import { StatCard } from "../../components/common/StatCard";
import { formatMoney, formatNumber } from "../../utils/format";
import RangePicker from "./RangePicker";

export default function AnalyticsPage() {
  const selectedChannelId = useChannelStore((s) => s.selectedChannelId);
  const channels = useChannelStore((s) => s.channels);
  const [range, setRange] = useState("28d");
  const [data, setData] = useState<AnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!selectedChannelId) return;
    setLoading(true);
    setError(null);
    fetchAnalytics(selectedChannelId, range)
      .then(setData)
      .catch((e) => setError(e.message ?? "Failed to load analytics."))
      .finally(() => setLoading(false));
  }, [selectedChannelId, range]);

  useEffect(() => {
    load();
  }, [load]);

  if (channels.length === 0) {
    return (
      <EmptyState
        title="No channel connected"
        description="Connect a YouTube channel to see analytics."
        action={
          <a href="http://localhost:5000/api/auth/google" className="btn-primary">
            Connect YouTube
          </a>
        }
      />
    );
  }

  if (loading && !data) return <SkeletonRow rows={6} />;
  if (error) return <ErrorAlert message={error} onRetry={load} />;
  if (!data) return null;

  const o = data.overview;
  const growth = data.growth;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-zinc-100">Analytics</h1>
          <p className="text-sm text-zinc-500">Based on synced YouTube analytics snapshots</p>
        </div>
        <RangePicker value={range} onChange={setRange} />
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        <StatCard icon={Eye} label="Views" value={formatNumber(o.views)} delta={growth.views_pct} />
        <StatCard icon={Users} label="Subscribers net" value={formatNumber(o.subscribers_gained - o.subscribers_lost)} delta={growth.subscribers_pct} />
        <StatCard icon={ThumbsUp} label="Likes" value={formatNumber(o.likes)} />
        <StatCard icon={MessageSquare} label="Comments" value={formatNumber(o.comments)} />
        <StatCard icon={TrendingUp} label="Watch time" value={`${Math.round(o.watch_time_seconds / 3600)}h`} />
        <StatCard icon={DollarSign} label="Revenue est." value={formatMoney(o.estimated_revenue)} />
      </div>

      <Card title="Views over time" subtitle={range === "custom" ? "Custom range" : `Last ${range}`} className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data.timeseries}>
            <defs>
              <linearGradient id="aviews" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#D0BCFF" stopOpacity={0.4} />
                <stop offset="95%" stopColor="#D0BCFF" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#2B2930" />
            <XAxis dataKey="date" stroke="#49454F" fontSize={11} />
            <YAxis stroke="#49454F" fontSize={11} />
            <Tooltip
              contentStyle={{ background: "#211F26", border: "1px solid #49454F", borderRadius: 8 }}
              labelStyle={{ color: "#E6E0E9" }}
            />
            <Area type="monotone" dataKey="views" stroke="#D0BCFF" fill="url(#aviews)" />
          </AreaChart>
        </ResponsiveContainer>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Top videos">
          <ul className="space-y-3">
            {data.top_videos.map((v) => (
              <li key={v.id} className="flex items-center gap-3">
                {v.thumbnail_url ? (
                  <img src={v.thumbnail_url} alt="" className="h-10 w-16 rounded object-cover" />
                ) : (
                  <div className="h-10 w-16 rounded bg-zinc-800" />
                )}
                <Link to={`/videos/${v.id}`} className="min-w-0 flex-1 truncate text-sm text-zinc-200 hover:text-brand-300">
                  {v.title}
                </Link>
                <span className="text-sm text-zinc-400">{formatNumber(v.view_count)}</span>
              </li>
            ))}
            {data.top_videos.length === 0 && <li className="text-sm text-zinc-600">No data yet.</li>}
          </ul>
        </Card>
        <Card title="Worst videos" subtitle="Candidates for optimization">
          <ul className="space-y-3">
            {data.worst_videos.map((v) => (
              <li key={v.id} className="flex items-center gap-3">
                {v.thumbnail_url ? (
                  <img src={v.thumbnail_url} alt="" className="h-10 w-16 rounded object-cover" />
                ) : (
                  <div className="h-10 w-16 rounded bg-zinc-800" />
                )}
                <Link to={`/videos/${v.id}`} className="min-w-0 flex-1 truncate text-sm text-zinc-200 hover:text-brand-300">
                  {v.title}
                </Link>
                <span className="text-sm text-zinc-400">{formatNumber(v.view_count)}</span>
              </li>
            ))}
            {data.worst_videos.length === 0 && <li className="text-sm text-zinc-600">No data yet.</li>}
          </ul>
        </Card>
      </div>

      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span className="inline-flex items-center gap-1 text-emerald-400">
          <TrendingUp className="h-4 w-4" /> Views {growth.views_delta >= 0 ? "+" : ""}
          {formatNumber(growth.views_delta)}
        </span>
        <span className="inline-flex items-center gap-1 text-emerald-400">
          <Users className="h-4 w-4" /> Subscribers {growth.subscribers_delta >= 0 ? "+" : ""}
          {formatNumber(growth.subscribers_delta)}
        </span>
        {growth.views_pct !== null && (
          <Badge tone={growth.views_pct >= 0 ? "green" : "red"}>
            {growth.views_pct >= 0 ? "+" : ""}
            {growth.views_pct}% views vs previous period
          </Badge>
        )}
      </div>
    </div>
  );
}
