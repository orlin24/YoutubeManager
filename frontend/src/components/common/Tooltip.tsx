import { HelpCircle } from "lucide-react";

/** Keterangan ramah pengguna (audit #24): tooltip untuk istilah teknis seperti
 * CTR, Retensi, RPM, Keyakinan (confidence) dan Baseline. */
export function Tooltip({ text, className = "" }: { text: string; className?: string }) {
  return (
    <span className={`group relative inline-flex align-middle ${className}`}>
      <HelpCircle className="h-3.5 w-3.5 cursor-help text-zinc-600 hover:text-zinc-400" />
      <span className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-1.5 hidden w-60 -translate-x-1/2 rounded-lg border border-zinc-700 bg-zinc-900 p-2 text-[11px] font-normal leading-snug text-zinc-300 shadow-xl group-hover:block">
        {text}
      </span>
    </span>
  );
}
