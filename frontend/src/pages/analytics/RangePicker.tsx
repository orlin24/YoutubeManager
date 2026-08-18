interface Props {
  value: string;
  onChange: (range: string) => void;
}

const RANGES = ["7d", "28d", "90d", "365d", "custom"];

export default function RangePicker({ value, onChange }: Props) {
  return (
    <div className="inline-flex rounded-lg border border-zinc-800 bg-zinc-900 p-1">
      {RANGES.map((r) => (
        <button
          key={r}
          onClick={() => onChange(r)}
          className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
            value === r ? "bg-brand-600 text-brand-950" : "text-zinc-400 hover:text-zinc-200"
          }`}
        >
          {r === "custom" ? "Custom" : r}
        </button>
      ))}
    </div>
  );
}
