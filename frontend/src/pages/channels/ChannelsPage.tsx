import { useCallback, useEffect, useState } from "react";
import { Activity, Brain, CheckCircle2, ChevronDown, ChevronUp, ExternalLink, Plus, RefreshCw, Trash2 } from "lucide-react";
import {
  disconnectAccount,
  fetchChannels,
  refreshChannel,
} from "../../services/api";
import { useChannelStore } from "../../stores/channel";
import type { Account, Channel } from "../../types";

const MODE_TONE: Record<string, "blue" | "green" | "violet" | "amber" | "red" | "gray"> = {
  NEW: "blue",
  GROWTH: "green",
  MONETIZED: "violet",
  SCALE: "amber",
  RECOVERY: "red",
};
import { ApiError } from "../../services/api";
import { Badge } from "../../components/common/Badge";
import { Button } from "../../components/common/Button";
import { Card } from "../../components/common/Card";
import { ConfirmDialog } from "../../components/common/ConfirmDialog";
import { EmptyState } from "../../components/common/EmptyState";
import { ErrorAlert } from "../../components/common/ErrorAlert";
import { SkeletonRow } from "../../components/common/SkeletonRow";
import { formatNumber } from "../../utils/format";
import ChannelProfileModal from "./ChannelProfileModal";
import RealtimeChart from "./RealtimeChart";
import TrafficSources from "./TrafficSources";

export default function ChannelsPage() {
  const setChannels = useChannelStore((s) => s.setChannels);
  const [channels, setLocal] = useState<Channel[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState<string | null>(null);
  const [profileFor, setProfileFor] = useState<Channel | null>(null);
  const [toDisconnect, setToDisconnect] = useState<Account | null>(null);
  const [disconnecting, setDisconnecting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [openRealtime, setOpenRealtime] = useState<string | null>(null);

  // silent=true keeps the current cards visible while refreshing in the background.
  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const resp = await fetchChannels();
      setLocal(resp.items);
      setChannels(resp.items);
      const me = await (await import("../../services/api")).fetchMe();
      setAccounts(me.accounts);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load channels.");
    } finally {
      setLoading(false);
    }
  }, [setChannels]);

  useEffect(() => {
    load();
  }, [load]);

  const onRefresh = async (id: string) => {
    if (refreshing) return; // anti double-click
    setRefreshing(id);
    try {
      const result = await refreshChannel(id);
      await load(true); // silent refresh - cards stay visible
      const title = channels.find((c) => c.id === id)?.title ?? "Channel";
      const time = new Date().toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
      setNotice(`Sync selesai: ${title} - data diperbarui pukul ${time}.`);
      setTimeout(() => setNotice(null), 5000);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Refresh failed.");
    } finally {
      setRefreshing(null);
    }
  };

  const onDisconnect = async () => {
    if (!toDisconnect) return;
    setDisconnecting(true);
    try {
      await disconnectAccount(toDisconnect.id);
      setToDisconnect(null);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Disconnect failed.");
    } finally {
      setDisconnecting(false);
    }
  };

  if (loading && channels.length === 0) return <SkeletonRow rows={4} />;
  if (error) return <ErrorAlert message={error} onRetry={() => load()} />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-zinc-100">Channels</h1>
          <p className="text-sm text-zinc-500">
            Connect your YouTube channels and manage the AI memory for each
          </p>
        </div>
        <a href="/api/auth/google" className="btn-primary">
          <Plus className="h-4 w-4" /> Connect YouTube
        </a>
      </div>

      {notice && (
        <div className="flex items-center gap-2 rounded-lg border border-emerald-800/60 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-300">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          {notice}
        </div>
      )}

      {channels.length === 0 ? (
        <EmptyState
          title="No channels connected yet"
          description="Connect a YouTube channel to let the AI analyze it and manage your content."
          action={
            <a href="/api/auth/google" className="btn-primary">
              Connect YouTube
            </a>
          }
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {channels.map((ch) => (
            <Card key={ch.id} className="flex flex-col">
              <div className="flex items-start gap-3">
                {ch.thumbnail_url ? (
                  <img src={ch.thumbnail_url} alt="" className="h-14 w-14 rounded-lg object-cover" />
                ) : (
                  <div className="h-14 w-14 rounded-lg bg-zinc-800" />
                )}
                <div className="min-w-0 flex-1">
                  <h3 className="truncate font-semibold text-zinc-100">{ch.title}</h3>
                  <p className="text-xs text-zinc-500">@{ch.channel_id}</p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {ch.lifecycle_mode && (
                      <Badge tone={MODE_TONE[ch.lifecycle_mode] ?? "gray"}>{ch.lifecycle_mode}</Badge>
                    )}
                    <Badge tone="gray">{formatNumber(ch.subscriber_count)} subs</Badge>
                    <Badge tone="gray">{formatNumber(ch.view_count)} views</Badge>
                    <Badge tone="gray">{formatNumber(ch.video_count)} videos</Badge>
                    {accounts.find((a) => a.channel_id === ch.channel_id)?.auth_error && (
                      <Badge tone="red">Perlu connect ulang</Badge>
                    )}
                  </div>
                </div>
              </div>
              <div className="mt-4 flex items-center gap-2 border-t border-zinc-800 pt-3">
                <Button
                  variant="secondary"
                  className="h-8 text-xs"
                  loading={refreshing === ch.id}
                  onClick={() => onRefresh(ch.id)}
                >
                  <RefreshCw className="h-3.5 w-3.5" /> Sync
                </Button>
                <Button variant="ghost" className="h-8 text-xs" onClick={() => setProfileFor(ch)}>
                  <Brain className="h-3.5 w-3.5" /> Memori AI
                </Button>
                <a
                  href={`https://www.youtube.com/channel/${ch.channel_id}`}
                  target="_blank"
                  rel="noreferrer"
                  className="btn-ghost h-8 text-xs"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                </a>
                <Button
                  variant="ghost"
                  className="ml-auto h-8 w-8 p-0 text-red-400 hover:text-red-300"
                  title="Disconnect"
                  onClick={() => {
                    const acc = accounts.find((a) => a.channel_id === ch.channel_id);
                    if (acc) setToDisconnect(acc);
                  }}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
              <button
                onClick={() => setOpenRealtime(openRealtime === ch.id ? null : ch.id)}
                className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-lg border border-zinc-800 bg-zinc-900/60 py-2 text-xs font-medium text-zinc-400 transition-colors hover:border-brand-600 hover:text-brand-300"
              >
                <Activity className="h-3.5 w-3.5" />
                Data Realtime
                {openRealtime === ch.id ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
              </button>
              {openRealtime === ch.id && (
                <>
                  <RealtimeChart channelId={ch.id} />
                  <TrafficSources channelId={ch.id} />
                </>
              )}
            </Card>
          ))}
        </div>
      )}

      {profileFor && (
        <ChannelProfileModal
          channelId={profileFor.id}
          channelTitle={profileFor.title}
          open
          onClose={() => setProfileFor(null)}
        />
      )}
      <ConfirmDialog
        open={!!toDisconnect}
        title="Disconnect this YouTube channel?"
        description={`The channel "${toDisconnect?.channel_title}" and its synced data will be removed. You can reconnect it later.`}
        confirmLabel="Disconnect"
        danger
        loading={disconnecting}
        onConfirm={onDisconnect}
        onCancel={() => setToDisconnect(null)}
      />
    </div>
  );
}
