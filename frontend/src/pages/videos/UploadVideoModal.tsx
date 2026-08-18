import { useCallback, useEffect, useRef, useState } from "react";
import { CalendarRange, ImagePlus, Play, Sparkles, Upload, X } from "lucide-react";
import {
  fetchUploadStatus,
  generateDescription,
  generateSeo,
  updateContentPlan,
  uploadVideoCancel,
  uploadVideoChunk,
  uploadVideoFinalize,
  uploadVideoInit,
  uploadVideoResume,
} from "../../services/api";
import { fetchContentPlan } from "../../services/api";
import { ApiError } from "../../services/api";
import { useChannelStore } from "../../stores/channel";
import type { ContentPlanItem } from "../../types";
import { Button } from "../../components/common/Button";
import { ErrorAlert } from "../../components/common/ErrorAlert";

interface Props {
  open: boolean;
  onClose: () => void;
  onUploaded?: () => void;
}

const PLAN_STATUSES = ["IDEA", "DRAFT", "READY", "APPROVAL", "SCHEDULED"];

export default function UploadVideoModal({ open, onClose, onUploaded }: Props) {
  const selectedChannelId = useChannelStore((s) => s.selectedChannelId);
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [thumbFile, setThumbFile] = useState<File | null>(null);
  const [thumbPreview, setThumbPreview] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [privacy, setPrivacy] = useState("private");
  const [schedule, setSchedule] = useState(false);
  const [publishDate, setPublishDate] = useState("");
  const [publishTime, setPublishTime] = useState("19:00");
  const [tags, setTags] = useState<string[]>([]);
  const [synthetic, setSynthetic] = useState(true); // default: Ya (mengandung AI/edited content)
  const [planItems, setPlanItems] = useState<ContentPlanItem[]>([]);
  const [planItemId, setPlanItemId] = useState("");
  const [uploading, setUploading] = useState(false);
  const [pausedUploadId, setPausedUploadId] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadMessage, setUploadMessage] = useState("");
  const [aiBusy, setAiBusy] = useState<"desc" | "seo" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadPlan = useCallback(() => {
    if (!selectedChannelId) return;
    fetchContentPlan({ channel_id: selectedChannelId })
      .then((r) => setPlanItems(r.items.filter((i) => PLAN_STATUSES.includes(i.status))))
      .catch(() => undefined);
  }, [selectedChannelId]);

  useEffect(() => {
    if (open) loadPlan();
  }, [open, loadPlan]);

  if (!open) return null;

  const applyPlanItem = (id: string) => {
    setPlanItemId(id);
    const item = planItems.find((i) => i.id === id);
    if (!item) return;
    setTitle(item.title);
    setDescription(item.description || item.idea || "");
    if (item.target_keyword && !tags.includes(item.target_keyword)) {
      setTags((t) => [...t, item.target_keyword as string]);
    }
  };

  const genDescription = async () => {
    if (!title.trim()) {
      setError("Isi judul dulu, lalu generate deskripsi.");
      return;
    }
    setAiBusy("desc");
    setError(null);
    try {
      const resp = await generateDescription({ title, channel_id: selectedChannelId ?? undefined });
      setDescription(resp.description);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Gagal generate deskripsi.");
    } finally {
      setAiBusy(null);
    }
  };

  const genSeo = async () => {
    if (!title.trim()) {
      setError("Isi judul dulu, lalu generate SEO.");
      return;
    }
    setAiBusy("seo");
    setError(null);
    try {
      const resp = await generateSeo({ title, description, channel_id: selectedChannelId ?? undefined });
      const combined = [...(resp.keywords ?? []), ...(resp.tags ?? [])];
      setTags((prev) => Array.from(new Set([...prev, ...combined])).slice(0, 50));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Gagal generate SEO.");
    } finally {
      setAiBusy(null);
    }
  };

  const removeTag = (tag: string) => setTags((t) => t.filter((x) => x !== tag));

  const CHUNK_SIZE = 5 * 1024 * 1024; // 5 MB per chunk

  const pollUpload = (uploadId: string): Promise<void> =>
    new Promise((resolve) => {
      const tick = async () => {
        const st = await fetchUploadStatus(uploadId);
        setUploadProgress(Math.round(st.progress));
        setUploadMessage(st.message ?? "Uploading...");
        if (st.status === "completed") {
          const resp = st.result as Record<string, unknown> | undefined;
          if (planItemId) {
            updateContentPlan(planItemId, { status: "PUBLISHED" }).catch(() => undefined);
          }
          const warning = (resp?.thumbnail_warning as string | undefined) ?? null;
          const scheduled = (resp?.scheduled_for as string | undefined) ?? null;
          if (scheduled) {
            setNotice(
              `Video terjadwal: akan tampil publik otomatis pada ${new Date(scheduled).toLocaleString(undefined, {
                dateStyle: "medium",
                timeStyle: "short",
              })}.`
            );
          } else if (warning) {
            setNotice(warning);
          }
          onUploaded?.();
          onClose();
          setUploading(false);
          resolve();
          return;
        }
        if (st.status === "paused") {
          setError(st.message ?? "Upload terputus.");
          setPausedUploadId(uploadId);
          setUploading(false);
          resolve();
          return;
        }
        if (st.status === "failed") {
          setError(st.error ?? st.message ?? "Upload gagal.");
          setUploading(false);
          resolve();
          return;
        }
        setTimeout(tick, 700);
      };
      tick().catch((e) => {
        setError(e instanceof ApiError ? e.message : "Gagal memeriksa status upload.");
        setUploading(false);
        resolve();
      });
    });

  const doUpload = async () => {
    if (!file || !selectedChannelId) return;
    if (schedule && (!publishDate || !publishTime)) {
      setError("Video terjadwal butuh tanggal & jam tayang. Pilih keduanya dulu.");
      return;
    }
    setUploading(true);
    setError(null);
    setNotice(null);
    setUploadMessage("Mengirim video ke server...");
    setUploadProgress(0);
    try {
      // Phase 1: chunked upload browser -> server (resume-safe by offset).
      const total = file.size;
      let uploadId: string | null = null;
      let offset = 0;

      const meta = new FormData();
      meta.append("channel_id", selectedChannelId);
      meta.append("title", title);
      meta.append("description", description);
      meta.append("privacy_status", schedule ? "public" : privacy);
      if (schedule && publishDate && publishTime) {
        meta.append("publish_at", new Date(`${publishDate}T${publishTime}`).toISOString());
      }
      if (tags.length) meta.append("tags", tags.join(","));
      if (planItemId) meta.append("content_plan_item_id", planItemId);
      meta.append("contains_synthetic_media", synthetic ? "true" : "false");
      meta.append("total_bytes", String(total));
      meta.append("file", file.slice(0, CHUNK_SIZE), file.name);
      if (thumbFile) meta.append("thumbnail", thumbFile);

      const init = await uploadVideoInit(meta);
      uploadId = init.upload_id;
      offset = init.received_bytes;
      setUploadProgress(Math.min(Math.round((offset / total) * 90), 90));

      while (uploadId && offset < total) {
        const chunk = file.slice(offset, offset + CHUNK_SIZE);
        let sent = false;
        for (let attempt = 0; attempt < 6 && !sent; attempt++) {
          try {
            const r = await uploadVideoChunk(uploadId, chunk);
            offset = r.received_bytes;
            sent = true;
            setUploadProgress(Math.min(Math.round((offset / total) * 90), 90));
          } catch {
            // connection dropped: ask the server where it stopped, then resume there
            try {
              const st = await fetchUploadStatus(uploadId!);
              if (typeof st.received_bytes === "number") offset = st.received_bytes;
            } catch {
              /* server unreachable - keep last offset */
            }
            await new Promise((res) => setTimeout(res, 1200 * (attempt + 1)));
          }
        }
        if (!sent) throw new Error("Koneksi terputus berulang kali. Upload dihentikan, coba lagi.");
      }

      if (!uploadId) throw new Error("Gagal memulai sesi upload.");

      // Phase 2: finalize then poll the backend (YouTube resumable upload).
      await uploadVideoFinalize(uploadId);
      await pollUpload(uploadId);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Upload gagal.");
      setUploading(false);
    }
  };

  const onResumeUpload = async () => {
    if (!pausedUploadId) return;
    const id = pausedUploadId;
    setPausedUploadId(null);
    setUploading(true);
    setError(null);
    setNotice(null);
    try {
      await uploadVideoResume(id);
      await pollUpload(id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Gagal melanjutkan upload.");
      setUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div
        className="max-h-[92vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-900 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Upload className="h-5 w-5 text-brand-400" />
            <h3 className="text-sm font-semibold text-zinc-100">Upload video</h3>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300" aria-label="Close">
            <X className="h-5 w-5" />
          </button>
        </div>
        {error && <div className="mb-4"><ErrorAlert message={error} /></div>}
        {notice && (
          <div className="mb-4 rounded-lg border border-amber-800/60 bg-amber-950/40 px-4 py-3 text-sm text-amber-300">
            {notice}
          </div>
        )}
        <div className="space-y-4">
          {/* Ambil dari Content Plan */}
          <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-3">
            <label className="mb-1 flex items-center gap-1.5 text-sm text-zinc-400">
              <CalendarRange className="h-3.5 w-3.5" /> Ambil dari Content Plan (opsional)
            </label>
            <select
              className="input"
              value={planItemId}
              onChange={(e) => applyPlanItem(e.target.value)}
            >
              <option value="">-- Pilih ide dari Content Plan --</option>
              {planItems.map((i) => (
                <option key={i.id} value={i.id}>
                  [{i.status}] {i.title}
                </option>
              ))}
            </select>
            {planItemId && (
              <p className="mt-1.5 text-xs text-emerald-400">
                Judul & deskripsi terisi otomatis. Setelah upload, item ini menjadi PUBLISHED.
              </p>
            )}
          </div>

          <div>
            <label className="mb-1 block text-sm text-zinc-400">
              Video file <span className="text-zinc-600">(tanpa batas ukuran - sesuai kuota YouTube 256GB/12 jam)</span>
            </label>
            <input
              ref={fileRef}
              type="file"
              accept="video/*"
              className="block w-full text-sm text-zinc-400 file:mr-3 file:rounded-lg file:border-0 file:bg-zinc-800 file:px-3 file:py-2 file:text-sm file:text-zinc-200 hover:file:bg-zinc-700"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            {file && <p className="mt-1 text-xs text-zinc-500">{file.name}</p>}
          </div>

          {/* Thumbnail opsional */}
          <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-3">
            <label className="mb-2 flex items-center gap-1.5 text-sm text-zinc-400">
              <ImagePlus className="h-4 w-4" /> Thumbnail (opsional - JPEG/PNG/WEBP, max 2MB, 16:9)
            </label>
            <div className="flex items-center gap-3">
              {thumbPreview ? (
                <img src={thumbPreview} alt="Thumbnail" className="h-16 w-28 rounded border border-zinc-700 object-cover" />
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
                  onChange={(e) => {
                    const f = e.target.files?.[0] ?? null;
                    setThumbFile(f);
                    setThumbPreview(f ? URL.createObjectURL(f) : null);
                  }}
                />
                {thumbFile && (
                  <button
                    type="button"
                    className="mt-1 text-xs text-zinc-500 hover:text-red-400"
                    onClick={() => { setThumbFile(null); setThumbPreview(null); }}
                  >
                    Hapus thumbnail
                  </button>
                )}
              </div>
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm text-zinc-400">Judul</label>
            <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between">
              <label className="block text-sm text-zinc-400">Deskripsi</label>
              <Button
                variant="ghost"
                className="h-7 px-2 text-xs"
                loading={aiBusy === "desc"}
                onClick={genDescription}
              >
                <Sparkles className="h-3 w-3" /> Generate dengan AI
              </Button>
            </div>
            <textarea
              className="input min-h-[110px]"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          {/* SEO */}
          <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-3">
            <div className="flex items-center justify-between">
              <label className="text-sm text-zinc-400">SEO (keywords & tags)</label>
              <Button
                variant="ghost"
                className="h-7 px-2 text-xs"
                loading={aiBusy === "seo"}
                onClick={genSeo}
              >
                <Sparkles className="h-3 w-3" /> Generate SEO dengan AI
              </Button>
            </div>
            {tags.length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {tags.map((t) => (
                  <span
                    key={t}
                    className="inline-flex items-center gap-1 rounded-full bg-zinc-800 px-2 py-0.5 text-xs text-zinc-300"
                  >
                    {t}
                    <button onClick={() => removeTag(t)} className="text-zinc-500 hover:text-red-400" aria-label={`Hapus ${t}`}>
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                ))}
              </div>
            ) : (
              <p className="mt-1.5 text-xs text-zinc-600">
                Belum ada tags. Generate otomatis dari judul, atau isi manual setelah generate.
              </p>
            )}
          </div>

          {/* Penggunaan AI (disclosure konten sintetis) */}
          <div className="rounded-lg border border-amber-800/40 bg-amber-950/20 p-3">
            <p className="text-sm font-medium text-zinc-200">Penggunaan AI</p>
            <p className="mt-1 text-xs text-zinc-500">
              Apakah AI digunakan untuk membuat atau mengedit konten Anda dengan cara berikut?
            </p>
            <ul className="mt-2 space-y-1 pl-4 text-xs text-zinc-500">
              <li className="list-disc">Membuat orang sungguhan terlihat mengatakan atau melakukan sesuatu yang tidak mereka katakan atau lakukan</li>
              <li className="list-disc">Memodifikasi rekaman video suatu peristiwa atau tempat yang nyata</li>
              <li className="list-disc">Menghasilkan adegan yang terlihat realistis yang sebenarnya tidak pernah terjadi</li>
            </ul>
            <div className="mt-3 flex gap-4">
              <label className="flex items-center gap-2 text-sm text-zinc-300">
                <input
                  type="radio"
                  name="synthetic"
                  checked={synthetic}
                  onChange={() => setSynthetic(true)}
                  className="accent-amber-500"
                />
                Ya
              </label>
              <label className="flex items-center gap-2 text-sm text-zinc-300">
                <input
                  type="radio"
                  name="synthetic"
                  checked={!synthetic}
                  onChange={() => setSynthetic(false)}
                  className="accent-amber-500"
                />
                Tidak
              </label>
            </div>
          </div>

          {/* Publikasi: sekarang atau terjadwal (gaya YouTube) */}
          <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-3">
            <div className="mb-3 inline-flex rounded-lg bg-zinc-900 p-1">
              <button
                type="button"
                onClick={() => setSchedule(false)}
                className={`rounded-md px-4 py-1.5 text-xs font-medium transition-colors ${
                  !schedule ? "bg-brand-600 text-brand-950" : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                Publikasikan sekarang
              </button>
              <button
                type="button"
                onClick={() => setSchedule(true)}
                className={`rounded-md px-4 py-1.5 text-xs font-medium transition-colors ${
                  schedule ? "bg-brand-600 text-brand-950" : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                Terjadwal
              </button>
            </div>

            {schedule ? (
              <div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="mb-1 block text-sm text-zinc-400">Tanggal tayang</label>
                    <input
                      type="date"
                      className="input [color-scheme:dark]"
                      value={publishDate}
                      min={new Date().toISOString().split("T")[0]}
                      onChange={(e) => setPublishDate(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-sm text-zinc-400">Jam tayang</label>
                    <input
                      type="time"
                      className="input [color-scheme:dark]"
                      value={publishTime}
                      onChange={(e) => setPublishTime(e.target.value)}
                    />
                  </div>
                </div>
                <p className="mt-2 text-[11px] text-zinc-500">
                  Video tampil publik otomatis pada tanggal & jam yang dipilih (zona waktu perangkat kamu).
                </p>
              </div>
            ) : (
              <div>
                <label className="mb-1 block text-sm text-zinc-400">Visibilitas</label>
                <select className="input" value={privacy} onChange={(e) => setPrivacy(e.target.value)}>
                  <option value="private">Private (hanya kamu)</option>
                  <option value="unlisted">Unlisted (via link)</option>
                  <option value="public">Public (semua orang)</option>
                </select>
              </div>
            )}
          </div>

          {uploading && (
            <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-3">
              <div className="mb-1.5 flex items-center justify-between text-xs">
                <span className="text-zinc-300">{uploadMessage}</span>
                <span className="font-semibold text-brand-300">{uploadProgress}%</span>
              </div>
              <div className="h-2.5 w-full overflow-hidden rounded-full bg-zinc-800">
                <div
                  className="h-full rounded-full bg-brand-500 transition-all duration-300"
                  style={{ width: `${Math.max(2, uploadProgress)}%` }}
                />
              </div>
              <p className="mt-1.5 text-[11px] text-zinc-600">
                Jangan tutup halaman ini sampai upload selesai. Jika koneksi putus, upload
                dilanjutkan otomatis dari posisi terakhir.
              </p>
            </div>
          )}

          {pausedUploadId && !uploading && (
            <div className="rounded-lg border border-amber-800/60 bg-amber-950/30 p-3 text-xs">
              <p className="text-amber-200">
                Upload terputus, tapi bisa dilanjutkan dari posisi terakhir (tidak mulai dari 0).
              </p>
              <div className="mt-2 flex gap-2">
                <Button variant="secondary" className="h-8 text-xs" onClick={onResumeUpload}>
                  <Play className="h-3.5 w-3.5" /> Lanjutkan upload
                </Button>
                <Button
                  variant="ghost"
                  className="h-8 text-xs"
                  onClick={async () => {
                    const id = pausedUploadId;
                    setPausedUploadId(null);
                    setError(null);
                    if (id) {
                      try {
                        await uploadVideoCancel(id);
                      } catch {
                        /* ignore */
                      }
                    }
                  }}
                >
                  Batal & hapus
                </Button>
              </div>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" onClick={onClose} disabled={uploading}>
              Batal
            </Button>
            <Button
              loading={uploading}
              disabled={!file || !title || uploading || (schedule && (!publishDate || !publishTime))}
              onClick={doUpload}
            >
              <Upload className="h-4 w-4" /> {uploading ? "Mengunggah..." : "Upload"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
