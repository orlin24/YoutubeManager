import { ShieldAlert } from "lucide-react";
import type { AiAction } from "../../types";
import { Badge } from "../../components/common/Badge";

const toneFor = (permission: string) =>
  permission === "HIGH_RISK" ? "red" : permission === "WRITE" ? "amber" : "gray";

export default function ActionCard({ action }: { action: AiAction }) {
  return (
    <span className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-zinc-700 bg-zinc-800/70 px-2.5 py-1 text-xs text-zinc-200">
      {action.permission === "HIGH_RISK" && <ShieldAlert className="h-3 w-3 shrink-0 text-red-400" />}
      <span className="truncate">{action.label}</span>
      <Badge tone={toneFor(action.permission)}>{action.permission}</Badge>
    </span>
  );
}
