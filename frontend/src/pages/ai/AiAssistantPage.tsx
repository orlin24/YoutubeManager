import { FormEvent, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Bot, Play, Send, User as UserIcon } from "lucide-react";
import { ApiError, executeAiAction, sendAiChat } from "../../services/api";
import type { AiAction } from "../../types";
import { useChannelStore } from "../../stores/channel";
import { EmptyState } from "../../components/common/EmptyState";
import { ErrorAlert } from "../../components/common/ErrorAlert";
import { Spinner } from "../../components/common/Button";

const QUICK_COMMANDS = [
  "Analisis channel saya hari ini",
  "Video mana yang paling bagus minggu ini?",
  "Buatkan 10 ide video",
  "Buat content plan 30 hari",
  "Optimalkan video yang CTR-nya rendah",
  "Buatkan 5 judul untuk video ini",
  "Upload video ini sebagai private",
  "Jadwalkan video ini besok jam 19:00",
  "Balas komentar yang positif",
  "Berikan laporan channel hari ini",
];

interface Message {
  role: "user" | "ai";
  text: string;
  actions?: AiAction[];
  error?: boolean;
}

export default function AiAssistantPage() {
  const selectedChannelId = useChannelStore((s) => s.selectedChannelId);
  const channels = useChannelStore((s) => s.channels);
  const [searchParams] = useSearchParams();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const thinkingRef = useRef(false);
  const [runningAction, setRunningAction] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  const onRunAction = async (msgIndex: number, a: AiAction) => {
    if (!selectedChannelId) return;
    setRunningAction(a.id);
    setActionMsg(null);
    try {
      const resp = await executeAiAction(selectedChannelId, a.id, a.payload);
      setActionMsg(
        resp.approved
          ? `Aksi "${a.label}" berhasil dijalankan.`
          : resp.message ?? `Aksi "${a.label}" menunggu persetujuan Anda di halaman Approvals.`
      );
      setMessages((prev) => {
        const next = [...prev];
        const m = next[msgIndex];
        if (m) m.actions = (m.actions ?? []).filter((x) => x.id !== a.id);
        return next;
      });
    } catch (e) {
      setActionMsg(e instanceof ApiError ? e.message : "Gagal menjalankan aksi.");
    } finally {
      setRunningAction(null);
    }
  };
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const prompt = searchParams.get("prompt");
    if (prompt) {
      setMessages([{ role: "user", text: prompt }]);
      send(prompt);
      searchParams.delete("prompt");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, thinking]);

  const send = async (text: string) => {
    if (!selectedChannelId || thinkingRef.current) return;
    thinkingRef.current = true;
    setThinking(true);
    setError(null);
    try {
      const resp = await sendAiChat(selectedChannelId, text);
      setMessages((prev) => [...prev, { role: "ai", text: resp.reply, actions: resp.actions }]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        {
          role: "ai",
          text: e instanceof ApiError ? e.message : "The AI is not reachable.",
          error: true,
        },
      ]);
    } finally {
      thinkingRef.current = false;
      setThinking(false);
    }
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || thinking) return;
    setMessages((prev) => [...prev, { role: "user", text }]);
    setInput("");
    send(text);
  };

  if (channels.length === 0) {
    return (
      <EmptyState
        title="Connect a channel first"
        description="The AI works on your connected YouTube channel."
        action={
          <a href="http://localhost:5000/api/auth/google" className="btn-primary">
            Connect YouTube
          </a>
        }
      />
    );
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-8rem)] max-w-3xl flex-col">
      <div className="mb-4">
        <h1 className="text-xl font-bold text-zinc-100">AI Assistant</h1>
        <p className="text-sm text-zinc-500">
          AI karyawan Anda: menganalisis channel, membuat content plan, menulis judul dan
          deskripsi, serta merekomendasikan tindakan - semua aksi dijalankan dari halaman Videos.
        </p>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
        {messages.length === 0 && !thinking && (
          <div>
            <p className="mb-3 text-center text-sm text-zinc-500">Quick commands</p>
            <div className="flex flex-wrap justify-center gap-2">
              {QUICK_COMMANDS.map((cmd) => (
                <button
                  key={cmd}
                  disabled={thinking}
                  onClick={() => {
                    if (thinkingRef.current) return;
                    setMessages((prev) => [...prev, { role: "user", text: cmd }]);
                    send(cmd);
                  }}
                  className="rounded-full border border-zinc-800 bg-zinc-900 px-3 py-1.5 text-xs text-zinc-300 transition-colors hover:border-brand-600 hover:text-brand-300 disabled:opacity-50"
                >
                  {cmd}
                </button>
              ))}
            </div>
          </div>
        )}

        {error && <ErrorAlert message={error} />}

        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="flex max-w-[85%] items-start gap-2">
                <div className="rounded-2xl rounded-tr-sm bg-brand-600 px-4 py-2.5 text-sm text-white">
                  {m.text}
                </div>
                <div className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-zinc-700 text-zinc-300">
                  <UserIcon className="h-3.5 w-3.5" />
                </div>
              </div>
            </div>
          ) : (
            <div key={i} className="flex justify-start">
              <div className="max-w-[85%] space-y-2">
                <div className="flex items-start gap-2">
                  <div className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-600 text-brand-950">
                    <Bot className="h-3.5 w-3.5" />
                  </div>
                  <div
                    className={`rounded-2xl rounded-tl-sm px-4 py-2.5 text-sm whitespace-pre-wrap ${
                      m.error ? "bg-red-950/60 text-red-300" : "bg-zinc-800 text-zinc-100"
                    }`}
                  >
                    {m.text}
                  </div>
                  {m.actions && m.actions.length > 0 && (
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      <span className="text-[11px] font-medium text-zinc-500">Aksi AI:</span>
                      {m.actions.map((a) => (
                        <button
                          key={a.id}
                          onClick={() => onRunAction(i, a)}
                          className="inline-flex items-center gap-1 rounded-full border border-zinc-700 bg-zinc-900 px-2.5 py-1 text-xs text-zinc-200 transition hover:border-emerald-600 hover:text-emerald-300"
                        >
                          <Play className="h-3 w-3" />
                          {a.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )
        )}
        {actionMsg && (
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/70 px-4 py-2 text-xs text-zinc-300">
            {actionMsg}
          </div>
        )}
        {thinking && (
          <div className="flex items-center gap-2 text-sm text-zinc-500">
            <Spinner className="h-4 w-4 text-brand-400" /> AI is working on it...
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={onSubmit} className="mt-3 flex items-center gap-2">
        <input
          className="input"
          placeholder="Ask your AI employee anything about your channel..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={thinking}
        />
        <button
          type="submit"
          disabled={thinking || !input.trim()}
          className="btn-primary h-10 w-12 shrink-0 disabled:opacity-50"
          aria-label="Send"
        >
          <Send className="h-4 w-4" />
        </button>
      </form>
    </div>
  );
}
