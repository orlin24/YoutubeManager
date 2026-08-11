import { ReactNode, useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  BookOpen,
  Bot,
  Check,
  CheckCircle2,
  ClipboardCopy,
  ExternalLink,
  KeyRound,
  RefreshCw,
  Rocket,
  Youtube,
} from "lucide-react";
import { fetchHealth } from "../../services/api";
import { Button } from "../../components/common/Button";
import { Card } from "../../components/common/Card";
import { Badge } from "../../components/common/Badge";
import { AiCredentialForm, GoogleCredentialForm } from "../../components/settings/CredentialForms";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function CopyBlock({ text, label }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard blocked; ignore
    }
  };
  return (
    <div className="relative">
      {label && <p className="mb-1 text-xs text-zinc-500">{label}</p>}
      <pre className="overflow-x-auto rounded-lg border border-zinc-800 bg-zinc-950 p-3 pr-16 text-xs text-zinc-300">
        {text}
      </pre>
      <button
        onClick={copy}
        className="absolute right-2 top-6 flex items-center gap-1 rounded-md bg-zinc-800 px-2 py-1 text-[11px] text-zinc-300 hover:bg-zinc-700"
      >
        {copied ? <Check className="h-3 w-3 text-emerald-400" /> : <ClipboardCopy className="h-3 w-3" />}
        {copied ? "Tersalin" : "Salin"}
      </button>
    </div>
  );
}

function Callout({
  tone,
  title,
  children,
}: {
  tone: "info" | "warn" | "success";
  title: string;
  children: ReactNode;
}) {
  const styles = {
    info: "border-sky-800/60 bg-sky-950/40 text-sky-200",
    warn: "border-amber-800/60 bg-amber-950/40 text-amber-200",
    success: "border-emerald-800/60 bg-emerald-950/40 text-emerald-200",
  }[tone];
  return (
    <div className={`rounded-lg border px-4 py-3 text-sm ${styles}`}>
      <p className="font-semibold">{title}</p>
      <div className="mt-1 text-xs opacity-90">{children}</div>
    </div>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <div className="flex gap-4">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-600 text-sm font-bold text-white">
        {n}
      </div>
      <div className="min-w-0 flex-1 space-y-3 pb-2">
        <h3 className="pt-1 text-base font-semibold text-zinc-100">{title}</h3>
        {children}
      </div>
    </div>
  );
}

function LinkBtn({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="btn-secondary inline-flex h-8 text-xs">
      <ExternalLink className="h-3.5 w-3.5" /> {children}
    </a>
  );
}

// ---------------------------------------------------------------------------
// Status chips (live from backend)
// ---------------------------------------------------------------------------

function StatusRow({ label, ok }: { label: string; ok: boolean | null }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-2.5">
      <span className="text-sm text-zinc-300">{label}</span>
      {ok === null ? (
        <span className="flex items-center gap-1.5 text-xs text-zinc-500">
          <span className="h-2 w-2 animate-pulse rounded-full bg-zinc-600" /> memeriksa...
        </span>
      ) : ok ? (
        <span className="flex items-center gap-1.5 text-xs text-emerald-400">
          <CheckCircle2 className="h-3.5 w-3.5" /> Sudah dikonfigurasi
        </span>
      ) : (
        <span className="flex items-center gap-1.5 text-xs text-amber-400">
          <AlertTriangle className="h-3.5 w-3.5" /> Belum / sebagian
        </span>
      )}
    </div>
  );
}

export default function TutorialPage() {
  const [status, setStatus] = useState<{
    youtube: boolean | null;
    ai: boolean | null;
    database: boolean | null;
  }>({ youtube: null, ai: null, database: null });

  const check = useCallback(async () => {
    try {
      const h = await fetchHealth();
      setStatus({
        youtube: h.checks.youtube_api === "configured",
        ai: h.checks.ai_provider === "configured",
        database: h.checks.database === "ok",
      });
    } catch {
      setStatus({ youtube: null, ai: null, database: null });
    }
  }, []);

  useEffect(() => {
    check();
  }, [check]);

  const origin = typeof window !== "undefined" ? window.location.origin : "http://localhost:5000";
  const redirectUri = `${origin}/api/auth/google/callback`;

  const envGoogle = `# backend/.env
GOOGLE_CLIENT_ID=${"xxxxx.apps.googleusercontent.com"}
GOOGLE_CLIENT_SECRET=${"GOCSPX-xxxxxxxxxxxxxxxx"}
GOOGLE_REDIRECT_URI=${redirectUri}
FRONTEND_URL=${origin}`;

  const envAi = `# backend/.env
AI_API_KEY=${"sk-xxxxxxxxxxxxxxxx"}
AI_MODEL=${"gpt-4o-mini"}
AI_BASE_URL=${"https://api.openai.com/v1"}`;

  const steps: Array<{ title: string; href: string; desc: string }> = [
    { title: "Buat Project di Google Cloud", href: "https://console.cloud.google.com", desc: "console.cloud.google.com" },
    { title: "Aktifkan YouTube API", href: "https://console.cloud.google.com/apis/library/youtube.googleapis.com", desc: "APIs & Services > Library" },
    { title: "OAuth consent screen", href: "https://console.cloud.google.com/apis/credentials/consent", desc: "APIs & Services > OAuth consent screen" },
    { title: "Buat OAuth Client ID", href: "https://console.cloud.google.com/apis/credentials", desc: "APIs & Services > Credentials" },
    { title: "Salin ke backend/.env", href: "", desc: "Client ID + Client Secret" },
    { title: "Restart & connect", href: "", desc: "systemctl restart ai-youtube-manager" },
  ];

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-zinc-100">
            <BookOpen className="h-5 w-5 text-brand-400" /> Tutorial Lengkap untuk Pemula
          </h1>
          <p className="mt-1 text-sm text-zinc-500">
            Cara menghubungkan channel YouTube dan mengaktifkan AI - langkah demi langkah, tanpa
            perlu pengalaman teknis.
          </p>
        </div>
        <Button variant="secondary" className="h-9 text-xs" onClick={check}>
          <RefreshCw className="h-3.5 w-3.5" /> Periksa status
        </Button>
      </div>

      {/* Status dashboard */}
      <Card
        title="Status konfigurasi kamu"
        subtitle="Diperiksa langsung dari server"
        actions={<Badge tone={status.youtube && status.ai ? "green" : "amber"}>lengkap / sebagian</Badge>}
      >
        <div className="space-y-2">
          <StatusRow label="1. Database (PostgreSQL)" ok={status.database} />
          <StatusRow label="2. Google OAuth (YouTube)" ok={status.youtube} />
          <StatusRow label="3. AI provider (opsional)" ok={status.ai} />
        </div>
        {!status.youtube && (
          <p className="mt-3 text-xs text-zinc-500">
            Belum ada kredensial Google? Ikuti langkah 1-6 di bawah - butuh sekitar 10 menit.
          </p>
        )}
      </Card>

      {/* Daftar isi */}
      <Card title="Yang akan kamu lakukan" subtitle="Klik untuk lompat ke langkah">
        <ol className="grid gap-2 md:grid-cols-2">
          {steps.map((s, i) => (
            <li key={s.title} className="flex items-center gap-2 text-sm">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-zinc-800 text-[10px] font-bold text-zinc-300">
                {i + 1}
              </span>
              {s.href ? (
                <a href={s.href} target="_blank" rel="noreferrer" className="text-brand-300 hover:underline">
                  {s.title}
                </a>
              ) : (
                <span className="text-zinc-300">{s.title}</span>
              )}
              <span className="text-xs text-zinc-600">{s.desc}</span>
            </li>
          ))}
        </ol>
      </Card>

      {/* Bagian 1: Google Cloud */}
      <Card
        id="google"
        title="Bagian 1 - Hubungkan YouTube (Google Cloud)"
        subtitle="Sekali setup, dipakai selamanya. Yang kamu butuhkan: akun Google biasa + channel YouTube."
        actions={<Youtube className="h-5 w-5 text-red-400" />}
      >
        <div className="space-y-6">
          <Callout tone="info" title="Apa itu Client ID & Client Secret?">
            Ini seperti "kunci rumah" dan "kunci cadangan" aplikasi kamu di Google. Google
            memberikannya agar aplikasi ini bisa membaca analytics channel kamu - dan hanya
            channel yang kamu pilih sendiri.
          </Callout>

          <Step n={1} title="Buat Project di Google Cloud Console">
            <ol className="list-decimal space-y-1.5 pl-5 text-sm text-zinc-400">
              <li>Buka <LinkBtn href="https://console.cloud.google.com">console.cloud.google.com</LinkBtn> dan login dengan akun Google kamu.</li>
              <li>Klik dropdown nama project di <b className="text-zinc-200">kiri atas</b> (dekat logo Google Cloud).</li>
              <li>Klik <b className="text-zinc-200">New Project</b> (Buat project baru).</li>
              <li>Isi nama, misal <code className="rounded bg-zinc-800 px-1">ai-youtube-manager</code>, klik <b className="text-zinc-200">Create</b>.</li>
              <li>Pastikan project baru terpilih di dropdown.</li>
            </ol>
          </Step>

          <Step n={2} title="Aktifkan YouTube Data API v3 + YouTube Analytics API">
            <ol className="list-decimal space-y-1.5 pl-5 text-sm text-zinc-400">
              <li>Buka menu <b className="text-zinc-200">APIs &amp; Services &gt; Library</b>.</li>
              <li>Cari <b className="text-zinc-200">YouTube Data API v3</b>, klik, lalu klik tombol <b className="text-zinc-200">Enable</b>.</li>
              <li>Ulangi untuk <b className="text-zinc-200">YouTube Analytics API</b>.</li>
            </ol>
            <Callout tone="info" title="Kenapa dua-duanya?">
              Data API v3 untuk daftar video, statistik channel, upload, komentar. Analytics API
              untuk grafik performa (views per hari, watch time, estimasi pendapatan).
            </Callout>
          </Step>

          <Step n={3} title="Atur OAuth consent screen (layar izin)">
            <ol className="list-decimal space-y-1.5 pl-5 text-sm text-zinc-400">
              <li>Buka <b className="text-zinc-200">APIs &amp; Services &gt; OAuth consent screen</b>.</li>
              <li>User Type pilih <b className="text-zinc-200">External</b> &gt; Create.</li>
              <li>Isi <b className="text-zinc-200">App name</b> (misal "AI YouTube Manager"), <b className="text-zinc-200">User support email</b>, dan <b className="text-zinc-200">Developer contact email</b> &gt; Save and Continue.</li>
              <li>Halaman Scopes: klik <b className="text-zinc-200">Add or remove scopes</b>, pastikan tercentang <code className="rounded bg-zinc-800 px-1">youtube.readonly</code>, <code className="rounded bg-zinc-800 px-1">youtube.upload</code>, <code className="rounded bg-zinc-800 px-1">yt-analytics.readonly</code>, dan <code className="rounded bg-zinc-800 px-1">email</code> &gt; Save and Continue.</li>
              <li>Halaman <b className="text-zinc-200">Test users</b>: tambahkan <b className="text-zinc-200">email Google kamu sendiri</b> (yang punya channel) &gt; Save and Continue &gt; Back to dashboard.</li>
            </ol>
            <Callout tone="warn" title="Penting: status Testing">
              Selama status "Testing", hanya email yang kamu daftarkan sebagai test user yang bisa
              menghubungkan channel. Untuk dipakai orang lain / produksi, klik <b>Publish app</b> dan
              ikuti proses verifikasi Google (butuh waktu).
            </Callout>
          </Step>

          <Step n={4} title="Buat OAuth Client ID (Web application)">
            <ol className="list-decimal space-y-1.5 pl-5 text-sm text-zinc-400">
              <li>Buka <b className="text-zinc-200">APIs &amp; Services &gt; Credentials</b>.</li>
              <li>Klik <b className="text-zinc-200">+ Create Credentials &gt; OAuth client ID</b>.</li>
              <li>Application type: <b className="text-zinc-200">Web application</b>.</li>
              <li>Di <b className="text-zinc-200">Authorized redirect URIs</b> klik <b className="text-zinc-200">+ Add URI</b>, lalu tempel persis baris ini:</li>
            </ol>
            <CopyBlock text={redirectUri} label="Redirect URI (salin persis, tanpa spasi)" />
            <Callout tone="warn" title="Penyebab paling umum gagal: redirect URI beda satu huruf saja">
              Google mencocokkan URI ini <b>karakter per karakter</b> dengan yang ada di
              <code className="rounded bg-zinc-800 px-1"> backend/.env </code>. Pastikan persis sama:
              protocol (<code>http</code>/<code>https</code>), host, dan path
              <code className="rounded bg-zinc-800 px-1"> /api/auth/google/callback</code>.
            </Callout>
            <ol className="list-decimal space-y-1.5 pl-5 text-sm text-zinc-400" start={5}>
              <li>Klik <b className="text-zinc-200">Create</b>.</li>
              <li>Akan muncul popup berisi <b className="text-zinc-200">Client ID</b> dan <b className="text-zinc-200">Client Secret</b>. Klik <b className="text-zinc-200">Download JSON</b> atau salin keduanya - lanjut ke langkah 5.</li>
            </ol>
          </Step>

          <Step n={5} title="Masukkan kredensial langsung di sini (tanpa edit file)">
            <p className="text-sm text-zinc-400">
              Setelah mendapat Client ID dan Client Secret dari Google, cukup tempel di form
              bawah ini lalu klik Simpan. <b className="text-zinc-200">Backend otomatis menyimpan
              dan menerapkannya</b> - tidak perlu menyentuh file .env sama sekali.
            </p>
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/70 p-4">
              <GoogleCredentialForm onSaved={check} />
            </div>
            <details className="group rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
              <summary className="cursor-pointer text-xs text-zinc-500 hover:text-zinc-300">
                Pengguna tingkat lanjut: atur lewat backend/.env (alternatif)
              </summary>
              <div className="mt-3">
                <CopyBlock text={envGoogle} label="Isi dengan Client ID & Client Secret kamu" />
                <p className="mt-2 text-xs text-zinc-500">
                  Nilai dari form web di atas menang jika keduanya terisi. Jangan bagikan Client
                  Secret ke siapa pun dan jangan commit file .env ke git.
                </p>
              </div>
            </details>
          </Step>

          <Step n={6} title="Hubungkan channel YouTube">
            <p className="text-sm text-zinc-400">
              Kredensial yang disimpan lewat form tadi sudah langsung aktif -{" "}
              <b className="text-zinc-200">tanpa perlu restart</b>. Sekarang klik tombol di bawah
              untuk memilih akun Google kamu dan setujui izinnya:
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <a href="/api/auth/google" className="btn-primary h-9 text-xs">Connect YouTube</a>
              <a href="/channels" className="btn-ghost h-9 text-xs">Buka halaman Channels</a>
            </div>
            <p className="text-sm text-zinc-400">
              Setelah diarahkan kembali, channel akan muncul di halaman{" "}
              <a href="/channels" className="text-brand-300 hover:underline">Channels</a>. Klik{" "}
              <b>Sync</b> untuk menarik data.
            </p>
            <Callout tone="success" title="Berhasil?">
              Status "Google OAuth (YouTube)" di atas akan berubah menjadi <b>Sudah dikonfigurasi</b>.
              Dashboard, Videos, dan Analytics mulai terisi setelah Sync / sinkronisasi otomatis.
            </Callout>
          </Step>
        </div>
      </Card>

      {/* Bagian 2: AI */}
      <Card
        id="ai"
        title="Bagian 2 - Aktifkan AI (opsional tapi sangat disarankan)"
        subtitle="Tanpa AI, aplikasi tetap jalan dengan analisis heuristik. Dengan AI, kamu dapat analisis mendalam, content plan 30 hari, judul & deskripsi otomatis."
        actions={<Bot className="h-5 w-5 text-brand-400" />}
      >
        <div className="space-y-6">
          <Step n={1} title="Pilih penyedia AI (pilih salah satu)">
            <div className="space-y-2">
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3 text-sm">
                <p className="font-medium text-zinc-200">Opsi A - OpenAI (paling umum)</p>
                <p className="mt-1 text-xs text-zinc-400">
                  Daftar di <LinkBtn href="https://platform.openai.com">platform.openai.com</LinkBtn>,
                  buka <b>API keys</b>, klik <b>Create new secret key</b>, salin kunci
                  <code className="rounded bg-zinc-800 px-1"> sk-...</code>. (Perlu saldo/payment method.)
                </p>
              </div>
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3 text-sm">
                <p className="font-medium text-zinc-200">Opsi B - Groq (gratis, cepat)</p>
                <p className="mt-1 text-xs text-zinc-400">
                  Daftar di <LinkBtn href="https://console.groq.com">console.groq.com</LinkBtn> (gratis),
                  buka <b>API Keys</b> &gt; <b>Create API Key</b>. Model gratis:{" "}
                  <code className="rounded bg-zinc-800 px-1">llama-3.3-70b-versatile</code>, base URL tetap
                  <code className="rounded bg-zinc-800 px-1"> https://api.groq.com/openai/v1</code>.
                </p>
              </div>
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3 text-sm">
                <p className="font-medium text-zinc-200">Opsi C - Model lokal (Ollama, 100% gratis & privat)</p>
                <p className="mt-1 text-xs text-zinc-400">
                  Install <LinkBtn href="https://ollama.com">Ollama</LinkBtn>, jalankan{" "}
                  <code className="rounded bg-zinc-800 px-1">ollama pull llama3.1</code>, lalu isi
                  AI_BASE_URL dengan <code className="rounded bg-zinc-800 px-1">http://localhost:11434/v1</code>.
                </p>
              </div>
            </div>
          </Step>

          <Step n={2} title="Masukkan API Key langsung di sini (tanpa edit file)">
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/70 p-4">
              <AiCredentialForm onSaved={check} />
            </div>
            <details className="group rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
              <summary className="cursor-pointer text-xs text-zinc-500 hover:text-zinc-300">
                Pengguna tingkat lanjut: atur lewat backend/.env (alternatif)
              </summary>
              <div className="mt-3">
                <CopyBlock text={envAi} label="Isi dengan kunci API kamu" />
              </div>
            </details>
          </Step>

          <Step n={3} title="Coba fitur AI">
            <p className="text-sm text-zinc-400">
              Buka <a href="/ai" className="text-brand-300 hover:underline">AI Assistant</a> dan ketik
              misalnya <i>"Analisis channel saya hari ini"</i> atau <i>"Buat content plan 30 hari"</i>.
              Upload, publish, dan delete dilakukan langsung dari halaman Videos.
            </p>
          </Step>
        </div>
      </Card>

      {/* Alternative: publish / desktop client */}
      <Card
        id="alternatif"
        title="Cara alternatif: Publish app + Client tipe Desktop (seperti LoopBot)"
        subtitle="Cara ini menghilangkan batasan 'hanya test user' - cocok kalau ingin dipakai banyak akun / orang lain"
      >
        <div className="space-y-3 text-sm">
          <Callout tone="info" title="Kenapa LoopBot bisa tanpa ribet?">
            LoopBot (dan aplikasi YouTube sejenis) adalah aplikasi <b>desktop</b> yang OAuth
            client-nya sudah <b>di-Publish (Production)</b>. Status Testing hanya mengizinkan
            maksimal 100 test user dan token kadaluarsa 7 hari; status Published menghapus
            keduanya. Aplikasi ini mendukung dua-duanya - kamu cukup membuat client tipe
            <b> Desktop app </b> lalu tempel Client ID/Secret-nya di form di atas.
          </Callout>
          <Step n={1} title="Publish aplikasi di Google Console">
            <ol className="list-decimal space-y-1.5 pl-5 text-zinc-400">
              <li>Buka <b className="text-zinc-200">OAuth consent screen</b> (sebagai developer).</li>
              <li>Klik <b className="text-zinc-200">Publish app</b> &gt; konfirmasi.</li>
              <li>
                Catatan: untuk scope YouTube (restricted), Google akan menampilkan peringatan
                "app tidak diverifikasi" - pada client tipe Desktop, peringatan ini bisa dilewati
                lewat <b className="text-zinc-200">Advanced &gt; Go to app (unsafe)</b>.
              </li>
            </ol>
          </Step>
          <Step n={2} title="Buat OAuth client tipe Desktop">
            <ol className="list-decimal space-y-1.5 pl-5 text-zinc-400">
              <li>Buka <b className="text-zinc-200">APIs &amp; Services &gt; Credentials</b>.</li>
              <li>Klik <b className="text-zinc-200">+ Create Credentials &gt; OAuth client ID</b>.</li>
              <li>Application type pilih <b className="text-zinc-200">Desktop app</b>.</li>
              <li>Beri nama (misal "AYM Desktop"), klik <b className="text-zinc-200">Create</b>.</li>
              <li>Salin <b className="text-zinc-200">Client ID</b> dan <b className="text-zinc-200">Client Secret</b> baru.</li>
            </ol>
          </Step>
          <Step n={3} title="Tempel di aplikasi dan hubungkan">
            <p className="text-zinc-400">
              Masukkan Client ID/Secret Desktop tadi ke form "Simpan kredensial Google" di langkah
              5 di atas, lalu klik <b>Connect YouTube</b>. Redirect URI tetap
              <code className="mx-1 rounded bg-zinc-800 px-1">http://localhost:5000/api/auth/google/callback</code>{" "}
              - client tipe Desktop mengizinkan redirect ke localhost tanpa perlu mendaftarkan URI.
            </p>
          </Step>
          <Callout tone="warn" title="Jangan publish kalau hanya dipakai sendiri">
            Mode Testing + test user cukup untuk pemakaian pribadi (maks 100 akun, token 7 hari).
            Publish diperlukan hanya jika banyak akun/orang lain yang akan menghubungkan channel.
          </Callout>
        </div>
      </Card>

      {/* Troubleshooting */}
      <Card title="Pemecahan masalah umum" subtitle="Error yang paling sering ditemui pemula">
        <div className="space-y-2 text-sm">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3">
            <p className="font-medium text-red-300">redirect_uri_mismatch</p>
            <p className="mt-1 text-xs text-zinc-400">
              Redirect URI di Google Console tidak persis sama dengan GOOGLE_REDIRECT_URI di .env.
              Bandingkan karakter per karakter (termasuk port dan path /api/auth/google/callback).
            </p>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3">
            <p className="font-medium text-red-300">access_denied / akun tidak muncul saat login Google</p>
            <p className="mt-1 text-xs text-zinc-400">
              Email kamu belum didaftarkan sebagai <b>Test user</b> di OAuth consent screen (langkah 3), atau
              status aplikasi masih "Testing". Tambahkan email kamu di menu Test users.
            </p>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3">
            <p className="font-medium text-amber-300">YouTube authorization has expired</p>
            <p className="mt-1 text-xs text-zinc-400">
              Token Google habis masa berlakunya (terjadi tiap 7 hari di mode Testing). Cukup buka
              Channels &gt; Connect YouTube lagi.
            </p>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3">
            <p className="font-medium text-amber-300">AI_NOT_CONFIGURED</p>
            <p className="mt-1 text-xs text-zinc-400">
              AI_API_KEY kosong atau salah. Isi di backend/.env lalu restart. Pastikan tidak ada spasi
              tersembunyi di sekitar tanda sama dengan (=).
            </p>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3">
            <p className="font-medium text-amber-300">redirect http:// di IP publik ditolak Google</p>
            <p className="mt-1 text-xs text-zinc-400">
              Google membatasi redirect <code>http://</code> untuk host non-localhost. Untuk produksi,
              gunakan domain + HTTPS (certbot) dan daftarkan URI <code>https://...</code> di Google
              Console. Untuk mencoba dari luar tanpa domain, bisa pakai tunnel seperti ngrok/cloudflared.
            </p>
          </div>
        </div>
      </Card>

      <div className="rounded-xl border border-brand-800/50 bg-brand-950/30 p-5 text-center">
        <Rocket className="mx-auto mb-2 h-6 w-6 text-brand-400" />
        <p className="text-sm text-zinc-300">
          Semua sudah dikonfigurasi?{" "}
          <a href="/channels" className="font-medium text-brand-300 hover:underline">Hubungkan channel</a>{" "}
          lalu langsung ke{" "}
          <a href="/dashboard" className="font-medium text-brand-300 hover:underline">Dashboard</a>.
        </p>
      </div>
    </div>
  );
}
