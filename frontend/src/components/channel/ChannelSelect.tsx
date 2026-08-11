import { ChevronDown } from "lucide-react";
import { useChannelStore } from "../../stores/channel";
import { Button } from "../common/Button";

export function ChannelSelect() {
  const channels = useChannelStore((s) => s.channels);
  const selectedChannelId = useChannelStore((s) => s.selectedChannelId);
  const selectChannel = useChannelStore((s) => s.selectChannel);

  if (channels.length <= 1) return null;

  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="hidden text-zinc-500 md:inline">Channel</span>
      <div className="relative">
        <select
          className="input w-56 appearance-none pr-8"
          value={selectedChannelId ?? ""}
          onChange={(e) => selectChannel(e.target.value || null)}
        >
          {channels.map((c) => (
            <option key={c.id} value={c.id}>
              {c.title}
            </option>
          ))}
        </select>
        <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
      </div>
    </label>
  );
}

export function ConnectChannelButton() {
  return (
    <a href="/api/auth/google" className="btn-primary">
      Connect YouTube
    </a>
  );
}

export { Button };
