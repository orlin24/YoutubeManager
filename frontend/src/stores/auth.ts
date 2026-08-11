import { create } from "zustand";
import { fetchMe, login as apiLogin, logout as apiLogout, setupAccount } from "../services/api";
import type { User } from "../types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  setup: (name: string, email: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  fetchMe: () => Promise<void>;
  ensureLoaded: () => Promise<void>;
}

let loaded = false;

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  loading: false,

  login: async (email, password) => {
    const resp = await apiLogin(email, password);
    set({ user: resp.user });
    loaded = true;
    return resp.user;
  },

  setup: async (name, email, password) => {
    const resp = await setupAccount(name, email, password);
    set({ user: resp.user });
    loaded = true;
    return resp.user;
  },

  logout: async () => {
    try {
      await apiLogout();
    } catch {
      // ignore network errors on logout
    }
    loaded = true;
    set({ user: null });
  },

  fetchMe: async () => {
    try {
      const resp = await fetchMe();
      set({ user: resp.user });
    } catch {
      set({ user: null });
    } finally {
      loaded = true;
    }
  },

  ensureLoaded: async () => {
    if (!loaded && !get().user) {
      await get().fetchMe();
    } else {
      loaded = true;
    }
  },
}));
