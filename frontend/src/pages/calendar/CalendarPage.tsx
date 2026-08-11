import { useCallback, useEffect, useState } from "react";
import { CalendarDays, RefreshCw } from "lucide-react";
import { advanceQueueItem, buildCalendar, fetchFactoryQueue, runContentPipeline } from "../../services/api";
import { Badge } from "../../components/common/Badge";
import { Button, Spinner } from "../../components/common/Button";
import { Card } from "../../components/common/Card";
import { ErrorAlert } from "../../components/common/ErrorAlert";
import { useChannelStore } from "../../stores/channel";

const TYPE_TONE: Record<string, "green" | "blue" | "violet" | "gray"> = {
  PROVEN: "green",
  VARIATION: "blue",
  EXPERIMENT: "violet",
};

// Status yang bisa dimajukan satu tahap pipeline.
const ADVANCEABLE: Record<string, boolean> = {
  RESEARCH: true,
  BRIEF: true,
  DRAFT: true,
  QUALITY_CHECK: true,
  READY: true,
  PRODUCTION: true,
  UPLOAD_QUEUE: true,
  SCHEDULED: true,
};

export default function CalendarPage() {
  const { channels, selectedChannelId, selectChannel, refreshChannels } = useChannelStore();
  const [plan, setPlan] = useState<Array<{ date: string; title: string; content_type: string; status: string; priority: number }>>([]);
  const [queue, setQueue] = useState<Array<{ id: string; title: string; content_type: string; status: string; priority: number }>>([]);
  const [dryRun, setDryRun] = useState<{ ideas: Array<{ idea: string; quality: string; score: number; queue_id: string | null }>; queued: number; note?: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [days, setDays] = useState(7);

  const load = useCallback(async () => {
    if (!selectedChannelId) return;
    setLoading(true);
    setError(null);
    try {
      const [p, q] = await Promise.all([
        buildCalendar(selectedChannelId, days),
        fetchFactoryQueue(selectedChannelId),
      ]);
      setPlan(p.plan);
      setQueue(q.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal memuat kalender.");
    } finally {
      setLoading(false);
    }
  }, [selectedChannelId, days]);

  useEffect(() => {
    refreshChannels().catch(() => undefined);
  }, [refreshChannels]);

  useEffect(() => {
    if (selectedChannelId) load();
  }, [selectedChannelId, days, load]);

  const onPipeline = async (real = false) => {
    if (!selectedChannelId) return;
    setBusy(true);
    setError(null);
    try {
      const r = await runContentPipeline(selectedChannelId, 3, !real);
      setDryRun(real ? null : { ideas: r.ideas, queued: r.queued, note: r.note });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Pipeline gagal.");
    } finally {
      setBusy(false);
    }
  };

  const onAdvance = async (q: { id: string; title: string; status: string }) => {
    setBusy(true);
    setError(null);
    try {
      await advanceQueueItem(q.id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal memajukan status.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-zinc-100">
            <CalendarDays className="h-5 w-5 text-brand-400" /> Calendar
          </h1>
          <p className="text-sm text-zinc-500">Rencana produksi & jadwal publish per channel.</p>
        </div>
        <div className="flex items-center gap-2">
          <select className="input h-9 w-36" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={7}>7 hari</option>
            <option value={14}>14 hari</option>
            <option value={30}>30 hari</option>
          </select>
          <Button variant="secondary" loading={loading} onClick={load}>
            <RefreshCw className="h-4 w-4" /> Muat ulang
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <label className="text-sm text-zinc-400">Channel</label>
        <select className="input h-9 w-64" value={selectedChannelId ?? ""} onChange={(e) => selectChannel(e.target.value)}>
          <option value="">Pilih channel...</option>
          {channels.map((c) => (
            <option key={c.id} value={c.id}>{c.title}</option>
          ))}
        </select>
      </div>

      {error && <ErrorAlert message={error} onRetry={load} />}

      {loading ? (
        <div className="flex justify-center py-12 text-brand-400"><Spinner className="h-6 w-6" /></div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Rencana (kalender)" subtitle={`${days} hari ke depan`}>
            {plan.length === 0 ? (
              <p className="text-sm text-zinc-500">Belum ada item terjadwal. Jalankan Content Factory untuk mengisi queue.</p>
            ) : (
              <div className="space-y-2">
                {plan.map((p, i) => (
                  <div key={i} className="flex items-start gap-3 rounded-lg border border-zinc-800 bg-zinc-950/50 px-3 py-2">
                    <span className="w-24 shrink-0 text-xs font-medium text-zinc-400">{p.date}</span>
                    <Badge tone={TYPE_TONE[p.content_type] ?? "gray"}>{p.content_type}</Badge>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm text-zinc-200">{p.title}</p>
                      <p className="text-xs text-zinc-600">prioritas {p.priority} · {p.status}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title="Content Queue" subtitle={`${queue.length} item di antrean`}>
            {dryRun && (
              <div className="mb-4 rounded-lg border border-dashed border-brand-500/40 bg-brand-500/5 p-3">
                <p className="text-xs font-medium text-brand-300">{dryRun.note ?? "Hasil dry run"}</p>
                {dryRun.ideas.length === 0 ? (
                  <p className="mt-1 text-sm text-zinc-500">Tidak ada ide yang dihasilkan. Coba lagi.</p>
                ) : (
                  <ul className="mt-2 space-y-2">
                    {dryRun.ideas.map((id, i) => (
                      <li key={i} className="flex items-start gap-2 rounded-md bg-zinc-950/60 px-2 py-1.5">
                        <Badge tone={id.quality === "PASS" ? "green" : id.quality === "WARN" ? "yellow" : "red"}>
                          {id.quality}
                        </Badge>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm text-zinc-200">{id.idea}</p>
                          <p className="text-xs text-zinc-600">skor kualitas {id.score}/100</p>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button variant="secondary" loading={busy} onClick={() => onPipeline(true)}>
                    Jalankan & simpan ({dryRun.ideas.length} ide)
                  </Button>
                </div>
              </div>
            )}
            {queue.length === 0 ? (
              <div>
                <p className="text-sm text-zinc-500">Queue kosong. Jalankan pipeline (dry run) untuk melihat alurnya.</p>
                <Button className="mt-3" loading={busy} onClick={() => onPipeline(false)}>
                  Jalankan Content Pipeline (dry run)
                </Button>
              </div>
            ) : (
              <div className="space-y-2">
                {queue.map((q) => (
                  <div key={q.id} className="flex items-start gap-3 rounded-lg border border-zinc-800 bg-zinc-950/50 px-3 py-2">
                    <Badge tone={TYPE_TONE[q.content_type] ?? "gray"}>{q.content_type}</Badge>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm text-zinc-200">{q.title}</p>
                      <p className="text-xs text-zinc-600">prioritas {q.priority} · {q.status}</p>
                    </div>
                    <button
                      className="rounded-md border border-brand-500/40 px-2 py-1 text-xs text-brand-300 hover:bg-brand-500/10 disabled:opacity-40"
                      disabled={busy || !ADVANCEABLE[q.status]}
                      title="Majukan satu tahap pipeline"
                      onClick={() => onAdvance(q)}
                    >
                      Advance →
                    </button>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
