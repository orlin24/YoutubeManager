import { useCallback, useEffect, useState } from "react";
import { Bot, OctagonAlert, Play, RotateCcw, ShieldCheck } from "lucide-react";
import {
  emergencyResume,
  emergencyStop,
  fetchAutoStatus,
  fetchAutoTasks,
  runAutoNow,
  setAutoDryRun,
  setAutoMode,
} from "../../services/api";
import { Badge } from "../../components/common/Badge";
import { Button } from "../../components/common/Button";
import { Card } from "../../components/common/Card";
import { ErrorAlert } from "../../components/common/ErrorAlert";
import type { AutoStatus } from "../../services/api";

const MODES = [
  { value: "OFF", label: "OFF (mati)" },
  { value: "RECOMMEND_ONLY", label: "RECOMMEND (hanya usul)" },
  { value: "SEMI_AUTO", label: "SEMI AUTO (risiko rendah jalan)" },
  { value: "FULL_AUTO", label: "FULL AUTO (semua kecuali berisiko)" },
];

const RISK_TONE: Record<string, "gray" | "green" | "amber" | "red"> = {
  LOW: "green",
  MEDIUM: "amber",
  HIGH: "red",
  CRITICAL: "red",
};

export default function AutonomousPage() {
  const [status, setStatus] = useState<AutoStatus | null>(null);
  const [tasks, setTasks] = useState<Array<{ id: string; task_type: string; instruction: string; priority: number; risk_level: string; status: string; error?: string | null }>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, t] = await Promise.all([fetchAutoStatus(), fetchAutoTasks()]);
      setStatus(s);
      setTasks(t.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal memuat status AI.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Aksi gagal.");
    } finally {
      setBusy(false);
    }
  };

  const stopped = !status || status.status === "STOPPED";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-zinc-100">
            <Bot className="h-5 w-5 text-brand-400" /> AI Autonom
          </h1>
          <p className="text-sm text-zinc-500">
            Karyawan AI 24/7: memantau, menganalisis, memberi tugas, dan (sesuai mode) menjalankannya.
          </p>
        </div>
        <Button variant="secondary" loading={busy} onClick={() => act(runAutoNow)}>
          <Play className="h-4 w-4" /> Jalankan siklus sekarang
        </Button>
      </div>

      {error && <ErrorAlert message={error} onRetry={load} />}

      <div className="grid gap-4 md:grid-cols-3">
        <Card title="Status AI">
          {!status ? (
            <p className="text-sm text-zinc-500">Memuat...</p>
          ) : (
            <div className="space-y-2 text-sm">
              <div className="flex items-center gap-2">
                <Badge tone={stopped ? "red" : "green"}>{status.status}</Badge>
                {status.emergency_stop && <Badge tone="red">EMERGENCY STOP</Badge>}
              </div>
              <p className="text-zinc-400">
                Siklus terakhir:{" "}
                <span className="text-zinc-200">{status.last_cycle ? new Date(status.last_cycle).toLocaleString("id-ID") : "belum ada"}</span>
              </p>
              <p className="text-zinc-400">
                Interval: <span className="text-zinc-200">{status.check_interval_minutes} menit</span>
              </p>
              <p className="text-zinc-400">
                Kuota aksi/hari: <span className="text-zinc-200">{status.max_actions_per_day}</span>
              </p>
            </div>
          )}
        </Card>

        <Card title="Mode operasi">
          <select
            className="input"
            value={status?.mode ?? "OFF"}
            onChange={(e) => act(() => setAutoMode(e.target.value))}
            disabled={!status}
          >
            {MODES.map((m) => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
          <label className="mt-3 flex items-center gap-2 text-sm text-zinc-300">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-zinc-700 bg-zinc-900"
              checked={status?.dry_run ?? true}
              onChange={(e) => act(() => setAutoDryRun(e.target.checked))}
            />
            Mode simulasi (DRY RUN - tidak menyentuh YouTube)
          </label>
          <p className="mt-2 text-[11px] text-zinc-600">
            DRY RUN aman: tugas dibuat & dianalisis, tetapi tidak ada perubahan nyata.
          </p>
        </Card>

        <Card title="Hari ini">
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="rounded-lg bg-zinc-900 p-3">
              <p className="text-xs text-zinc-500">Tugas dibuat</p>
              <p className="text-xl font-semibold text-zinc-100">{status?.tasks_today ?? 0}</p>
            </div>
            <div className="rounded-lg bg-zinc-900 p-3">
              <p className="text-xs text-zinc-500">Selesai</p>
              <p className="text-xl font-semibold text-emerald-400">{status?.completed_today ?? 0}</p>
            </div>
            <div className="rounded-lg bg-zinc-900 p-3">
              <p className="text-xs text-zinc-500">Menunggu persetujuan</p>
              <p className="text-xl font-semibold text-amber-400">{status?.waiting_approvals ?? 0}</p>
            </div>
            <div className="rounded-lg bg-zinc-900 p-3">
              <p className="text-xs text-zinc-500">Antrian</p>
              <p className="text-xl font-semibold text-zinc-100">{status?.pending ?? 0}</p>
            </div>
          </div>
          <div className="mt-3 flex gap-2">
            {stopped ? (
              <Button variant="secondary" loading={busy} onClick={() => act(emergencyResume)}>
                <RotateCcw className="h-4 w-4" /> Lanjutkan
              </Button>
            ) : (
              <Button variant="danger" loading={busy} onClick={() => act(emergencyStop)}>
                <OctagonAlert className="h-4 w-4" /> Emergency Stop
              </Button>
            )}
          </div>
        </Card>
      </div>

      <Card
        title="Daftar tugas AI"
        subtitle="Tugas dari siklus otomatis - persetujuan di halaman Approvals"
      >
        {tasks.length === 0 ? (
          <p className="flex items-center gap-2 text-sm text-zinc-500">
            <ShieldCheck className="h-4 w-4 text-emerald-500" />
            Belum ada tugas. Mode AI akan membuat tugas dari anomali & prioritas channel.
          </p>
        ) : (
          <div className="space-y-2">
            {tasks.map((t) => (
              <div key={t.id} className="flex items-start gap-3 rounded-lg border border-zinc-800 bg-zinc-950/50 px-3 py-2">
                <Badge tone={RISK_TONE[t.risk_level] ?? "gray"}>{t.risk_level}</Badge>
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-zinc-200">{t.instruction}</p>
                  <p className="text-xs text-zinc-600">
                    {t.task_type} · prioritas {t.priority} · {t.status}
                    {t.error ? ` · ${t.error}` : ""}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
