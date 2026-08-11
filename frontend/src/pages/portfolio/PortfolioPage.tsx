import { useCallback, useEffect, useState } from "react";
import { Activity, RefreshCw, TrendingDown, TrendingUp } from "lucide-react";
import {
  analyzeChannelLifecycle,
  fetchPortfolio,
  fetchPortfolioPriorities,
} from "../../services/api";
import type { PortfolioChannel, PortfolioOverview } from "../../services/api";
import { Badge } from "../../components/common/Badge";
import { Button, Spinner } from "../../components/common/Button";
import { Card } from "../../components/common/Card";
import { EmptyState } from "../../components/common/EmptyState";
import { ErrorAlert } from "../../components/common/ErrorAlert";

const MODE_TONE: Record<string, "blue" | "green" | "violet" | "amber" | "red"> = {
  NEW: "blue",
  GROWTH: "green",
  MONETIZED: "violet",
  SCALE: "amber",
  RECOVERY: "red",
};

const PRIORITY_TONE: Record<string, "red" | "amber" | "blue" | "gray"> = {
  CRITICAL: "red",
  HIGH: "amber",
  MEDIUM: "blue",
  LOW: "gray",
};

export default function PortfolioPage() {
  const [portfolio, setPortfolio] = useState<PortfolioOverview | null>(null);
  const [priorities, setPriorities] = useState<
    Array<{ channel_title: string; priority: string; title: string; reason: string }>
  >([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([fetchPortfolio(), fetchPortfolioPriorities()])
      .then(([p, pr]) => {
        setPortfolio(p);
        setPriorities(pr.items);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Gagal memuat portfolio."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const onAnalyze = async (channelId: string) => {
    setAnalyzing(channelId);
    setError(null);
    try {
      await analyzeChannelLifecycle(channelId);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analisis gagal.");
    } finally {
      setAnalyzing(null);
    }
  };

  const modeOrder = ["NEW", "GROWTH", "MONETIZED", "SCALE", "RECOVERY"];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">Portfolio</h1>
          <p className="text-sm text-zinc-500">Tahap lifecycle tiap channel + prioritas aksi AI harian.</p>
        </div>
        <Button variant="secondary" onClick={load} loading={loading}>
          <RefreshCw className="h-4 w-4" /> Muat ulang
        </Button>
      </div>

      {error && <ErrorAlert message={error} onRetry={load} />}

      {loading && !portfolio ? (
        <div className="flex justify-center py-16 text-brand-400">
          <Spinner className="h-6 w-6" />
        </div>
      ) : !portfolio || portfolio.total === 0 ? (
        <EmptyState
          icon={Activity}
          title="Belum ada analisis lifecycle"
          description="Jalankan analisis di salah satu channel untuk memulai."
        />
      ) : (
        <>
          <div className="grid gap-3 md:grid-cols-5">
            {modeOrder.map((m) => (
              <Card key={m} className="p-4">
                <div className="flex items-center justify-between">
                  <Badge tone={MODE_TONE[m]}>{portfolio.labels[m] ?? m}</Badge>
                  <span className="text-lg font-semibold text-zinc-100">{portfolio.by_mode[m] ?? 0}</span>
                </div>
                <p className="mt-2 text-[11px] leading-snug text-zinc-500">{portfolio.objectives[m] ?? ""}</p>
              </Card>
            ))}
          </div>

          <Card title="Perbandingan channel" subtitle={`${portfolio.total} channel terpantau`}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-800 text-left text-xs text-zinc-500">
                    <th className="py-2 pr-3 font-medium">Channel</th>
                    <th className="px-3 py-2 font-medium">Mode</th>
                    <th className="px-3 py-2 font-medium">Kesehatan</th>
                    <th className="px-3 py-2 font-medium">Tren 28h</th>
                    <th className="px-3 py-2 font-medium">Subs</th>
                    <th className="px-3 py-2 font-medium">Views 28h</th>
                    <th className="px-3 py-2 font-medium">Analisis</th>
                  </tr>
                </thead>
                <tbody>
                  {portfolio.channels.map((c: PortfolioChannel) => (
                    <tr key={c.channel_id} className="border-b border-zinc-800/60">
                      <td className="py-2.5 pr-3 font-medium text-zinc-200">{c.title}</td>
                      <td className="px-3 py-2.5">
                        <Badge tone={MODE_TONE[c.mode] ?? "gray"}>{c.mode_label}</Badge>
                      </td>
                      <td className="px-3 py-2.5 text-zinc-300">
                        {c.health_score != null ? `${c.health_score}/100` : "-"}
                      </td>
                      <td className="px-3 py-2.5">
                        {c.growth_pct == null ? (
                          <span className="text-zinc-600">-</span>
                        ) : (
                          <span className={`inline-flex items-center gap-1 ${c.growth_pct >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                            {c.growth_pct >= 0 ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
                            {c.growth_pct > 0 ? "+" : ""}
                            {c.growth_pct}%
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-zinc-300">{(c.subscribers ?? 0).toLocaleString()}</td>
                      <td className="px-3 py-2.5 text-zinc-300">{(c.views_28d ?? 0).toLocaleString()}</td>
                      <td className="px-3 py-2.5">
                        <Button variant="ghost" className="h-7 px-2 text-xs" loading={analyzing === c.channel_id} onClick={() => onAnalyze(c.channel_id)}>
                          Analisis
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card title="Prioritas aksi AI hari ini" subtitle="Diurutkan dari yang paling kritis">
            {priorities.length === 0 ? (
              <p className="text-sm text-zinc-500">Belum ada prioritas. Jalankan analisis pada channel terlebih dahulu.</p>
            ) : (
              <div className="space-y-2">
                {priorities.map((p, i) => (
                  <div key={i} className="flex items-start gap-3 rounded-lg border border-zinc-800 bg-zinc-950/50 px-3 py-2">
                    <Badge tone={PRIORITY_TONE[p.priority] ?? "gray"}>{p.priority}</Badge>
                    <div className="min-w-0">
                      <p className="text-sm text-zinc-200">
                        <span className="font-medium">{p.channel_title}</span> - {p.title}
                      </p>
                      <p className="text-xs text-zinc-500">{p.reason}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
