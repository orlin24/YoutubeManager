import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Bot, Eye, ThumbsUp, MessageSquare, Trash2 } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { deleteVideo, fetchVideo, fetchVideoAnalytics } from "../../services/api";
import { ApiError } from "../../services/api";
import type { Video } from "../../types";
import { Badge, toneForStatus } from "../../components/common/Badge";
import { Button } from "../../components/common/Button";
import { Card } from "../../components/common/Card";
import { ConfirmDialog } from "../../components/common/ConfirmDialog";
import { ErrorAlert } from "../../components/common/ErrorAlert";
import { SkeletonRow } from "../../components/common/SkeletonRow";
import { formatDateTime, formatDuration, formatNumber, formatPercent } from "../../utils/format";
import AnalyzeVideoButton from "./AnalyzeVideoButton";
import EditVideoModal from "./EditVideoModal";

export default function VideoDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [video, setVideo] = useState<Video | null>(null);
  const [analytics, setAnalytics] = useState<{ overview: Record<string, unknown>; timeseries: Array<Record<string, unknown>> }>({ overview: {}, timeseries: [] });
  const overview = analytics.overview as Record<string, number>;
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!id) return;
    setLoading(true);
    setError(null);
    Promise.all([fetchVideo(id), fetchVideoAnalytics(id)])
      .then(([v, a]) => {
        setVideo(v);
        setAnalytics({ overview: a.overview, timeseries: a.timeseries as Array<Record<string, unknown>> });
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Failed to load video."))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const onDelete = async () => {
    try {
      await deleteVideo(id!);
      setNotice("Video dihapus dari YouTube.");
      setDeleteOpen(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Delete failed.");
    }
  };

  if (loading) return <SkeletonRow rows={8} />;
  if (error) return <ErrorAlert message={error} onRetry={load} />;
  if (!video) return null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link to="/videos" className="btn-ghost h-8 text-xs">
          <ArrowLeft className="h-4 w-4" /> Back to videos
        </Link>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => setEditOpen(true)}>
            Edit
          </Button>
          <Button variant="danger" onClick={() => setDeleteOpen(true)}>
            <Trash2 className="h-4 w-4" /> Delete
          </Button>
        </div>
      </div>

      {notice && (
        <div className="rounded-lg border border-emerald-800/60 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-300">
          {notice}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          {video.thumbnail_url ? (
            <img src={video.thumbnail_url} alt="" className="w-full rounded-xl border border-zinc-800" />
          ) : (
            <div className="aspect-video w-full rounded-xl bg-zinc-800" />
          )}
          <h1 className="mt-4 text-xl font-bold text-zinc-100">{video.title}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-zinc-500">
            <span className="inline-flex items-center gap-1"><Eye className="h-4 w-4" /> {formatNumber(video.view_count)}</span>
            <span className="inline-flex items-center gap-1"><ThumbsUp className="h-4 w-4" /> {formatNumber(video.like_count)}</span>
            <span className="inline-flex items-center gap-1"><MessageSquare className="h-4 w-4" /> {formatNumber(video.comment_count)}</span>
            <Badge tone={toneForStatus(video.privacy_status)}>{video.privacy_status}</Badge>
            <span>{formatDateTime(video.published_at)}</span>
            <span>{formatDuration(video.duration_seconds)}</span>
            <span>CTR {formatPercent(video.ctr)}</span>
          </div>
          {video.description && (
            <p className="mt-4 whitespace-pre-wrap text-sm text-zinc-400">{video.description.slice(0, 2000)}</p>
          )}
          <a
            href={`https://www.youtube.com/watch?v=${video.youtube_video_id}`}
            target="_blank"
            rel="noreferrer"
            className="btn-secondary mt-4"
          >
            Open on YouTube
          </a>
        </div>

        <div className="space-y-4">
          <Card title="AI Performance Score" subtitle="Heuristic 0-100 - not an official YouTube metric">
            <div className="mb-3 flex items-center gap-3">
              <div className="flex h-16 w-16 items-center justify-center rounded-xl bg-brand-600/15 text-2xl font-bold text-brand-300">
                {video.ai_score !== null && video.ai_score !== undefined ? Math.round(video.ai_score) : "-"}
              </div>
              <AnalyzeVideoButton
                videoId={video.id}
                initialScore={video.ai_score}
                onScore={() => load()}
              />
            </div>
            <a href={`/ai?prompt=${encodeURIComponent(`Analyze and optimize the video "${video.title}"`)}`} className="btn-ghost h-8 text-xs">
              <Bot className="h-3.5 w-3.5" /> Ask the AI about this video
            </a>
          </Card>

          <Card title="28-day analytics" subtitle="From stored snapshots">
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div className="rounded-lg bg-zinc-900 p-3">
                <p className="text-xs text-zinc-500">Views</p>
                <p className="font-semibold text-zinc-100">{formatNumber(overview.views)}</p>
              </div>
              <div className="rounded-lg bg-zinc-900 p-3">
                <p className="text-xs text-zinc-500">Watch time</p>
                <p className="font-semibold text-zinc-100">{Math.round((overview.watch_time_seconds ?? 0) / 3600)}h</p>
              </div>
              <div className="rounded-lg bg-zinc-900 p-3">
                <p className="text-xs text-zinc-500">Likes</p>
                <p className="font-semibold text-zinc-100">{formatNumber(overview.likes)}</p>
              </div>
              <div className="rounded-lg bg-zinc-900 p-3">
                <p className="text-xs text-zinc-500">Comments</p>
                <p className="font-semibold text-zinc-100">{formatNumber(overview.comments)}</p>
              </div>
            </div>
            {analytics.timeseries.length > 0 && (
              <div className="mt-3 h-40">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={analytics.timeseries}>
                    <defs>
                      <linearGradient id="vviews" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#D0BCFF" stopOpacity={0.4} />
                        <stop offset="95%" stopColor="#D0BCFF" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#2B2930" />
                    <XAxis dataKey="date" stroke="#49454F" fontSize={10} />
                    <YAxis stroke="#49454F" fontSize={10} />
                    <Tooltip
                      contentStyle={{ background: "#211F26", border: "1px solid #49454F", borderRadius: 8 }}
                      labelStyle={{ color: "#e4e4e7" }}
                    />
                    <Area type="monotone" dataKey="views" stroke="#D0BCFF" fill="url(#vviews)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
          </Card>
        </div>
      </div>

      {editOpen && (
        <EditVideoModal
          video={video}
          open
          onClose={() => setEditOpen(false)}
          onSaved={() => { setEditOpen(false); load(); }}
        />
      )}
      <ConfirmDialog
        open={deleteOpen}
        title="Delete this video?"
        description={`"${video.title}" akan dihapus permanen dari YouTube.`}
        confirmLabel="Hapus permanen"
        danger
        onConfirm={onDelete}
        onCancel={() => setDeleteOpen(false)}
      />
    </div>
  );
}
