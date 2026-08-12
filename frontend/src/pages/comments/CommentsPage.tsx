import { useCallback, useEffect, useState } from "react";
import { MessageSquare, Reply, Sparkles } from "lucide-react";
import { aiCommentDraft, fetchComments, fetchVideos, replyComment } from "../../services/api";
import { useChannelStore } from "../../stores/channel";
import type { Comment, Video } from "../../types";
import { ApiError } from "../../services/api";
import { Button } from "../../components/common/Button";
import { EmptyState } from "../../components/common/EmptyState";
import { ErrorAlert } from "../../components/common/ErrorAlert";
import { SkeletonRow } from "../../components/common/SkeletonRow";
import { formatNumber, timeAgo } from "../../utils/format";

export default function CommentsPage() {
  const selectedChannelId = useChannelStore((s) => s.selectedChannelId);
  const channels = useChannelStore((s) => s.channels);
  const [videos, setVideos] = useState<Video[]>([]);
  const [videoId, setVideoId] = useState("");
  const [sort, setSort] = useState("newest");
  const [items, setItems] = useState<Comment[]>([]);
  const [replies, setReplies] = useState<Record<string, string>>({});
  const [replying, setReplying] = useState<string | null>(null);
  const [aiDrafting, setAiDrafting] = useState<string | null>(null);
  const [replyMsg, setReplyMsg] = useState<string | null>(null);
  const [hiddenCount, setHiddenCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadVideos = useCallback(() => {
    if (!selectedChannelId) return;
    fetchVideos({ channel_id: selectedChannelId, limit: 50, sort: "latest" })
      .then((r) => setVideos(r.items))
      .catch(() => undefined);
  }, [selectedChannelId]);

  const load = useCallback(() => {
    if (!selectedChannelId) return;
    setLoading(true);
    setError(null);
    const q: Record<string, unknown> = { channel_id: selectedChannelId, sort };
    if (videoId) q.video_id = videoId;
    fetchComments(q)
      .then((r) => {
        setItems(r.items);
        setHiddenCount(r.hidden_count ?? 0);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Failed to load comments."))
      .finally(() => setLoading(false));
  }, [selectedChannelId, videoId, sort]);

  useEffect(() => {
    loadVideos();
  }, [loadVideos]);

  useEffect(() => {
    load();
  }, [load]);

  const onAiDraft = async (c: Comment) => {
    if (!selectedChannelId) return;
    setAiDrafting(c.id);
    setError(null);
    try {
      const { draft } = await aiCommentDraft(selectedChannelId, c.text, c.author, c.video_title);
      setReplies((r) => ({ ...r, [c.id]: draft }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "AI draft failed.");
    } finally {
      setAiDrafting(null);
    }
  };

  const onReply = async (commentId: string) => {
    if (!selectedChannelId) return;
    const text = (replies[commentId] ?? "").trim();
    if (!text) {
      document.getElementById(`reply-input-${commentId}`)?.focus();
      return;
    }
    setReplying(commentId);
    setReplyMsg(null);
    try {
      await replyComment(commentId, selectedChannelId, text);
      setReplies((r) => ({ ...r, [commentId]: "" }));
      setItems((prev) => prev.filter((c) => c.id !== commentId)); // hide, not delete
      setHiddenCount((n) => n + 1);
      setReplyMsg("Balasan terkirim ke YouTube - komentar disembunyikan dari daftar.");
      setTimeout(() => setReplyMsg(null), 4000);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Reply failed.");
    } finally {
      setReplying(null);
    }
  };

  if (channels.length === 0) {
    return (
      <EmptyState
        title="No channel connected"
        description="Connect a YouTube channel to manage comments."
        action={
          <a href="http://localhost:5000/api/auth/google" className="btn-primary">
            Connect YouTube
          </a>
        }
      />
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-bold text-zinc-100">
          <MessageSquare className="h-5 w-5 text-brand-400" /> Comments
        </h1>
        <p className="text-sm text-zinc-500">Live comments from YouTube (requires a connected channel)</p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <select
          className="input w-72"
          value={videoId}
          onChange={(e) => setVideoId(e.target.value)}
        >
          <option value="">All videos</option>
          {videos.map((v) => (
            <option key={v.id} value={v.id}>
              {v.title}
            </option>
          ))}
        </select>
        <select className="input w-40" value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="newest">Newest</option>
          <option value="oldest">Oldest</option>
        </select>
      </div>

      {error && <ErrorAlert message={error} onRetry={load} />}
      {replyMsg && (
        <div className="rounded-lg border border-emerald-800/60 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-300">
          {replyMsg}
        </div>
      )}
      {hiddenCount > 0 && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 px-4 py-2 text-xs text-zinc-400">
          {hiddenCount} komentar sudah dibalas dan disembunyikan dari daftar (tetap ada di YouTube).
        </div>
      )}
      {loading ? (
        <SkeletonRow rows={6} />
      ) : items.length === 0 ? (
        <EmptyState title="No comments found" description="Comments load live from YouTube when available." />
      ) : (
        <div className="space-y-3">
          {items.map((c) => (
            <div key={c.id} className="card">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-zinc-200">{c.author}</p>
                  <p className="text-xs text-zinc-600">
                    {c.video_title || "Unknown video"} · {timeAgo(c.published_at)} ·{" "}
                    {formatNumber(c.like_count)} likes
                  </p>
                </div>
                <span className="text-xs text-zinc-600">{c.id.slice(0, 8)}</span>
              </div>
              <p className="mt-2 text-sm text-zinc-300">{c.text}</p>
              <div className="mt-3 flex items-center gap-2">
                <input
                  id={`reply-input-${c.id}`}
                  className="input h-9 flex-1"
                  placeholder="Tulis balasan... (atau klik AI draft)"
                  value={replies[c.id] ?? ""}
                  onChange={(e) => setReplies((r) => ({ ...r, [c.id]: e.target.value }))}
                />
                <Button
                  variant="secondary"
                  className="h-9 text-xs"
                  loading={aiDrafting === c.id}
                  onClick={() => onAiDraft(c)}
                >
                  <Sparkles className="h-3.5 w-3.5" /> AI draft
                </Button>
                <Button
                  variant="secondary"
                  className="h-9 text-xs"
                  loading={replying === c.id}
                  onClick={() => onReply(c.id)}
                >
                  <Reply className="h-3.5 w-3.5" /> Reply
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
