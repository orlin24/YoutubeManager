import { useCallback, useEffect, useState } from "react";
import { ListVideo, Plus, X } from "lucide-react";
import {
  addPlaylistItem,
  createPlaylist,
  fetchPlaylistItems,
  fetchPlaylists,
  fetchVideos,
  updatePlaylist,
} from "../../services/api";
import { useChannelStore } from "../../stores/channel";
import type { Playlist, PlaylistItem, Video } from "../../types";
import { ApiError } from "../../services/api";
import { Button } from "../../components/common/Button";
import { Card } from "../../components/common/Card";
import { EmptyState } from "../../components/common/EmptyState";
import { ErrorAlert } from "../../components/common/ErrorAlert";
import { SkeletonRow } from "../../components/common/SkeletonRow";
import { formatNumber } from "../../utils/format";

export default function PlaylistsPage() {
  const selectedChannelId = useChannelStore((s) => s.selectedChannelId);
  const channels = useChannelStore((s) => s.channels);
  const [items, setItems] = useState<Playlist[]>([]);
  const [openPlaylist, setOpenPlaylist] = useState<Playlist | null>(null);
  const [playlistItems, setPlaylistItems] = useState<PlaylistItem[]>([]);
  const [videos, setVideos] = useState<Video[]>([]);
  const [addVideoId, setAddVideoId] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [editTitle, setEditTitle] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    if (!selectedChannelId) return;
    setLoading(true);
    setError(null);
    fetchPlaylists(selectedChannelId)
      .then((r) => setItems(r.items))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Failed to load playlists."))
      .finally(() => setLoading(false));
  }, [selectedChannelId]);

  useEffect(() => {
    load();
  }, [load]);

  const openItems = async (p: Playlist) => {
    if (!selectedChannelId) return;
    setOpenPlaylist(p);
    setEditTitle(p.title);
    setAddVideoId("");
    try {
      const [pi, vids] = await Promise.all([
        fetchPlaylistItems(p.id, selectedChannelId),
        fetchVideos({ channel_id: selectedChannelId, limit: 50 }),
      ]);
      setPlaylistItems(pi.items);
      setVideos(vids.items);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load playlist items.");
    }
  };

  const onCreate = async () => {
    if (!selectedChannelId || !newTitle.trim()) return;
    setBusy(true);
    try {
      await createPlaylist(selectedChannelId, newTitle.trim(), newDesc);
      setCreateOpen(false);
      setNewTitle("");
      setNewDesc("");
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Create failed.");
    } finally {
      setBusy(false);
    }
  };

  const onAddItem = async () => {
    if (!openPlaylist || !selectedChannelId || !addVideoId) return;
    setBusy(true);
    try {
      await addPlaylistItem(openPlaylist.id, selectedChannelId, addVideoId);
      setAddVideoId("");
      openItems(openPlaylist);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Add failed.");
    } finally {
      setBusy(false);
    }
  };

  const onSaveTitle = async () => {
    if (!openPlaylist || !selectedChannelId || !editTitle.trim()) return;
    setBusy(true);
    try {
      await updatePlaylist(openPlaylist.id, selectedChannelId, { title: editTitle.trim() });
      setOpenPlaylist(null);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Update failed.");
    } finally {
      setBusy(false);
    }
  };

  if (channels.length === 0) {
    return (
      <EmptyState
        title="No channel connected"
        description="Connect a YouTube channel to manage playlists."
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
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-zinc-100">
            <ListVideo className="h-5 w-5 text-brand-400" /> Playlists
          </h1>
          <p className="text-sm text-zinc-500">Live YouTube playlists</p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4" /> New playlist
        </Button>
      </div>

      {error && <ErrorAlert message={error} onRetry={load} />}
      {loading ? (
        <SkeletonRow rows={4} />
      ) : items.length === 0 ? (
        <EmptyState title="No playlists yet" description="Create your first playlist." />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {items.map((p) => (
            <Card key={p.id} className="cursor-pointer transition-colors hover:border-brand-700" >
              <div onClick={() => openItems(p)}>
                {p.thumbnail_url ? (
                  <img src={p.thumbnail_url} alt="" className="h-32 w-full rounded-lg object-cover" />
                ) : (
                  <div className="flex h-32 w-full items-center justify-center rounded-lg bg-zinc-800 text-zinc-600">
                    <ListVideo className="h-8 w-8" />
                  </div>
                )}
                <h3 className="mt-3 truncate font-semibold text-zinc-100">{p.title}</h3>
                <p className="mt-1 text-xs text-zinc-500">{formatNumber(p.item_count)} items</p>
              </div>
            </Card>
          ))}
        </div>
      )}

      {createOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => setCreateOpen(false)}>
          <div className="w-full max-w-md rounded-xl border border-zinc-800 bg-zinc-900 p-6" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-zinc-100">New playlist</h3>
              <button onClick={() => setCreateOpen(false)} className="text-zinc-500"><X className="h-5 w-5" /></button>
            </div>
            <div className="space-y-3">
              <input className="input" placeholder="Title" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} />
              <textarea className="input min-h-[80px]" placeholder="Description" value={newDesc} onChange={(e) => setNewDesc(e.target.value)} />
              <Button className="w-full" loading={busy} onClick={onCreate}>Create</Button>
            </div>
          </div>
        </div>
      )}

      {openPlaylist && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => setOpenPlaylist(null)}>
          <div className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-900 p-6" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-zinc-100">{openPlaylist.title}</h3>
              <button onClick={() => setOpenPlaylist(null)} className="text-zinc-500"><X className="h-5 w-5" /></button>
            </div>
            <div className="mb-4 flex gap-2">
              <input className="input h-9" placeholder="New title" value={editTitle} onChange={(e) => setEditTitle(e.target.value)} />
              <Button variant="secondary" className="h-9 text-xs" loading={busy} onClick={onSaveTitle}>Rename</Button>
            </div>
            <div className="mb-4 flex gap-2">
              <select className="input h-9 flex-1" value={addVideoId} onChange={(e) => setAddVideoId(e.target.value)}>
                <option value="">Add a video...</option>
                {videos.map((v) => (
                  <option key={v.id} value={v.youtube_video_id}>{v.title}</option>
                ))}
              </select>
              <Button variant="secondary" className="h-9 text-xs" loading={busy} disabled={!addVideoId} onClick={onAddItem}>Add</Button>
            </div>
            <ul className="space-y-2">
              {playlistItems.map((i) => (
                <li key={i.playlist_item_id} className="flex items-center gap-3">
                  {i.thumbnail_url ? (
                    <img src={i.thumbnail_url} alt="" className="h-10 w-16 rounded object-cover" />
                  ) : (
                    <div className="h-10 w-16 rounded bg-zinc-800" />
                  )}
                  <span className="min-w-0 flex-1 truncate text-sm text-zinc-200">{i.title || i.video_id}</span>
                </li>
              ))}
              {playlistItems.length === 0 && <li className="text-sm text-zinc-600">Empty playlist.</li>}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
