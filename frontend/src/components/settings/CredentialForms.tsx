import { FormEvent, useEffect, useState } from "react";
import { Eye, EyeOff, KeyRound, Save, Youtube } from "lucide-react";
import {
  fetchCredentialsStatus,
  saveAiCredentials,
  saveGoogleCredentials,
  type CredentialsStatus,
} from "../../services/api";
import { ApiError } from "../../services/api";
import { Badge } from "../common/Badge";
import { Button } from "../common/Button";
import { ErrorAlert } from "../common/ErrorAlert";

function SourceBadge({ source }: { source: CredentialsStatus["google"]["source"] }) {
  if (source === "web") return <Badge tone="green">tersimpan di web</Badge>;
  if (source === "env") return <Badge tone="blue">dari .env</Badge>;
  return <Badge tone="amber">belum diatur</Badge>;
}

function SecretInput({
  value,
  onChange,
  placeholder,
  autoComplete,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  autoComplete?: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <input
        type={show ? "text" : "password"}
        className="input pr-10"
        value={value}
        placeholder={placeholder}
        autoComplete={autoComplete}
        onChange={(e) => onChange(e.target.value)}
      />
      <button
        type="button"
        onClick={() => setShow(!show)}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300"
        aria-label={show ? "Sembunyikan" : "Tampilkan"}
      >
        {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  );
}

export function GoogleCredentialForm({ onSaved }: { onSaved?: () => void }) {
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [status, setStatus] = useState<CredentialsStatus["google"] | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    fetchCredentialsStatus()
      .then((s) => setStatus(s.google))
      .catch(() => undefined);
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const resp = await saveGoogleCredentials(clientId.trim(), clientSecret.trim());
      setSuccess(resp.message);
      setClientId("");
      setClientSecret("");
      const s = await fetchCredentialsStatus();
      setStatus(s.google);
      onSaved?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Gagal menyimpan kredensial.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Youtube className="h-4 w-4 text-red-400" />
        <span className="text-sm font-medium text-zinc-200">Google OAuth (YouTube)</span>
        {status && <SourceBadge source={status.source} />}
      </div>
      {error && <ErrorAlert message={error} />}
      {success && (
        <div className="rounded-lg border border-emerald-800/60 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-300">
          {success}
        </div>
      )}
      <div>
        <label className="mb-1 block text-sm text-zinc-400">Client ID</label>
        <input
          className="input"
          value={clientId}
          placeholder="xxxxx.apps.googleusercontent.com"
          autoComplete="off"
          onChange={(e) => setClientId(e.target.value)}
        />
      </div>
      <div>
        <label className="mb-1 block text-sm text-zinc-400">Client Secret</label>
        <SecretInput
          value={clientSecret}
          placeholder="GOCSPX-..."
          autoComplete="off"
          onChange={setClientSecret}
        />
      </div>
      <Button type="submit" loading={saving} disabled={clientId.trim().length < 10 || clientSecret.trim().length < 10}>
        <Save className="h-4 w-4" /> Simpan kredensial Google
      </Button>
      <p className="text-xs text-zinc-500">
        Disimpan aman di database, langsung diterapkan tanpa restart. Secret tidak pernah
        ditampilkan kembali.
      </p>
    </form>
  );
}

export function AiCredentialForm({ onSaved }: { onSaved?: () => void }) {
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("gpt-4o-mini");
  const [baseUrl, setBaseUrl] = useState("https://api.openai.com/v1");
  const [status, setStatus] = useState<CredentialsStatus["ai"] | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    fetchCredentialsStatus()
      .then((s) => setStatus(s.ai))
      .catch(() => undefined);
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const resp = await saveAiCredentials({
        api_key: apiKey.trim(),
        model: model.trim() || undefined,
        base_url: baseUrl.trim() || undefined,
      });
      setSuccess(resp.message);
      setApiKey("");
      const s = await fetchCredentialsStatus();
      setStatus(s.ai);
      onSaved?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Gagal menyimpan kredensial AI.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <KeyRound className="h-4 w-4 text-brand-400" />
        <span className="text-sm font-medium text-zinc-200">AI provider</span>
        {status && <SourceBadge source={status.source} />}
      </div>
      {error && <ErrorAlert message={error} />}
      {success && (
        <div className="rounded-lg border border-emerald-800/60 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-300">
          {success}
        </div>
      )}
      <div>
        <label className="mb-1 block text-sm text-zinc-400">API Key</label>
        <SecretInput
          value={apiKey}
          placeholder="sk-..."
          autoComplete="off"
          onChange={setApiKey}
        />
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <div>
          <label className="mb-1 block text-sm text-zinc-400">Model</label>
          <input className="input" value={model} placeholder="gpt-4o-mini" onChange={(e) => setModel(e.target.value)} />
        </div>
        <div>
          <label className="mb-1 block text-sm text-zinc-400">Base URL</label>
          <input
            className="input"
            value={baseUrl}
            placeholder="https://api.openai.com/v1"
            onChange={(e) => setBaseUrl(e.target.value)}
          />
        </div>
      </div>
      <Button type="submit" loading={saving} disabled={apiKey.trim().length < 5}>
        <Save className="h-4 w-4" /> Simpan kredensial AI
      </Button>
      <p className="text-xs text-zinc-500">
        OpenAI, Groq, atau model lokal (Ollama): cukup ganti Base URL. Disimpan aman dan
        diterapkan langsung.
      </p>
    </form>
  );
}
