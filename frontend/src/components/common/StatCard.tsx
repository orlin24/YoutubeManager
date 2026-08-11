import { LucideIcon, TrendingDown, TrendingUp } from "lucide-react";

interface Props {
  icon: LucideIcon;
  label: string;
  value: string;
  delta?: number | null;
  deltaLabel?: string;
}

export function StatCard({ icon: Icon, label, value, delta, deltaLabel }: Props) {
  const hasDelta = delta !== null && delta !== undefined && !Number.isNaN(delta);
  const positive = hasDelta && (delta as number) >= 0;
  return (
    <div className="card flex items-center gap-4">
      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-brand-600/15 text-brand-400">
        <Icon className="h-5 w-5" />
      </div>
      <div className="min-w-0">
        <p className="text-xs text-zinc-500">{label}</p>
        <p className="truncate text-xl font-semibold text-zinc-100">{value}</p>
        {hasDelta ? (
          <p className={`mt-0.5 flex items-center gap-1 text-xs ${positive ? "text-emerald-400" : "text-red-400"}`}>
            {positive ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
            {Math.abs(delta as number).toFixed(1)}% {deltaLabel ?? "vs prev period"}
          </p>
        ) : (
          <p className="mt-0.5 text-xs text-zinc-600">{deltaLabel ?? "no prior data"}</p>
        )}
      </div>
    </div>
  );
}
