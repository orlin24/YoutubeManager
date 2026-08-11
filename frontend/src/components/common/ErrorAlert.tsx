import { AlertTriangle } from "lucide-react";

interface Props {
  message: string;
  code?: string;
  onRetry?: () => void;
}

export function ErrorAlert({ message, code, onRetry }: Props) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-red-800/60 bg-red-950/40 px-4 py-3">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
      <div className="flex-1">
        <p className="text-sm text-red-300">{message}</p>
        {code && <p className="mt-0.5 text-xs text-red-500">{code}</p>}
      </div>
      {onRetry && (
        <button onClick={onRetry} className="text-xs font-medium text-red-300 hover:text-red-200">
          Retry
        </button>
      )}
    </div>
  );
}
