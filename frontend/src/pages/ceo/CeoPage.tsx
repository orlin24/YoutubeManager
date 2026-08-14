import { useCallback, useEffect, useState } from "react";
import { Crown, RefreshCw, Send } from "lucide-react";
import {
  fetchBiAccuracy,
  fetchBiOverview,
  fetchBiStrategy,
  refreshBi,
  simulateBi,
  fetchCeoAllocation,
  fetchCeoOpportunities,
  fetchCeoOverview,
  fetchCeoPriorities,
  fetchCeoRecommendation,
  fetchCeoRisks,
  fetchCeoScorecard,
  sendCeoTelegram,
} from "../../services/api";
import { Badge } from "../../components/common/Badge";
import { Button, Spinner } from "../../components/common/Button";
import { Card } from "../../components/common/Card";
import { ErrorAlert } from "../../components/common/ErrorAlert";

const PRIO_TONE: Record<string, "red" | "amber" | "blue" | "gray"> = {
  CRITICAL: "red",
  HIGH: "amber",
  MEDIUM: "blue",
  LOW: "gray",
};

export default function CeoPage() {
  const [data, setData] = useState<{ [k: string]: unknown }>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [bi, setBi] = useState<{ generated_at?: string | null; per_channel?: Array<Record<string, unknown>>; risks?: Array<Record<string, string>> }>({});
  const [strategy, setStrategy] = useState<Array<{ question: string; answer: string }>>([]);
  const [accuracy, setAccuracy] = useState<{ status: string; count: number; mape_pct?: number } | null>(null);
  const [sim, setSim] = useState<{ base_case: { views_delta_pct: number }; best_case: { views_delta_pct: number }; worst_case: { views_delta_pct: number }; confidence: number; risk: string; assumptions: string } | null>(null);
  const [uploads, setUploads] = useState(3);
  const [simBusy, setSimBusy] = useState(false);

  const loadBi = useCallback(async () => {
    try {
      const [b, st, ac] = await Promise.all([fetchBiOverview(), fetchBiStrategy(), fetchBiAccuracy()]);
      setBi(b);
      setStrategy(st.items);
      setAccuracy(ac);
    } catch {
      /* BI optional - dashboard tetap tampil */
    }
  }, []);

  const onSimulate = async () => {
    setSimBusy(true);
    try {
      const r = await simulateBi({ name: "Simulasi frekuensi upload", uploads_per_week: uploads });
      setSim(r);
    } catch {
      /* ignore */
    } finally {
      setSimBusy(false);
    }
  };

  const onRefreshBi = async () => {
    try {
      const r = await refreshBi();
      await loadBi();
    } catch {
      /* ignore */
    }
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [ov, prio, opp, rk, rec, alloc, sc] = await Promise.all([
        fetchCeoOverview(), fetchCeoPriorities(), fetchCeoOpportunities(),
        fetchCeoRisks(), fetchCeoRecommendation(), fetchCeoAllocation(), fetchCeoScorecard(),
      ]);
      setData({ ov, prio: prio.items, opp: opp.items, rk: rk.items, rec, alloc: alloc.items, sc });
      loadBi();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal memuat dashboard CEO.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const ov = data.ov as { total_channels?: number; monetized?: number; revenue?: number | null; views?: number; subscribers?: number; content_produced?: number; content_published?: number; ai_actions?: number } | undefined;
  const prio = (data.prio as Array<{ channel: string; priority: string; title: string; reason: string }>) ?? [];
  const opp = (data.opp as Array<{ channel: string; type: string; title: string; confidence: string }>) ?? [];
  const rk = (data.rk as Array<{ channel: string; level: string; title: string }>) ?? [];
  const rec = data.rec as { channel?: string; decision?: string; reason?: string; confidence?: string } | undefined;
  const alloc = (data.alloc as Array<{ channel: string; mode: string; share: number }>) ?? [];
  const sc = data.sc as { portfolio_health?: number | null; growth?: number | null; revenue?: number | null; content_efficiency?: number | null; experimentation?: number | null; risk?: string; portfolio_score?: { total?: number | null; breakdown?: { HEALTH?: number | null; GROWTH?: number | null; RISK?: number | null; OPPORTUNITY?: number | null; EXPERIMENTATION?: number | null }; note?: string } } | undefined;

  const onSend = async () => {
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      const r = await sendCeoTelegram();
      setMsg(r.message);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal mengirim laporan.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-zinc-100">
            <Crown className="h-5 w-5 text-amber-400" /> AI CEO
          </h1>
          <p className="text-sm text-zinc-500">Apa yang harus dilakukan hari ini? Jawaban dari data aktual portfolio Anda.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" loading={loading} onClick={load}>
            <RefreshCw className="h-4 w-4" /> Muat ulang
          </Button>
          <Button loading={busy} onClick={onSend}>
            <Send className="h-4 w-4" /> Kirim ke Telegram
          </Button>
        </div>
      </div>

      {error && <ErrorAlert message={error} onRetry={load} />}
      {msg && <div className="rounded-lg border border-emerald-800/60 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-300">{msg}</div>}

      {loading ? (
        <div className="flex justify-center py-16 text-brand-400"><Spinner className="h-6 w-6" /></div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Card className="p-4"><p className="text-xs text-zinc-500">Channel</p><p className="text-xl font-semibold text-zinc-100">{ov?.total_channels ?? 0}</p></Card>
            <Card className="p-4"><p className="text-xs text-zinc-500">Monetized</p><p className="text-xl font-semibold text-violet-400">{ov?.monetized ?? 0}</p></Card>
            <Card className="p-4"><p className="text-xs text-zinc-500">Views</p><p className="text-xl font-semibold text-zinc-100">{(ov?.views ?? 0).toLocaleString()}</p></Card>
            <Card className="p-4"><p className="text-xs text-zinc-500">Subscribers</p><p className="text-xl font-semibold text-zinc-100">{(ov?.subscribers ?? 0).toLocaleString()}</p></Card>
            <Card className="p-4"><p className="text-xs text-zinc-500">Revenue</p><p className="text-xl font-semibold text-emerald-400">{ov?.revenue != null ? ov.revenue.toLocaleString() : "N/A"}</p></Card>
            <Card className="p-4"><p className="text-xs text-zinc-500">Konten dibuat</p><p className="text-xl font-semibold text-zinc-100">{ov?.content_produced ?? 0}</p></Card>
            <Card className="p-4"><p className="text-xs text-zinc-500">Konten tayang</p><p className="text-xl font-semibold text-zinc-100">{ov?.content_published ?? 0}</p></Card>
            <Card className="p-4"><p className="text-xs text-zinc-500">Aksi AI</p><p className="text-xl font-semibold text-brand-400">{ov?.ai_actions ?? 0}</p></Card>
          </div>

          {rec && (
            <Card title="Rekomendasi AI" subtitle="Internal - tidak ada perubahan otomatis">
              <p className="text-sm text-zinc-200">
                Fokus pada <span className="font-semibold text-amber-300">{rec.channel}</span> - keputusan{" "}
                <Badge tone="amber">{rec.decision}</Badge>
              </p>
              <p className="mt-1 text-xs text-zinc-500">{rec.reason} (confidence {rec.confidence})</p>
            </Card>
          )}

          <div className="grid gap-4 lg:grid-cols-3">
            <Card title="Prioritas hari ini" subtitle="Maks 5 - dari data terbaru">
              {prio.length === 0 ? (
                <p className="text-sm text-zinc-500">Belum ada prioritas.</p>
              ) : (
                <div className="space-y-2">
                  {prio.map((p, i) => (
                    <div key={i} className="flex items-start gap-2 rounded-lg border border-zinc-800 bg-zinc-950/50 px-3 py-2">
                      <Badge tone={PRIO_TONE[p.priority] ?? "gray"}>{p.priority}</Badge>
                      <div className="min-w-0">
                        <p className="text-sm text-zinc-200"><span className="font-medium">{p.channel}</span> - {p.title}</p>
                        <p className="text-xs text-zinc-500">{p.reason}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            <Card title="Peluang teratas" subtitle="Dari pola pemenang terdeteksi">
              {opp.length === 0 ? (
                <p className="text-sm text-zinc-500">Belum ada peluang terdeteksi.</p>
              ) : (
                <div className="space-y-2">
                  {opp.map((o, i) => (
                    <div key={i} className="rounded-lg border border-emerald-900/50 bg-emerald-950/20 px-3 py-2">
                      <p className="text-sm text-zinc-200"><span className="font-semibold text-emerald-300">{o.channel}</span> - {o.type}</p>
                      <p className="truncate text-xs text-zinc-500">{o.title}</p>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            <Card title="Risiko teratas" subtitle="Dari deteksi risiko lifecycle">
              {rk.length === 0 ? (
                <p className="text-sm text-zinc-500">Tidak ada risiko tinggi.</p>
              ) : (
                <div className="space-y-2">
                  {rk.map((r, i) => (
                    <div key={i} className="rounded-lg border border-red-900/50 bg-red-950/20 px-3 py-2">
                      <p className="text-sm text-zinc-200"><span className="font-semibold text-red-300">{r.channel}</span> - {r.level}</p>
                      <p className="text-xs text-zinc-500">{r.title}</p>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Alokasi produksi" subtitle="Rekomendasi internal pembagian kapasitas">
              {alloc.map((a) => (
                <div key={a.channel} className="mb-2 flex items-center gap-2">
                  <span className="w-40 truncate text-xs text-zinc-400">{a.channel}</span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-zinc-800">
                    <div className="h-full rounded-full bg-indigo-500" style={{ width: `${Math.max(a.share, 2)}%` }} />
                  </div>
                  <span className="w-12 text-right text-xs text-zinc-300">{a.share}%</span>
                </div>
              ))}
            </Card>

            <Card title="Scorecard portfolio" subtitle="Skor internal - bukan metrik resmi YouTube">
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div className="rounded-lg bg-zinc-900 p-3"><p className="text-xs text-zinc-500">Kesehatan</p><p className="text-lg font-semibold text-zinc-100">{sc?.portfolio_health ?? "-"}</p></div>
                <div className="rounded-lg bg-zinc-900 p-3"><p className="text-xs text-zinc-500">Pertumbuhan</p><p className="text-lg font-semibold text-emerald-400">{sc?.growth != null ? `${sc.growth}%` : "-"}</p></div>
                <div className="rounded-lg bg-zinc-900 p-3"><p className="text-xs text-zinc-500">Eksperimen</p><p className="text-lg font-semibold text-violet-400">{sc?.experimentation ?? "-"}</p></div>
                <div className="rounded-lg bg-zinc-900 p-3"><p className="text-xs text-zinc-500">Risiko</p><p className="text-lg font-semibold text-red-400">{sc?.risk ?? "-"}</p></div>
              </div>
              {sc?.portfolio_score && (
                <>
                  <div className="mt-3 flex items-end gap-2 border-t border-zinc-800 pt-3">
                    <p className="text-2xl font-bold text-zinc-100">{sc.portfolio_score.total ?? "-"}</p>
                    <p className="pb-0.5 text-[11px] text-zinc-500">Skor portfolio (detail) · {sc.portfolio_score.note ?? ""}</p>
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-2 text-sm md:grid-cols-5">
                    {(
                      [
                        ["HEALTH", "Kesehatan"], ["GROWTH", "Pertumbuhan"], ["RISK", "Risiko"],
                        ["OPPORTUNITY", "Peluang"], ["EXPERIMENTATION", "Eksperimen"],
                      ] as const
                    ).map(([k, label]) => (
                      <div key={k} className="rounded-lg bg-zinc-900 p-2">
                        <p className="text-[10px] uppercase tracking-wide text-zinc-500">{label}</p>
                        <p className="text-base font-semibold text-zinc-100">{sc.portfolio_score.breakdown?.[k] ?? "-"}</p>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </Card>
          </div>

          <Card title="Business Intelligence" subtitle="Forecast statistik (range + confidence, bukan jaminan)">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-xs text-zinc-500">
                Snapshot: {bi.generated_at ? new Date(bi.generated_at).toLocaleString("id-ID") : "belum ada"} ·
                Akurasi: {accuracy && accuracy.status === "OK" ? `MAPE ${accuracy.mape_pct}%` : "INSUFFICIENT DATA"}
              </span>
              <Button variant="ghost" className="h-7 text-xs" onClick={onRefreshBi}>
                <RefreshCw className="h-3 w-3" /> Hitung ulang
              </Button>
            </div>
            <div className="grid gap-2 md:grid-cols-2">
              {((bi.per_channel ?? []) as Array<{ title?: string; views_forecast?: { status?: string; trend?: string; forecast?: { expected?: number; lower?: number; upper?: number; confidence?: number } } }>).map((c) => {
                const f = c.views_forecast;
                if (!f || f.status !== "OK" || !f.forecast) return null;
                return (
                  <div key={c.title} className="rounded-lg border border-zinc-800 bg-zinc-950/50 px-3 py-2">
                    <p className="text-xs font-medium text-zinc-400">{c.title} <span className="text-zinc-600">({f.trend})</span></p>
                    <p className="text-sm text-zinc-200">
                      {Math.round(f.forecast.expected ?? 0).toLocaleString()} views (30 hari)
                    </p>
                    <p className="text-[11px] text-zinc-500">
                      Rentang {Math.round(f.forecast.lower ?? 0).toLocaleString()} - {Math.round(f.forecast.upper ?? 0).toLocaleString()} ·
                      Confidence {f.forecast.confidence}%
                    </p>
                  </div>
                );
              })}
            </div>
          </Card>

          <Card title="What-if Simulator" subtitle="Model estimate - bukan jaminan">
            <div className="flex items-center gap-3">
              <span className="text-sm text-zinc-400">Upload/minggu:</span>
              <input
                type="range" min={0} max={10} value={uploads}
                onChange={(e) => setUploads(Number(e.target.value))}
                className="flex-1 accent-indigo-500"
              />
              <span className="w-8 text-center text-sm font-semibold text-zinc-100">{uploads}</span>
              <Button variant="secondary" loading={simBusy} onClick={onSimulate}>Simulasi</Button>
            </div>
            {sim && (
              <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                <div className="rounded-lg bg-emerald-950/40 p-3"><p className="text-xs text-zinc-500">Best</p><p className="text-lg font-semibold text-emerald-400">{sim.best_case.views_delta_pct > 0 ? "+" : ""}{sim.best_case.views_delta_pct}%</p></div>
                <div className="rounded-lg bg-zinc-900 p-3"><p className="text-xs text-zinc-500">Base</p><p className="text-lg font-semibold text-zinc-100">{sim.base_case.views_delta_pct > 0 ? "+" : ""}{sim.base_case.views_delta_pct}%</p></div>
                <div className="rounded-lg bg-red-950/40 p-3"><p className="text-xs text-zinc-500">Worst</p><p className="text-lg font-semibold text-red-400">{sim.worst_case.views_delta_pct > 0 ? "+" : ""}{sim.worst_case.views_delta_pct}%</p></div>
                <p className="col-span-3 text-[11px] text-zinc-600">Confidence {sim.confidence}% · Risiko {sim.risk} · {sim.assumptions}</p>
              </div>
            )}
          </Card>

          <Card title="Keputusan strategis (evidence-first)" subtitle="Jawaban 7 pertanyaan dari data aktual">
            <div className="space-y-2">
              {strategy.map((q, i) => (
                <div key={i} className="rounded-lg border border-zinc-800 bg-zinc-950/50 px-3 py-2">
                  <p className="text-xs font-medium text-amber-200/90">{q.question}</p>
                  <p className="text-sm text-zinc-300">{q.answer}</p>
                </div>
              ))}
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
