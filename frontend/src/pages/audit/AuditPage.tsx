import { useCallback, useEffect, useState } from "react";
import { ScrollText } from "lucide-react";
import { fetchAudit } from "../../services/api";
import { useChannelStore } from "../../stores/channel";
import type { AuditEntry } from "../../types";
import { ApiError } from "../../services/api";
import { Badge, toneForStatus } from "../../components/common/Badge";
import { EmptyState } from "../../components/common/EmptyState";
import { ErrorAlert } from "../../components/common/ErrorAlert";
import { Pagination } from "../../components/common/Pagination";
import { SkeletonRow } from "../../components/common/SkeletonRow";
import { formatDateTime } from "../../utils/format";

const PAGE_SIZE = 50;

export default function AuditPage() {
  const selectedChannelId = useChannelStore((s) => s.selectedChannelId);
  const [items, setItems] = useState<AuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    const q: Record<string, unknown> = { limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE };
    if (selectedChannelId) q.channel_id = selectedChannelId;
    fetchAudit(q)
      .then((r) => {
        setItems(r.items);
        setTotal(r.total);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Failed to load audit log."))
      .finally(() => setLoading(false));
  }, [page, selectedChannelId]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-bold text-zinc-100">
          <ScrollText className="h-5 w-5 text-brand-400" /> Audit Logs
        </h1>
        <p className="text-sm text-zinc-500">
          Every meaningful action is recorded here - who did what, when, and the result
        </p>
      </div>

      {error && <ErrorAlert message={error} onRetry={load} />}
      {loading ? (
        <SkeletonRow rows={8} />
      ) : items.length === 0 ? (
        <EmptyState title="No audit entries yet" description="Actions will appear here as you use the app." />
      ) : (
        <>
          <ol className="relative space-y-4 border-l border-zinc-800 pl-5">
            {items.map((entry) => (
              <li key={entry.id} className="relative">
                <span className="absolute -left-[26px] top-1 h-3 w-3 rounded-full border-2 border-zinc-950 bg-zinc-700" />
                <div className="card p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-medium text-zinc-200">
                      {entry.action.replace(/_/g, " ")}
                      {entry.target ? <span className="text-zinc-500"> · {entry.target}</span> : null}
                    </p>
                    {entry.result && <Badge tone={toneForStatus(entry.result)}>{entry.result}</Badge>}
                  </div>
                  <p className="mt-1 text-xs text-zinc-600">{formatDateTime(entry.created_at)}</p>
                  {Object.keys(entry.metadata ?? {}).length > 0 && (
                    <pre className="mt-2 overflow-x-auto rounded-lg bg-zinc-950 p-2 text-[11px] text-zinc-500">
                      {JSON.stringify(entry.metadata)}
                    </pre>
                  )}
                </div>
              </li>
            ))}
          </ol>
          <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPage={setPage} />
        </>
      )}
    </div>
  );
}
