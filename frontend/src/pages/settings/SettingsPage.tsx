import { useCallback, useEffect, useRef, useState } from "react";
import { Download, Save, Settings as SettingsIcon, Upload } from "lucide-react";
import {
  fetchSettings,
  updateSettings,
  exportBackup,
  restoreBackup,
  saveTelegramCredentials,
  testTelegram,
} from "../../services/api";
import { AiCredentialForm, GoogleCredentialForm } from "../../components/settings/CredentialForms";
import type { Settings } from "../../types";
import { ApiError } from "../../services/api";
import { Badge } from "../../components/common/Badge";
import { Button } from "../../components/common/Button";
import { Card } from "../../components/common/Card";
import { ErrorAlert } from "../../components/common/ErrorAlert";
import { SkeletonRow } from "../../components/common/SkeletonRow";

const WEIGHT_HINTS: Record<string, string> = {
  ctr: "Click-through rate",
  retention: "Average view duration",
  views_velocity: "Views per day",
  subscriber_conversion: "Subscribers per view",
  watch_time: "Total watch time",
  engagement: "Likes + comments per view",
};

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [model, setModel] = useState("");
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const [exportPwd, setExportPwd] = useState("");
  const [restorePwd, setRestorePwd] = useState("");
  const [restoreFile, setRestoreFile] = useState<File | null>(null);
  const [exporting, setExporting] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [backupMsg, setBackupMsg] = useState<string | null>(null);
  const [backupError, setBackupError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [tgToken, setTgToken] = useState("");
  const [tgChatId, setTgChatId] = useState("");
  const [tgSaving, setTgSaving] = useState(false);
  const [tgTesting, setTgTesting] = useState(false);
  const [tgMsg, setTgMsg] = useState<string | null>(null);
  const [tgErr, setTgErr] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchSettings()
      .then((s) => {
        setSettings(s);
        setModel(s.ai.model);
        setWeights({ ...s.score_weights });
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Failed to load settings."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const onSave = async () => {
    if (!settings) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await updateSettings({
        ai: { model, enabled: settings.ai.enabled },
        score_weights: weights as unknown as Settings["score_weights"],
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to save settings.");
    } finally {
      setSaving(false);
    }
  };

  const onExport = async () => {
    setExporting(true);
    setBackupError(null);
    setBackupMsg(null);
    try {
      const { blob, filename } = await exportBackup(exportPwd || undefined);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setBackupMsg(
        exportPwd
          ? "Backup diunduh (terenkripsi password). Simpan file ini di tempat aman."
          : "Backup diunduh. File berisi token akses YouTube - sebaiknya gunakan password."
      );
    } catch (e) {
      setBackupError(e instanceof ApiError ? e.message : "Export failed.");
    } finally {
      setExporting(false);
    }
  };

  const onRestore = async () => {
    if (!restoreFile) return;
    const ok = window.confirm(
      "Restore akan MENGGANTI SEMUA data di server ini dengan isi file backup.\n\nLanjutkan?"
    );
    if (!ok) return;
    setRestoring(true);
    setBackupError(null);
    setBackupMsg(null);
    try {
      const resp = await restoreBackup(restoreFile, restorePwd || undefined);
      setRestoreFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      setBackupMsg(`Restore selesai: ${Object.entries(resp.restored).length} tabel dipulihkan. ${resp.note ?? ""}`);
      load(); // refresh settings after data replacement
    } catch (e) {
      setBackupError(e instanceof ApiError ? e.message : "Restore failed.");
    } finally {
      setRestoring(false);
    }
  };

  if (loading) return <SkeletonRow rows={6} />;
  if (error && !settings) return <ErrorAlert message={error} onRetry={load} />;
  if (!settings) return null;

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-bold text-zinc-100">
          <SettingsIcon className="h-5 w-5 text-brand-400" /> Settings
        </h1>
        <p className="text-sm text-zinc-500">AI model and performance score configuration</p>
      </div>

      {error && <ErrorAlert message={error} />}
      {saved && (
        <div className="rounded-lg border border-emerald-800/60 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-300">
          Settings saved.
        </div>
      )}

      <Card
        title="Koneksi & kredensial"
        subtitle="Simpan dari sini - backend otomatis menerapkan tanpa restart (alternatif .env tidak diperlukan)"
      >
        <div className="grid gap-6 md:grid-cols-2">
          <GoogleCredentialForm onSaved={() => setSaved(true)} />
          <AiCredentialForm onSaved={() => setSaved(true)} />
        </div>
      </Card>

      <Card
        title="AI provider (model default)"
        subtitle="Model dipakai untuk generate; kredensial diisi di form di atas atau backend/.env"
        actions={<Badge tone={settings.ai.enabled ? "green" : "amber"}>{settings.ai.enabled ? "enabled" : "disabled"}</Badge>}
      >
        <label className="mb-1 block text-sm text-zinc-400">Default model</label>
        <input className="input" value={model} onChange={(e) => setModel(e.target.value)} placeholder="gpt-4o-mini" />
        {!settings.ai.enabled && (
          <p className="mt-2 text-xs text-amber-400">
            AI is disabled. Masukkan API key di form di atas untuk mengaktifkan analisis, content plan,
            dan AI Assistant.
          </p>
        )}
      </Card>

      <Card title="AI Performance Score weights" subtitle="Heuristic 0-100 score - not an official YouTube metric">
        <div className="grid grid-cols-2 gap-3">
          {Object.entries(weights).map(([key, value]) => (
            <div key={key}>
              <label className="mb-1 block text-xs text-zinc-400">
                {key} <span className="text-zinc-600">({WEIGHT_HINTS[key] ?? ""})</span>
              </label>
              <input
                type="number"
                min={0}
                max={1}
                step={0.05}
                className="input"
                value={value}
                onChange={(e) => setWeights({ ...weights, [key]: Number(e.target.value) })}
              />
            </div>
          ))}
        </div>
      </Card>

      <Card title="Notifications" subtitle="AI melapor otomatis ke Telegram: laporan harian channel, dan notifikasi lainnya">
        {tgErr && <ErrorAlert message={tgErr} />}
        {tgMsg && (
          <div className="mb-4 rounded-lg border border-emerald-800/60 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-300">
            {tgMsg}
          </div>
        )}
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs text-zinc-400">Bot Token</label>
            <input
              className="input"
              value={tgToken}
              onChange={(e) => setTgToken(e.target.value)}
              placeholder="123456:ABC-DEF... (dari @BotFather)"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-zinc-400">Chat ID</label>
            <input
              className="input"
              value={tgChatId}
              onChange={(e) => setTgChatId(e.target.value)}
              placeholder="contoh: 123456789 (dari @userinfobot)"
            />
          </div>
        </div>
        <div className="mt-3 flex gap-2">
          <Button
            loading={tgSaving}
            onClick={async () => {
              setTgSaving(true);
              setTgErr(null);
              setTgMsg(null);
              try {
                const resp = await saveTelegramCredentials(tgToken, tgChatId);
                setTgMsg(resp.message);
              } catch (e) {
                setTgErr(e instanceof ApiError ? e.message : "Gagal menyimpan.");
              } finally {
                setTgSaving(false);
              }
            }}
          >
            Simpan kredensial
          </Button>
          <Button
            variant="secondary"
            loading={tgTesting}
            onClick={async () => {
              setTgTesting(true);
              setTgErr(null);
              setTgMsg(null);
              try {
                const resp = await testTelegram();
                setTgMsg(resp.message);
              } catch (e) {
                setTgErr(e instanceof ApiError ? e.message : "Pesan tes gagal.");
              } finally {
                setTgTesting(false);
              }
            }}
          >
            Kirim pesan tes
          </Button>
        </div>
        <p className="mt-2 text-xs text-zinc-500">
          Kredensial tersimpan di database (ikut terbawa backup) dan diterapkan langsung. Cara membuat bot:
          chat ke @BotFather untuk token, lalu chat ke @userinfobot untuk Chat ID Anda.
        </p>
      </Card>

      <Card title="Backup & Restore" subtitle="Satu file berisi semua data: channel, video, token login YouTube, content plan, riwayat AI, audit, dan pengaturan">
        {backupError && <ErrorAlert message={backupError} />}
        {backupMsg && (
          <div className="mb-4 rounded-lg border border-emerald-800/60 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-300">
            {backupMsg}
          </div>
        )}
        <div className="grid gap-6 md:grid-cols-2">
          <div>
            <h4 className="mb-1 text-sm font-medium text-zinc-200">Unduh backup</h4>
            <p className="mb-3 text-xs text-zinc-500">
              Untuk pindah server: unduh file ini, upload di server baru. Token login
              YouTube ikut tersimpan, jadi tidak perlu login ulang.
            </p>
            <label className="mb-1 block text-xs text-zinc-400">
              Password (opsional, untuk mengenkripsi file)
            </label>
            <div className="flex gap-2">
              <input
                type="password"
                className="input flex-1"
                value={exportPwd}
                onChange={(e) => setExportPwd(e.target.value)}
                placeholder="kosongkan jika tidak ingin password"
              />
              <Button variant="secondary" loading={exporting} onClick={onExport}>
                <Download className="h-4 w-4" /> Backup
              </Button>
            </div>
          </div>
          <div>
            <h4 className="mb-1 text-sm font-medium text-zinc-200">Pulihkan dari file</h4>
            <p className="mb-3 text-xs text-amber-400/90">
              Peringatan: restore akan MENGGANTI SEMUA data di server ini dengan isi file backup.
            </p>
            <label className="mb-1 block text-xs text-zinc-400">Password (jika backup dienkripsi)</label>
            <div className="flex gap-2">
              <input
                type="password"
                className="input flex-1"
                value={restorePwd}
                onChange={(e) => setRestorePwd(e.target.value)}
                placeholder="kosongkan jika tanpa password"
              />
              <input
                ref={fileInputRef}
                type="file"
                accept=".json,.enc,application/json,application/octet-stream"
                className="hidden"
                onChange={(e) => setRestoreFile(e.target.files?.[0] ?? null)}
              />
              <Button variant="secondary" onClick={() => fileInputRef.current?.click()}>Pilih file</Button>
              <Button variant="danger" loading={restoring} onClick={onRestore} disabled={!restoreFile}>
                <Upload className="h-4 w-4" /> Restore
              </Button>
            </div>
            <p className="mt-2 text-xs text-zinc-600">
              {restoreFile ? `File: ${restoreFile.name}` : "Belum ada file dipilih"}
            </p>
            <p className="mt-2 text-xs text-zinc-500">
              Agar channel langsung jalan tanpa login ulang di server baru: pakai file
              backend/.env yang sama, atau simpan kredensial Google lewat form
              "Koneksi & kredensial" di atas (ikut terbawa backup).
            </p>
          </div>
        </div>
      </Card>

      <div className="flex justify-end">
        <Button loading={saving} onClick={onSave}>
          <Save className="h-4 w-4" /> Save settings
        </Button>
      </div>
    </div>
  );
}
