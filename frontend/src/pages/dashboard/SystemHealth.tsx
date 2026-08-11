import { Bot, Database, Cpu, Radio, Server } from "lucide-react";
import { useEffect, useState } from "react";
import { fetchHealth } from "../../services/api";
import type { HealthCheck } from "../../types";

const ICONS = {
  backend: Server,
  database: Database,
  youtube_api: Cpu,
  ai_provider: Bot,
  redis: Radio,
} as const;

export default function SystemHealth() {
  const [health, setHealth] = useState<HealthCheck | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setError(true));
  }, []);

  if (error) {
    return (
      <div className="flex flex-wrap gap-2">
        <span className="inline-flex items-center gap-1.5 text-xs text-red-400">
          <span className="h-1.5 w-1.5 rounded-full bg-red-400" /> System offline
        </span>
      </div>
    );
  }
  if (!health) {
    return (
      <div className="flex flex-wrap gap-2">
        <span className="inline-flex items-center gap-1.5 text-xs text-zinc-600">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-zinc-600" /> Checking...
        </span>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap gap-2">
      {Object.entries(health.checks).map(([key, status]) => {
        const Icon = ICONS[key as keyof typeof ICONS] ?? Server;
        const color =
          status === "ok" || status === "configured"
            ? "text-emerald-400"
            : status === "error"
              ? "text-red-400"
              : "text-zinc-500";
        const dot =
          status === "ok" || status === "configured"
            ? "bg-emerald-400"
            : status === "error"
              ? "bg-red-400"
              : "bg-zinc-600";
        return (
          <span
            key={key}
            className={`inline-flex items-center gap-1.5 rounded-full border border-zinc-800 bg-zinc-900 px-2.5 py-1 text-xs ${color}`}
            title={`${key}: ${status}`}
          >
            <Icon className="h-3 w-3" />
            {key.replace(/_/g, " ")}
            <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
          </span>
        );
      })}
    </div>
  );
}
