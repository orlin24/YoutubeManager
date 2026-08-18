import { useCallback, useEffect, useState } from "react";
import { Brain, CheckCircle2, FlaskConical, RefreshCw, XCircle } from "lucide-react";
import {
  evaluateLearning,
  fetchLearningMemory,
  fetchLearningOutcomes,
  fetchLearningStats,
} from "../../services/api";
import type {
  LearningMemoryRow,
  LearningOutcomeRow,
  LearningStats,
} from "../../services/api";
import { Button, Spinner } from "../../components/common/Button";
import { Card } from "../../components/common/Card";
import { ErrorAlert } from "../../components/common/ErrorAlert";
import { EmptyState } from "../../components/common/EmptyState";
import { Tooltip } from "../../components/common/Tooltip";

const KIND_LABEL: Record<string, string> = {
  WINNING_PATTERN: "Pola terbukti",
  FAILED_PATTERN: "Pola gagal",
  EXPERIMENT_RESULT: "Eksperimen",
  DECISION_OUTCOME: "Keputusan",
  CONFIDENCE_HISTORY: "Perubahan keyakinan",
  STRATEGY_HISTORY: "Strategi",
};

const KIND_TONE: Record<string, string> = {
  WINNING_PATTERN: "text-emerald-400",
  FAILED_PATTERN: "text-red-400",
  EXPERIMENT_RESULT: "text-violet-400",
  DECISION_OUTCOME: "text-sky-400",
  CONFIDENCE_HISTORY: "text-amber-400",
  STRATEGY_HISTORY: "text-zinc-300",
};

function confidenceColor(c: number) {
  if (c >= 65) return "bg-emerald-500";
  if (c >= 35) return "bg-amber-500";
  return "bg-red-500";
}

function Stat({ label, value, tooltip }: { label: string; value: string | number; tooltip?: string }) {
  return (
    <Card className="p-4">
      <p className="flex items-center gap-1 text-xs text-zinc-500">
        {label}
        {tooltip && <Tooltip text={tooltip} />}
      </p>
      <p className="mt-1 text-xl font-semibold text-zinc-100">{value}</p>
    </Card>
  );
}

export default function LearningPage() {
  const [stats, setStats] = useState<LearningStats | null>(null);
  const [memory, setMemory] = useState<LearningMemoryRow[]>([]);
  const [outcomes, setOutcomes] = useState<LearningOutcomeRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([fetchLearningStats(), fetchLearningMemory(), fetchLearningOutcomes()])
      .then(([s, m, o]) => {
        setStats(s);
        setMemory(m);
        setOutcomes(o);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Gagal memuat data pembelajaran."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const onEvaluate = async () => {
    setEvaluating(true);
    setError(null);
    setInfo(null);
    try {
      const res = await evaluateLearning();
      const total = (res?.evaluated ?? 0) + (res?.pending_left ?? 0);
      setInfo(
        total === 0
          ? "Tidak ada rekomendasi baru untuk dievaluasi. Rekomendasi perlu waktu ±7 hari setelah dibuat agar hasilnya bisa dibandingkan."
          : `Evaluasi selesai: ${res?.evaluated ?? 0} diproses, ${res?.updated ?? 0} keyakinan diperbarui.`
      );
      window.setTimeout(() => setInfo(null), 8000);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Evaluasi gagal.");
    } finally {
      setEvaluating(false);
    }
  };

  const pending = outcomes.filter((o) => o.status === "pending").length;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-zinc-100">
            <Brain className="h-5 w-5 text-violet-400" /> AI Learning
          </h1>
          <p className="text-sm text-zinc-500">
            AI belajar otomatis dari hasil nyata: rekomendasi dibandingkan dengan hasil aktual, keyakinan naik/turun, dan memori dipakai untuk keputusan berikutnya.
          </p>
        </div>
        <Button variant="secondary" onClick={onEvaluate} loading={evaluating}>
          <RefreshCw className="h-4 w-4" /> Evaluasi sekarang
        </Button>
      </div>

      {error && <ErrorAlert message={error} onRetry={load} />}
      {info && (
        <div className="flex items-start gap-2 rounded-lg border border-emerald-800 bg-emerald-950/40 px-3 py-2 text-sm text-emerald-300">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /> {info}
        </div>
      )}

      {loading && !stats ? (
        <div className="flex justify-center py-16 text-brand-400">
          <Spinner className="h-6 w-6" />
        </div>
      ) : !stats ? (
        <EmptyState icon={Brain} title="Belum ada data pembelajaran" description="Rekomendasi AI akan mulai terekam dan dievaluasi otomatis." />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Video dianalisis" value={stats.videos_analyzed.toLocaleString()} />
            <Stat
              label="Pola terbukti"
              value={stats.proven_patterns}
              tooltip="Pola yang konsisten outperform baseline channel (10+ video, keyakinan tinggi)."
            />
            <Stat
              label="Pola sedang diuji"
              value={stats.testing_patterns}
              tooltip="Eksperimen berjalan: belum cukup data untuk disebut terbukti."
            />
            <Stat
              label="Pola gagal"
              value={stats.failed_patterns}
              tooltip="Pola yang hasilnya di bawah target - AI menghindarinya."
            />
            <Stat label="Eksperimen aktif" value={stats.active_experiments} />
            <Stat
              label="Keyakinan rata-rata"
              value={
                memory.length
                  ? `${Math.round(memory.reduce((a, m) => a + (m.confidence || 0), 0) / memory.length)}/100`
                  : "-"
              }
              tooltip="Keyakinan (confidence) = seberapa kuat data mendukung pola. Bukan ukuran pasti."
            />
            <Stat label="Versi strategi" value={stats.strategy_version} tooltip="Setiap siklus evaluasi menaikkan versi strategi AI." />
            <Stat
              label="Terakhir belajar"
              value={stats.last_learned ? new Date(stats.last_learned).toLocaleDateString("id-ID") : "belum"}
            />
          </div>

          <Card
            title="Memori pembelajaran"
            subtitle={`${pending} rekomendasi menunggu evaluasi hasil`}
          >
            {memory.length === 0 ? (
              <p className="text-sm text-zinc-500">
                Belum ada memori. AI mulai belajar setelah rekomendasi pertama dievaluasi (otomatis, ±7 hari).
              </p>
            ) : (
              <div className="space-y-2">
                {memory.slice(0, 10).map((m) => (
                  <div key={m.id} className="flex items-start gap-3 rounded-lg border border-zinc-800 bg-zinc-950/50 px-3 py-2">
                    <span className={`mt-0.5 text-[10px] font-semibold uppercase tracking-wide ${KIND_TONE[m.kind] ?? "text-zinc-400"}`}>
                      {KIND_LABEL[m.kind] ?? m.kind}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-zinc-200">{m.pattern}</p>
                      <p className="text-xs text-zinc-500">{m.performance}</p>
                      {m.evidence && <p className="mt-0.5 line-clamp-2 text-[11px] text-zinc-600">{m.evidence}</p>}
                    </div>
                    <div className="w-24 shrink-0 pt-1">
                      <div className="h-1.5 overflow-hidden rounded-full bg-zinc-800">
                        <div className={`h-full ${confidenceColor(m.confidence)}`} style={{ width: `${Math.min(100, m.confidence)}%` }} />
                      </div>
                      <p className="mt-0.5 text-right text-[10px] text-zinc-500">{Math.round(m.confidence)}/100</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title="Rekomendasi vs hasil aktual" subtitle="Perbandingan ekspektasi dan realita (expected vs actual)">
            {outcomes.length === 0 ? (
              <p className="text-sm text-zinc-500">Belum ada rekomendasi terekam.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-zinc-800 text-left text-xs text-zinc-500">
                      <th className="py-2 pr-3 font-medium">Rekomendasi</th>
                      <th className="px-3 py-2 font-medium">Keyakinan</th>
                      <th className="px-3 py-2 font-medium">Target</th>
                      <th className="px-3 py-2 font-medium">Hasil aktual</th>
                      <th className="px-3 py-2 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {outcomes.slice(0, 20).map((o) => (
                      <tr key={o.id} className="border-b border-zinc-800/60 align-top">
                        <td className="min-w-[320px] py-2.5 pr-3">
                          <p className="break-words text-sm leading-snug text-zinc-200">{o.decision}</p>
                        </td>
                        <td className="whitespace-nowrap px-3 py-2.5 text-zinc-300">{o.confidence}</td>
                        <td className="px-3 py-2.5">
                          <p className="font-medium text-zinc-200">
                            {o.expected_value != null ? o.expected_value.toLocaleString() : "-"}
                          </p>
                          <p className="break-words text-[11px] leading-snug text-zinc-600">{o.expected_outcome}</p>
                        </td>
                        <td className="whitespace-nowrap px-3 py-2.5 text-zinc-300">
                          {o.actual_value != null ? o.actual_value.toLocaleString() : "-"}
                        </td>
                        <td className="whitespace-nowrap px-3 py-2.5">
                          {o.status === "evaluated" ? (
                            <span className="inline-flex items-center gap-1 text-xs text-emerald-400">
                              <CheckCircle2 className="h-3.5 w-3.5" /> Terverifikasi
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-xs text-amber-400">
                              <FlaskConical className="h-3.5 w-3.5" /> Menunggu
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <p className="flex items-center gap-1.5 text-[11px] text-zinc-600">
            <XCircle className="h-3 w-3" /> AI hanya menganalisis, merekomendasikan, belajar dan memperbarui memori - tidak pernah mengambil tindakan publikasi/penghapusan otomatis.
          </p>
        </>
      )}
    </div>
  );
}
