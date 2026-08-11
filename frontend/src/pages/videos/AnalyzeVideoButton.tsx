import { useState } from "react";
import { BrainCircuit } from "lucide-react";
import { analyzeVideo } from "../../services/api";
import { ApiError } from "../../services/api";
import { Badge } from "../../components/common/Badge";
import { Button } from "../../components/common/Button";

interface Props {
  videoId: string;
  initialScore?: number | null;
  onScore?: (score: number | null) => void;
}

export default function AnalyzeVideoButton({ videoId, initialScore, onScore }: Props) {
  const [score, setScore] = useState<number | null>(initialScore ?? null);
  const [details, setDetails] = useState<{ strengths: string[]; weaknesses: string[] } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await analyzeVideo(videoId);
      setScore(resp.score);
      setDetails({ strengths: resp.strengths, weaknesses: resp.weaknesses });
      onScore?.(resp.score);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Analysis failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      <Button variant="secondary" className="h-8 text-xs" loading={loading} onClick={run}>
        <BrainCircuit className="h-3.5 w-3.5" /> Analyze
      </Button>
      {score !== null && score !== undefined && (
        <Badge tone={score >= 60 ? "green" : score >= 40 ? "amber" : "red"}>AI {Math.round(score)}</Badge>
      )}
      {error && <span className="text-xs text-red-400">{error}</span>}
      {details && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/70 p-3 text-xs">
          {details.strengths.length > 0 && (
            <p className="text-emerald-400">Strengths: {details.strengths.join(", ")}</p>
          )}
          {details.weaknesses.length > 0 && (
            <p className="mt-1 text-red-400">To improve: {details.weaknesses.join(", ")}</p>
          )}
        </div>
      )}
    </div>
  );
}
