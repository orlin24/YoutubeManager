import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AlertTriangle, CheckCircle2, X } from "lucide-react";

type Notice = { tone: "success" | "error"; title: string; message: string } | null;

function parseNotice(error: string | null, connected: string | null): Notice {
  if (connected === "1") {
    return {
      tone: "success",
      title: "Channel YouTube berhasil dihubungkan!",
      message: "Buka halaman Channels untuk melihat channel kamu, lalu klik Sync untuk menarik data.",
    };
  }
  switch (error) {
    case "google_auth_failed":
      return {
        tone: "error",
        title: "Gagal menghubungkan YouTube.",
        message:
          "Kredensial Google mungkin salah, atau redirect URI tidak cocok. Buka Tutorial untuk memeriksa Client ID, Client Secret, dan redirect URI.",
      };
    case "google_auth_requires_login":
      return {
        tone: "error",
        title: "Silakan masuk dulu.",
        message: "Sesi login kamu sudah berakhir. Masuk kembali, lalu coba hubungkan channel YouTube lagi.",
      };
    default:
      return null;
  }
}

export default function OAuthNotice() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [notice, setNotice] = useState<Notice>(null);

  useEffect(() => {
    const error = searchParams.get("error");
    const connected = searchParams.get("connected");
    const parsed = parseNotice(error, connected);
    if (parsed) {
      setNotice(parsed);
      // Clear the query params so a refresh does not re-show the banner.
      searchParams.delete("error");
      searchParams.delete("connected");
      setSearchParams(searchParams, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!notice) return null;

  const styles =
    notice.tone === "success"
      ? "border-emerald-800/60 bg-emerald-950/40 text-emerald-300"
      : "border-amber-800/60 bg-amber-950/40 text-amber-200";

  return (
    <div className={`mb-5 flex items-start gap-3 rounded-xl border px-4 py-3.5 ${styles}`}>
      {notice.tone === "success" ? (
        <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-400" />
      ) : (
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-400" />
      )}
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold">{notice.title}</p>
        <p className="mt-0.5 text-xs opacity-90">{notice.message}</p>
        {notice.tone === "error" && (
          <Link to="/tutorial" className="mt-2 inline-block text-xs font-medium underline underline-offset-2">
            Buka Tutorial (panduan Client ID & redirect URI)
          </Link>
        )}
      </div>
      <button
        onClick={() => setNotice(null)}
        className="shrink-0 text-current opacity-60 hover:opacity-100"
        aria-label="Tutup"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
