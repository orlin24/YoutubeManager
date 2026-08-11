import { useEffect, useState } from "react";
import { Brain, X } from "lucide-react";
import { fetchChannelProfile, updateChannelProfile } from "../../services/api";
import type { ChannelProfile } from "../../types";
import { ApiError } from "../../services/api";
import { Button } from "../../components/common/Button";
import { ErrorAlert } from "../../components/common/ErrorAlert";

interface Props {
  channelId: string;
  channelTitle: string;
  open: boolean;
  onClose: () => void;
  onSaved?: () => void;
}

const FIELDS: Array<{ key: keyof ChannelProfile; label: string; placeholder: string }> = [
  { key: "niche", label: "Niche / kategori konten", placeholder: "contoh: Teknologi, Kuliner, Gaming, Keuangan" },
  { key: "target_audience", label: "Target audiens", placeholder: "contoh: Pemula usia 18-34 yang suka coding" },
  { key: "language", label: "Bahasa konten", placeholder: "contoh: Indonesia, Inggris" },
  { key: "country", label: "Negara", placeholder: "contoh: ID, US" },
  { key: "content_style", label: "Gaya konten", placeholder: "contoh: Tutorial, Vlog, Review, Podcast" },
  { key: "upload_frequency", label: "Frekuensi upload (deskripsi)", placeholder: "contoh: 2x seminggu" },
  { key: "brand_rules", label: "Aturan brand", placeholder: "Nada bicara, hal yang boleh dan tidak boleh" },
];

export default function ChannelProfileModal({ channelId, channelTitle, open, onClose, onSaved }: Props) {
  const [form, setForm] = useState<Partial<ChannelProfile>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setLoading(true);
    fetchChannelProfile(channelId)
      .then(setForm)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Gagal memuat profil."))
      .finally(() => setLoading(false));
  }, [open, channelId]);

  if (!open) return null;

  const set = (key: keyof ChannelProfile, value: string) => setForm((f) => ({ ...f, [key]: value }));

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await updateChannelProfile(channelId, form);
      onSaved?.();
      onClose();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Gagal menyimpan profil.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-900 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Brain className="h-5 w-5 text-brand-400" />
            <h3 className="text-sm font-semibold text-zinc-100">Memori AI: {channelTitle}</h3>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300" aria-label="Close">
            <X className="h-5 w-5" />
          </button>
        </div>
        <p className="mb-4 text-xs text-zinc-500">
          Profil ini memberi AI konteks tentang channel kamu, sehingga analisis dan rekomendasi
          kontennya sesuai dengan niche dan audiens kamu.
        </p>
        {error && <div className="mb-4"><ErrorAlert message={error} /></div>}
        {loading ? (
          <div className="h-40 animate-pulse rounded-lg bg-zinc-800/60" />
        ) : (
          <div className="space-y-3">
            {FIELDS.map(({ key, label, placeholder }) => (
              <div key={key}>
                <label className="mb-1 block text-sm text-zinc-400">{label}</label>
                <input
                  className="input"
                  value={(form[key] as string) ?? ""}
                  placeholder={placeholder}
                  onChange={(e) => set(key, e.target.value)}
                />
              </div>
            ))}
            <div>
              <label className="mb-1 block text-sm text-zinc-400">
                Pengingat upload via Telegram
              </label>
              <select
                className="input"
                value={form.upload_cadence_days ?? 0}
                onChange={(e) =>
                  setForm((f) => ({ ...f, upload_cadence_days: Number(e.target.value) || 0 }))
                }
              >
                <option value={0}>Nonaktif</option>
                <option value={1}>Setiap hari</option>
                <option value={2}>Setiap 2 hari</option>
                <option value={3}>Setiap 3 hari</option>
                <option value={4}>Setiap 4 hari</option>
                <option value={5}>Setiap 5 hari</option>
                <option value={7}>1 minggu sekali</option>
                <option value={14}>2 minggu sekali</option>
              </select>
              <p className="mt-1 text-[11px] text-zinc-600">
                AI mengingatkan via Telegram jika channel belum upload sesuai jadwal
                (maksimal sekali per periode, jam 08.00-21.00).
              </p>
            </div>
            <div>
              <label className="flex items-center gap-2 text-sm text-zinc-300">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-zinc-700 bg-zinc-900"
                  checked={form.monetized ?? false}
                  onChange={(e) => setForm((f) => ({ ...f, monetized: e.target.checked }))}
                />
                Channel sudah monetisasi (ditandai manual)
              </label>
              <p className="mt-1 text-[11px] text-zinc-600">
                Tandai jika channel sudah lolos monetisasi - AI menyesuaikan mode (MONETIZED/SCALE).
              </p>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="ghost" onClick={onClose}>
                Batal
              </Button>
              <Button loading={saving} onClick={save}>
                Simpan profil
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
