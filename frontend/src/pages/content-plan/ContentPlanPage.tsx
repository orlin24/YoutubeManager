import { useCallback, useEffect, useState } from "react";
import { CalendarRange, Lightbulb, Plus, Sparkles, Trash2, X } from "lucide-react";
import {
  createContentPlan,
  deleteContentPlan,
  fetchContentPlan,
  generateContentPatterns,
  generateContentPlan,
  updateContentPlan,
} from "../../services/api";
import type { ContentPatternRec } from "../../services/api";
import { useChannelStore } from "../../stores/channel";
import type { ContentPlanItem } from "../../types";
import { ApiError } from "../../services/api";
import { Badge, toneForStatus } from "../../components/common/Badge";
import { Button } from "../../components/common/Button";
import { EmptyState } from "../../components/common/EmptyState";
import { ErrorAlert } from "../../components/common/ErrorAlert";
import { SkeletonRow } from "../../components/common/SkeletonRow";
import { formatDate } from "../../utils/format";

const STATUSES = ["IDEA", "DRAFT", "READY", "APPROVAL", "SCHEDULED", "PUBLISHED", "CANCELLED"];

export default function ContentPlanPage() {
  const selectedChannelId = useChannelStore((s) => s.selectedChannelId);
  const channels = useChannelStore((s) => s.channels);
  const [items, setItems] = useState<ContentPlanItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [patternBusy, setPatternBusy] = useState(false);
  const [patterns, setPatterns] = useState<ContentPatternRec[] | null>(null);
  const [patternAnalysis, setPatternAnalysis] = useState<string>("");
  const [notice, setNotice] = useState<string | null>(null);

  const [form, setForm] = useState({
    title: "",
    description: "",
    idea: "",
    target_keyword: "",
    planned_date: "",
    notes: "",
  });

  const load = useCallback(() => {
    if (!selectedChannelId) return;
    setLoading(true);
    setError(null);
    fetchContentPlan({ channel_id: selectedChannelId })
      .then((r) => setItems(r.items))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Failed to load content plan."))
      .finally(() => setLoading(false));
  }, [selectedChannelId]);

  useEffect(() => {
    load();
  }, [load]);

  const onCreate = async () => {
    if (!selectedChannelId || !form.title.trim()) return;
    try {
      await createContentPlan({ channel_id: selectedChannelId, ...form, planned_date: form.planned_date || undefined });
      setForm({ title: "", description: "", idea: "", target_keyword: "", planned_date: "", notes: "" });
      setCreateOpen(false);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Create failed.");
    }
  };

  const onStatus = async (item: ContentPlanItem, status: string) => {
    try {
      await updateContentPlan(item.id, { status });
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Update failed.");
    }
  };

  const onDelete = async (item: ContentPlanItem) => {
    if (!window.confirm(`Delete "${item.title}"?`)) return;
    try {
      await deleteContentPlan(item.id);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Delete failed.");
    }
  };

  const onGenerate = async () => {
    if (!selectedChannelId) return;
    setAiBusy(true);
    setNotice(null);
    try {
      const resp = await generateContentPlan({ channel_id: selectedChannelId, days: 30 });
      setNotice(`AI generated ${resp.items.length} ideas. Review and refine them below.`);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "AI generation failed.");
    } finally {
      setAiBusy(false);
    }
  };

  const onPatterns = async () => {
    if (!selectedChannelId) return;
    setPatternBusy(true);
    setNotice(null);
    setError(null);
    setPatterns(null);
    try {
      const resp = await generateContentPatterns(selectedChannelId, 28);
      setPatterns(resp.recommendations);
      setPatternAnalysis(resp.analysis);
      setNotice(
        `3 rekomendasi judul tersimpan ke Content Plan (Terjadwal) untuk 3 hari ke depan.`
      );
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Analisis pola judul gagal.");
    } finally {
      setPatternBusy(false);
    }
  };

  if (channels.length === 0) {
    return (
      <EmptyState
        title="No channel connected"
        description="Connect a YouTube channel to build a content plan."
        action={
          <a href="http://localhost:5000/api/auth/google" className="btn-primary">
            Connect YouTube
          </a>
        }
      />
    );
  }

  const grouped = STATUSES.map((s) => ({ status: s, items: items.filter((i) => i.status === s) }));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-zinc-100">
            <CalendarRange className="h-5 w-5 text-brand-400" /> Content Plan
          </h1>
          <p className="text-sm text-zinc-500">Plan your uploads from idea to published</p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" loading={patternBusy} onClick={onPatterns}>
            <Lightbulb className="h-4 w-4" /> AI: Pola Judul dari Data
          </Button>
          <Button variant="secondary" loading={aiBusy} onClick={onGenerate}>
            <Sparkles className="h-4 w-4" /> Generate with AI
          </Button>
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" /> Add idea
          </Button>
        </div>
      </div>

      {patterns && (
        <div className="space-y-3">
          {patternAnalysis && (
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 px-4 py-3 text-xs leading-relaxed text-zinc-400">
              {patternAnalysis}
            </div>
          )}
          {patterns.map((p, i) => (
            <div key={i} className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-4">
              <div className="flex items-start justify-between gap-2">
                <h3 className="text-sm font-semibold text-zinc-100">
                  {i + 1}. {p.title}
                </h3>
                {p.target_keyword && (
                  <Badge tone="green">{p.target_keyword}</Badge>
                )}
              </div>
              {p.description && (
                <p className="mt-1 whitespace-pre-wrap text-xs text-zinc-400">{p.description}</p>
              )}
              {p.reason && (
                <p className="mt-2 rounded-md bg-amber-950/30 px-3 py-2 text-xs text-amber-200/90">
                  {p.reason}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {notice && (
        <div className="rounded-lg border border-emerald-800/60 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-300">
          {notice}
        </div>
      )}
      {error && <ErrorAlert message={error} onRetry={load} />}

      {loading ? (
        <SkeletonRow rows={4} />
      ) : items.length === 0 ? (
        <EmptyState
          title="No content plan yet"
          description="Add ideas manually or let the AI generate a 30-day plan."
          action={
            <Button onClick={onGenerate}>
              <Sparkles className="h-4 w-4" /> Generate with AI
            </Button>
          }
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {grouped.map(({ status, items: group }) => (
            <div key={status}>
              <div className="mb-2 flex items-center gap-2">
                <Badge tone={toneForStatus(status)}>{status}</Badge>
                <span className="text-xs text-zinc-600">{group.length}</span>
              </div>
              <div className="space-y-2">
                {group.map((item) => (
                  <div key={item.id} className="card p-3">
                    <p className="text-sm font-medium text-zinc-200">{item.title}</p>
                    {item.target_keyword && (
                      <p className="mt-1 text-xs text-brand-300">#{item.target_keyword}</p>
                    )}
                    {(item.planned_date || item.publish_date) && (
                      <p className="mt-1 text-xs text-zinc-500">
                        {item.planned_date ? `Planned ${formatDate(item.planned_date)}` : ""}
                        {item.publish_date ? ` · Publish ${formatDate(item.publish_date)}` : ""}
                      </p>
                    )}
                    {item.notes && <p className="mt-1 line-clamp-2 text-xs text-zinc-500">{item.notes}</p>}
                    <div className="mt-2 flex items-center gap-1">
                      <select
                        className="input h-7 flex-1 px-2 text-xs"
                        value={item.status}
                        onChange={(e) => onStatus(item, e.target.value)}
                      >
                        {STATUSES.map((s) => (
                          <option key={s} value={s}>{s}</option>
                        ))}
                      </select>
                      <button
                        className="text-zinc-600 hover:text-red-400"
                        onClick={() => onDelete(item)}
                        aria-label="Delete"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
                {group.length === 0 && (
                  <div className="rounded-lg border border-dashed border-zinc-800 p-3 text-center text-xs text-zinc-700">
                    empty
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {createOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => setCreateOpen(false)}>
          <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-900 p-6" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-zinc-100">New plan item</h3>
              <button onClick={() => setCreateOpen(false)} className="text-zinc-500"><X className="h-5 w-5" /></button>
            </div>
            <div className="space-y-3">
              <input className="input" placeholder="Title *" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
              <textarea className="input min-h-[70px]" placeholder="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
              <input className="input" placeholder="Idea" value={form.idea} onChange={(e) => setForm({ ...form, idea: e.target.value })} />
              <input className="input" placeholder="Target keyword" value={form.target_keyword} onChange={(e) => setForm({ ...form, target_keyword: e.target.value })} />
              <input type="date" className="input" value={form.planned_date} onChange={(e) => setForm({ ...form, planned_date: e.target.value })} />
              <textarea className="input min-h-[60px]" placeholder="Notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
              <Button className="w-full" disabled={!form.title.trim()} onClick={onCreate}>Create</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
