import { FormEvent, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Bot, KeyRound, UserPlus } from "lucide-react";
import { useAuthStore } from "../../stores/auth";
import { useChannelStore } from "../../stores/channel";
import { ApiError, fetchSetupStatus } from "../../services/api";
import { ErrorAlert } from "../../components/common/ErrorAlert";
import { Button } from "../../components/common/Button";

type Mode = "loading" | "setup" | "login";

export default function LoginPage() {
  const [mode, setMode] = useState<Mode>("loading");
  // setup fields
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const login = useAuthStore((s) => s.login);
  const setup = useAuthStore((s) => s.setup);
  const refreshChannels = useChannelStore((s) => s.refreshChannels);
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  useEffect(() => {
    fetchSetupStatus()
      .then((s) => setMode(s.setup_required ? "setup" : "login"))
      .catch(() => setMode("login"));
  }, []);

  const finish = async () => {
    let channels = [];
    try {
      channels = await refreshChannels();
    } catch {
      // ignore
    }
    navigate(from, { replace: true });
  };

  const onSetup = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("Konfirmasi password tidak sama.");
      return;
    }
    setLoading(true);
    try {
      await setup(name, email, password);
      await finish();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Setup gagal.");
    } finally {
      setLoading(false);
    }
  };

  const onLogin = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      await finish();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login gagal.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-600 text-brand-950">
            <Bot className="h-7 w-7" />
          </div>
          <h1 className="text-2xl font-bold text-zinc-100">AI YouTube Manager</h1>
          <p className="mt-1 text-sm text-zinc-500">Your AI employee for YouTube channel growth</p>
        </div>

        {mode === "loading" ? (
          <div className="card space-y-3">
            <div className="h-8 animate-pulse rounded-lg bg-zinc-800/60" />
            <div className="h-8 animate-pulse rounded-lg bg-zinc-800/60" />
            <div className="h-10 animate-pulse rounded-lg bg-zinc-800/60" />
          </div>
        ) : (
          <form
            onSubmit={mode === "setup" ? onSetup : onLogin}
            className="card space-y-4"
            autoComplete="on"
          >
            <div className="flex items-center gap-2">
              {mode === "setup" ? (
                <UserPlus className="h-5 w-5 text-brand-400" />
              ) : (
                <KeyRound className="h-5 w-5 text-brand-400" />
              )}
              <h2 className="text-lg font-semibold text-zinc-100">
                {mode === "setup" ? "Setup aplikasi (pertama kali)" : "Login"}
              </h2>
            </div>

            {mode === "setup" && (
              <p className="text-xs text-zinc-500">
                Aplikasi baru diinstall. Buat akun admin sekali saja - setelah ini tinggal login
                dengan email & password yang sama.
              </p>
            )}
            {error && <ErrorAlert message={error} />}

            {mode === "setup" && (
              <div>
                <label className="mb-1 block text-sm text-zinc-400">Nama</label>
                <input
                  required
                  minLength={2}
                  className="input"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Nama kamu"
                  autoComplete="name"
                />
              </div>
            )}
            <div>
              <label className="mb-1 block text-sm text-zinc-400">Email</label>
              <input
                type="email"
                required
                className="input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm text-zinc-400">Password</label>
              <input
                type="password"
                required
                minLength={8}
                className="input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Minimal 8 karakter"
                autoComplete={mode === "setup" ? "new-password" : "current-password"}
              />
            </div>
            {mode === "setup" && (
              <div>
                <label className="mb-1 block text-sm text-zinc-400">Konfirmasi password</label>
                <input
                  type="password"
                  required
                  minLength={8}
                  className="input"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  placeholder="Ulangi password"
                  autoComplete="new-password"
                />
              </div>
            )}
            <Button type="submit" loading={loading} className="w-full">
              {mode === "setup" ? "Buat akun admin" : "Login"}
            </Button>
            {mode === "login" && (
              <>
                <p className="text-center text-xs text-zinc-600">
                  Lupa password? Hubungi admin aplikasi - tidak ada pendaftaran akun baru.
                </p>
                <div className="border-t border-zinc-800 pt-3 text-center">
                  <a
                    href="http://localhost:5000/api/auth/google"
                    className="text-xs font-medium text-brand-400 underline underline-offset-2 hover:text-brand-300"
                  >
                    Hubungkan channel YouTube langsung (tanpa login)
                  </a>
                </div>
              </>
            )}
          </form>
        )}
      </div>
    </div>
  );
}
