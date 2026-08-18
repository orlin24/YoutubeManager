import { useCallback, useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Info, RefreshCw } from "lucide-react";
import { fetchRealtimeViews } from "../../services/api";
import { Button, Spinner } from "../../components/common/Button";
import { ErrorAlert } from "../../components/common/ErrorAlert";

interface RealtimeChartProps {
  channelId: string;
}

export default function RealtimeChart({ channelId }: RealtimeChartProps) {
  const [data, setData] = useState<Array<{ date: string; views: number }>>([]);
  const [disclaimer, setDisclaimer] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updated, setUpdated] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchRealtimeViews(channelId)
      .then((resp) => {
        setData(resp.items.map((i) => ({ date: i.date, views: i.views })));
        setDisclaimer(resp.disclaimer);
        setUpdated(
          new Date().toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
        );
      })
      .catch((e) => setError(e.message ?? "Gagal memuat data realtime."))
      .finally(() => setLoading(false));
  }, [channelId]);

  useEffect(() => {
    load();
  }, [load]);

  const total = data.reduce((s, d) => s + d.views, 0);

  return (
    <div className="mt-3 rounded-lg border border-zinc-800 bg-zinc-950/60 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-zinc-400">
          Penayangan 7 hari terakhir: <span className="font-semibold text-zinc-200">{total.toLocaleString()}</span>
          {updated && <span className="ml-1.5 text-zinc-600">· update {updated}</span>}
        </p>
        <Button variant="ghost" className="h-7 px-2 text-xs" loading={loading} onClick={load}>
          <RefreshCw className="h-3 w-3" /> Muat ulang
        </Button>
      </div>

      {error ? (
        <ErrorAlert message={error} onRetry={load} />
      ) : loading ? (
        <div className="flex h-32 items-center justify-center text-brand-400">
          <Spinner className="h-5 w-5" />
        </div>
      ) : (
        <>
          <div className="h-32">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} margin={{ top: 4, right: 4, left: -18, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2B2930" vertical={false} />
                <XAxis
                  dataKey="date"
                  stroke="#49454F"
                  fontSize={10}
                  tickFormatter={(d: string) => new Date(d).toLocaleDateString(undefined, { day: "numeric", month: "short" })}
                />
                <YAxis stroke="#49454F" fontSize={10} />
                <Tooltip
                  cursor={{ fill: "#2B293055" }}
                  contentStyle={{ background: "#211F26", border: "1px solid #49454F", borderRadius: 8 }}
                  labelStyle={{ color: "#E6E0E9" }}
                  formatter={(value) => [`${Number(value).toLocaleString()}`, "penayangan"]}
                  labelFormatter={(d) => new Date(String(d)).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })}
                />
                <Bar dataKey="views" fill="#D0BCFF" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 flex items-start gap-1.5 text-[11px] leading-snug text-zinc-600">
            <Info className="mt-0.5 h-3 w-3 shrink-0" />
            {disclaimer}
          </p>
        </>
      )}
    </div>
  );
}
