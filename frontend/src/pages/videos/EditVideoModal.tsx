import { useState } from "react";
import { ImagePlus, X } from "lucide-react";
import { updateVideo, uploadThumbnail } from "../../services/api";
import { ApiError } from "../../services/api";
import type { Video } from "../../types";
import { Button } from "../../components/common/Button";
import { ErrorAlert } from "../../components/common/ErrorAlert";

interface Props {
  video: Video;
  open: boolean;
  onClose: () => void;
  onSaved?: () => void;
}

export default function EditVideoModal({ video, open, onClose, onSaved }: Props) {
  const [title, setTitle] = useState(video.title);
  const [description, setDescription] = useState(video.description);
  const [privacy, setPrivacy] = useState(video.privacy_status);
  const [thumbFile, setThumbFile] = useState<File | null>(null);
  const [thumbPreview, setThumbPreview] = useState<string | null>(null);
  const [thumbnailUrl, setThumbnailUrl] = useState(video.thumbnail_url);
  const [saving, setSaving] = useState(false);
  const [thumbBusy, setThumbBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  if (!open) return null;

  const save = async () => {
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      await updateVideo(video.id, { title, description, privacy_status: privacy });
      onSaved?.();
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Gagal menyimpan.");
    } finally {
      setSaving(false);
    }
  };

  const onPickThumb = (file: File | null) => {
    setThumbFile(file);
    setError(null);
    if (file) {
      setThumbPreview(URL.createObjectURL(file));
    } else {
      setThumbPreview(null);
    }
  };

  const uploadThumb = async () => {
    if (!thumbFile) return;
    setThumbBusy(true);
    setError(null);
    const form = new FormData();
    form.append("file", thumbFile);
    try {
      const resp = await uploadThumbnail(video.id, form);
      setThumbnailUrl(resp.video.thumbnail_url);
      setThumbFile(null);
      setThumbPreview(null);
      setNotice("Thumbnail berhasil diunggah ke YouTube!");
      onSaved?.();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Gagal upload thumbnail.");
    } finally {
      setThumbBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div
        className="max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-900 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-zinc-100">Edit video</h3>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300" aria-label="Close">
            <X className="h-5 w-5" />
          </button>
        </div>
        {error && <div className="mb-4"><ErrorAlert message={error} /></div>}
        {notice && (
          <div className="mb-4 rounded-lg border border-emerald-800/60 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-300">
            {notice}
          </div>
        )}
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm text-zinc-400">Judul</label>
            <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>

          {/* Thumbnail */}
          <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-3">
            <label className="mb-2 flex items-center gap-1.5 text-sm text-zinc-400">
              <ImagePlus className="h-4 w-4" /> Thumbnail (JPEG/PNG/WEBP, max 2MB, 16:9)
            </label>
            <div className="flex items-center gap-3">
              {(thumbPreview || thumbnailUrl) ? (
                <img
                  src={thumbPreview ?? thumbnailUrl ?? ""}
                  alt="Thumbnail"
                  className="h-16 w-28 rounded border border-zinc-700 object-cover"
                />
              ) : (
                <div className="flex h-16 w-28 items-center justify-center rounded border border-dashed border-zinc-700 text-xs text-zinc-600">
                  tanpa thumbnail
                </div>
              )}
              <div className="flex-1">
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  className="block w-full text-xs text-zinc-400 file:mr-2 file:rounded-lg file:border-0 file:bg-zinc-800 file:px-2.5 file:py-1.5 file:text-xs file:text-zinc-200 hover:file:bg-zinc-700"
                  onChange={(e) => onPickThumb(e.target.files?.[0] ?? null)}
                />
                <Button
                  variant="secondary"
                  className="mt-2 h-8 text-xs"
                  loading={thumbBusy}
                  disabled={!thumbFile}
                  onClick={uploadThumb}
                >
                  Upload thumbnail
                </Button>
              </div>
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm text-zinc-400">Deskripsi</label>
            <textarea
              className="input min-h-[120px]"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-zinc-400">Visibilitas</label>
            <select className="input" value={privacy} onChange={(e) => setPrivacy(e.target.value)}>
              <option value="private">Private</option>
              <option value="unlisted">Unlisted</option>
              <option value="public">Public (butuh persetujuan)</option>
            </select>
            {privacy === "public" && video.privacy_status !== "public" && (
              <p className="mt-1 text-xs text-amber-400">
                Video akan langsung tampil publik setelah disimpan.
              </p>
            )}
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" onClick={onClose}>
              Batal
            </Button>
            <Button loading={saving} onClick={save}>
              Simpan
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
