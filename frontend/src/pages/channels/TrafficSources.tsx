import { useCallback, useEffect, useState } from "react";
import { Info, RefreshCw } from "lucide-react";
import { fetchTrafficSources } from "../../services/api";
import { Button, Spinner } from "../../components/common/Button";
import { ErrorAlert } from "../../components/common/ErrorAlert";

interface TrafficSource {
  source: string;
  label: string;
  views: number;
  percent: number;
}

interface TrafficSourcesProps {
  channelId: string;
}

export default function TrafficSources({ channelId }: TrafficSourcesProps) {
  const [items, setItems] = useState<TrafficSource[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchTrafficSources(channelId)
      .then((resp) => {
        setItems(resp.items);
        setTotal(resp.total_views);
      })
      .catch((e) => setError(e.message ?? "Gagal memuat sumber traffic."))
      .finally(() => setLoading(false));
  }, [channelId]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="mt-3 rounded-lg border border-zinc-800 bg-zinc-950/60 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-zinc-400">
          Sumber traffic 28 hari:{" "}
          <span className="font-semibold text-zinc-200">{total.toLocaleString()} penayangan</span>
        </p>
        <Button variant="ghost" className="h-7 px-2 text-xs" loading={loading} onClick={load}>
          <RefreshCw className="h-3 w-3" /> Muat ulang
        </Button>
      </div>

      {error ? (
        <ErrorAlert message={error} onRetry={load} />
      ) : loading ? (
        <div className="flex h-20 items-center justify-center text-brand-400">
          <Spinner className="h-5 w-5" />
        </div>
      ) : items.length === 0 ? (
        <p className="text-xs text-zinc-600">Belum ada data sumber traffic untuk channel ini.</p>
      ) : (
        <div className="space-y-1.5">
          {items.map((s) => (
            <div key={s.source} className="flex items-center gap-2">
              <span className="w-36 shrink-0 truncate text-[11px] text-zinc-400">{s.label}</span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-zinc-800">
                <div
                  className="h-full rounded-full bg-indigo-500"
                  style={{ width: `${Math.max(s.percent, 1)}%` }}
                />
              </div>
              <span className="w-24 shrink-0 text-right text-[11px] text-zinc-300">
                {s.views.toLocaleString()} ({s.percent}%)
              </span>
            </div>
          ))}
          <p className="mt-2 flex items-start gap-1.5 text-[11px] leading-snug text-zinc-600">
            <Info className="mt-0.5 h-3 w-3 shrink-0" />
            Data langsung dari YouTube Analytics. "Rekomendasi video" = penayangan dari video yang
            disarankan YouTube, "Pencarian YouTube" = dari hasil pencarian.
          </p>
        </div>
      )}
    </div>
  );
}
