import { create } from "zustand";
import { fetchChannels } from "../services/api";
import type { Channel } from "../types";

const STORAGE_KEY = "aym_selected_channel";

function persistedSelection(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

interface ChannelState {
  channels: Channel[];
  selectedChannelId: string | null;
  setChannels: (channels: Channel[]) => void;
  selectChannel: (id: string | null) => void;
  refreshChannels: () => Promise<Channel[]>;
}

export const useChannelStore = create<ChannelState>((set, get) => ({
  channels: [],
  selectedChannelId: persistedSelection(),

  setChannels: (channels) => {
    const current = get().selectedChannelId;
    const stillValid = current && channels.some((c) => c.id === current);
    const next = stillValid ? current : channels[0]?.id ?? null;
    set({ channels, selectedChannelId: next });
    try {
      if (next) localStorage.setItem(STORAGE_KEY, next);
      else localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore storage errors
    }
  },

  selectChannel: (id) => {
    set({ selectedChannelId: id });
    try {
      if (id) localStorage.setItem(STORAGE_KEY, id);
      else localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
  },

  refreshChannels: async () => {
    const resp = await fetchChannels();
    get().setChannels(resp.items);
    return resp.items;
  },
}));
