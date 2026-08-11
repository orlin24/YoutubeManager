import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { BrainCircuit, Eye, Search, Upload } from "lucide-react";
import { analyzeAllVideos, ApiError, deleteVideo, fetchVideos } from "../../services/api";
import { useChannelStore } from "../../stores/channel";
import type { Video } from "../../types";
import { Badge, toneForStatus } from "../../components/common/Badge";
import { Button } from "../../components/common/Button";
import { EmptyState } from "../../components/common/EmptyState";
import { ErrorAlert } from "../../components/common/ErrorAlert";
import { Pagination } from "../../components/common/Pagination";
import { SkeletonRow } from "../../components/common/SkeletonRow";
import { formatDuration, formatNumber, formatPercent, timeAgo } from "../../utils/format";
import AnalyzeVideoButton from "./AnalyzeVideoButton";
import EditVideoModal from "./EditVideoModal";
import UploadVideoModal from "./UploadVideoModal";
import { ConfirmDialog } from "../../components/common/ConfirmDialog";

const PAGE_SIZE = 25;

export default function VideosPage() {
  const navigate = useNavigate();
  const selectedChannelId = useChannelStore((s) => s.selectedChannelId);
  const channels = useChannelStore((s) => s.channels);
  const [videos, setVideos] = useState<Video[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState("latest");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [editVideo, setEditVideo] = useState<Video | null>(null);
  const [toDelete, setToDelete] = useState<Video | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [analyzingAll, setAnalyzingAll] = useState(false);
  const autoAnalyzedRef = useRef(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    const q: Record<string, unknown> = {
      limit: PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
      sort,
    };
    if (selectedChannelId) q.channel_id = selectedChannelId;
    if (search) q.search = search;
    if (status) q.status = status;
    fetchVideos(q)
      .then((resp) => {
        setVideos(resp.items);
        setTotal(resp.total);
      })
      .catch((e) => setError(e.message ?? "Failed to load videos."))
      .finally(() => setLoading(false));
  }, [page, search, status, sort, selectedChannelId]);

  useEffect(() => {
    load();
  }, [load]);

  // Auto-analyze all videos once per page load when any lack an AI score.
  useEffect(() => {
    if (autoAnalyzedRef.current) return;
    if (!loading && videos.length > 0 && videos.some((v) => v.ai_score === null || v.ai_score === undefined)) {
      autoAnalyzedRef.current = true;
      runAnalyzeAll(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, videos]);

  const runAnalyzeAll = async (silent = false) => {
    setAnalyzingAll(true);
    try {
      const resp = await analyzeAllVideos(selectedChannelId ?? undefined);
      if (!silent) {
        setNotice(
          `Analisis selesai: ${resp.with_score} video mendapat skor AI, ${resp.without} belum punya cukup data.`
        );
      }
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Analisis gagal.");
    } finally {
      setAnalyzingAll(false);
    }
  };

  const onDelete = async () => {
    if (!toDelete) return;
    setDeleting(true);
    try {
      await deleteVideo(toDelete.id);
      setNotice("Video dihapus dari YouTube.");
      setToDelete(null);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed.");
    } finally {
      setDeleting(false);
    }
  };

  if (channels.length === 0) {
    return (
      <EmptyState
        title="No channel connected"
        description="Connect a YouTube channel to see your videos."
        action={
          <a href="/api/auth/google" className="btn-primary">
            Connect YouTube
          </a>
        }
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-zinc-100">Videos</h1>
          <p className="text-sm text-zinc-500">{total} videos</p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" loading={analyzingAll} onClick={() => runAnalyzeAll(false)}>
            <BrainCircuit className="h-4 w-4" /> Analisis semua
          </Button>
          <Button onClick={() => setUploadOpen(true)}>
            <Upload className="h-4 w-4" /> Upload
          </Button>
        </div>
      </div>

      {notice && (
        <div className="rounded-lg border border-emerald-800/60 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-300">
          {notice}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
          <input
            className="input w-64 pl-9"
            placeholder="Search videos..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <select className="input w-40" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">All statuses</option>
          <option value="public">Public</option>
          <option value="unlisted">Unlisted</option>
          <option value="private">Private</option>
        </select>
        <select className="input w-40" value={sort} onChange={(e) => { setSort(e.target.value); setPage(1); }}>
          <option value="latest">Latest</option>
          <option value="views">Most views</option>
          <option value="ai_score">AI score</option>
        </select>
      </div>

      {error && <ErrorAlert message={error} onRetry={load} />}
      {loading ? (
        <SkeletonRow rows={8} />
      ) : videos.length === 0 ? (
        <EmptyState title="No videos found" description="Sync your channel or change the filters." />
      ) : (
        <div className="card overflow-x-auto p-0">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead>
              <tr className="border-b border-zinc-800 text-xs uppercase tracking-wide text-zinc-500">
                <th className="px-4 py-3">Video</th>
                <th className="px-4 py-3">Views</th>
                <th className="px-4 py-3">CTR</th>
                <th className="px-4 py-3">Watch time</th>
                <th className="px-4 py-3">Published</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">AI</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {videos.map((v) => (
                <tr key={v.id} className="border-b border-zinc-800/60 transition-colors hover:bg-zinc-900/60">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      {v.thumbnail_url ? (
                        <img src={v.thumbnail_url} alt="" className="h-10 w-[68px] rounded object-cover" />
                      ) : (
                        <div className="h-10 w-[68px] rounded bg-zinc-800" />
                      )}
                      <Link
                        to={`/videos/${v.id}`}
                        className="line-clamp-2 max-w-[260px] font-medium text-zinc-200 hover:text-brand-300"
                      >
                        {v.title}
                      </Link>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-zinc-400">{formatNumber(v.view_count)}</td>
                  <td className="px-4 py-3 text-zinc-400">{formatPercent(v.ctr)}</td>
                  <td className="px-4 py-3 text-zinc-400">{formatDuration(v.average_view_duration_seconds)}</td>
                  <td className="px-4 py-3 text-zinc-500">{timeAgo(v.published_at)}</td>
                  <td className="px-4 py-3">
                    <Badge tone={toneForStatus(v.privacy_status)}>{v.privacy_status}</Badge>
                  </td>
                  <td className="px-4 py-3">
                    {v.ai_score !== null && v.ai_score !== undefined ? (
                      <Badge tone={v.ai_score >= 60 ? "green" : v.ai_score >= 40 ? "amber" : "red"}>
                        {Math.round(v.ai_score)}
                      </Badge>
                    ) : (
                      <span className="text-zinc-600">-</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      <AnalyzeVideoButton videoId={v.id} initialScore={v.ai_score} />
                      <Button variant="ghost" className="h-8 px-2 text-xs" onClick={() => setEditVideo(v)}>
                        Edit
                      </Button>
                      <Button
                        variant="ghost"
                        className="h-8 px-2 text-xs text-red-400 hover:text-red-300"
                        onClick={() => setToDelete(v)}
                      >
                        Delete
                      </Button>
                      <Link to={`/videos/${v.id}`} className="btn-ghost h-8 px-2 text-xs" title="Analytics">
                        <Eye className="h-3.5 w-3.5" />
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="px-4 py-3">
            <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPage={setPage} />
          </div>
        </div>
      )}

      <UploadVideoModal
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onUploaded={() => { setNotice("Video berhasil diupload."); load(); }}
      />
      {editVideo && (
        <EditVideoModal
          video={editVideo}
          open
          onClose={() => setEditVideo(null)}
          onSaved={() => { setEditVideo(null); load(); }}
        />
      )}
      <ConfirmDialog
        open={!!toDelete}
        title="Hapus video ini?"
        description={`"${toDelete?.title}" akan dihapus permanen dari YouTube.`}
        confirmLabel="Hapus permanen"
        danger
        loading={deleting}
        onConfirm={onDelete}
        onCancel={() => setToDelete(null)}
      />
    </div>
  );
}
