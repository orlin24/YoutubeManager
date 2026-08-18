import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  BarChart3,
  Bot,
  CalendarRange,
  Clapperboard,
  LayoutDashboard,
  ListVideo,
  LogOut,
  Menu,
  MessagesSquare,
  ScrollText,
  Settings as SettingsIcon,
  Video,
  X,
  BookOpen,
  Cpu,
} from "lucide-react";
import { ChannelSelect } from "../components/channel/ChannelSelect";
import { useAuthStore } from "../stores/auth";
import { Brain, CalendarDays, Crown, Layers } from "lucide-react";
import { useChannelStore } from "../stores/channel";
import { fetchHealth } from "../services/api";
import type { HealthCheck } from "../types";
import { Button } from "../components/common/Button";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/calendar", label: "Calendar", icon: CalendarDays },
  { to: "/ai/ceo", label: "AI CEO", icon: Crown },
  { to: "/portfolio", label: "Portfolio", icon: Layers },
  { to: "/channels", label: "Channels", icon: Clapperboard },
  { to: "/videos", label: "Videos", icon: Video },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/content-plan", label: "Content Plan", icon: CalendarRange },
  { to: "/ai", label: "AI Assistant", icon: Bot },
  { to: "/ai/autonomous", label: "AI Autonom", icon: Cpu },
  { to: "/ai/learning", label: "AI Learning", icon: Brain },
  { to: "/comments", label: "Comments", icon: MessagesSquare },
  { to: "/playlists", label: "Playlists", icon: ListVideo },
  { to: "/audit", label: "Audit Logs", icon: ScrollText },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
  { to: "/tutorial", label: "Tutorial", icon: BookOpen },
];

function HealthDot({ label, status }: { label: string; status: string }) {
  const color =
    status === "ok" || status === "configured"
      ? "bg-emerald-400"
      : status === "error"
        ? "bg-red-400"
        : "bg-zinc-600";
  const text =
    status === "ok" || status === "configured"
      ? "text-emerald-400"
      : status === "error"
        ? "text-red-400"
        : "text-zinc-500";
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs ${text}`} title={`${label}: ${status}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${color}`} />
      {label}
    </span>
  );
}

export function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [health, setHealth] = useState<HealthCheck | null>(null);
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();
  const refreshChannels = useChannelStore((s) => s.refreshChannels);
  const channels = useChannelStore((s) => s.channels);

  useEffect(() => {
    refreshChannels().catch(() => undefined);
    const timer = setInterval(() => {
      fetchHealth().then(setHealth).catch(() => undefined);
    }, 30_000);
    fetchHealth().then(setHealth).catch(() => undefined);
    return () => clearInterval(timer);
  }, [refreshChannels]);

  const onLogout = async () => {
    await logout();
    navigate("/auth/login");
  };

  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 px-5 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-700 text-brand-100">
          <Bot className="h-5 w-5" />
        </div>
        <div>
          <p className="text-sm font-bold tracking-tight text-zinc-100">AI YOUTUBE MANAGER</p>
          <p className="text-[10px] uppercase tracking-widest text-zinc-500">Your AI employee</p>
        </div>
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-2">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-brand-700 text-brand-100"
                  : "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
              }`
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-zinc-800 p-4">
        <div className="mb-3 flex flex-wrap gap-2">
          <HealthDot label="Backend" status={health?.checks.backend ?? "unknown"} />
          <HealthDot label="DB" status={health?.checks.database ?? "unknown"} />
          <HealthDot label="YouTube" status={health?.checks.youtube_api ?? "unknown"} />
          <HealthDot label="AI" status={health?.checks.ai_provider ?? "unknown"} />
        </div>
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-zinc-200">{user?.name ?? "User"}</p>
            <p className="truncate text-xs text-zinc-500">{user?.email ?? ""}</p>
          </div>
          <Button variant="ghost" onClick={onLogout} title="Log out">
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex min-h-screen bg-zinc-950">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 border-r border-zinc-800 bg-zinc-900/60 backdrop-blur lg:block">
        {sidebar}
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/70" onClick={() => setMobileOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64 bg-zinc-900 shadow-2xl">
            <button
              className="absolute right-3 top-4 text-zinc-400"
              onClick={() => setMobileOpen(false)}
              aria-label="Close menu"
            >
              <X className="h-5 w-5" />
            </button>
            {sidebar}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col lg:pl-64">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-zinc-800 bg-zinc-950/90 px-4 backdrop-blur lg:px-8">
          <button
            className="text-zinc-400 lg:hidden"
            onClick={() => setMobileOpen(true)}
            aria-label="Open menu"
          >
            <Menu className="h-5 w-5" />
          </button>
          <div className="flex-1" />
          {channels.length > 0 && <ChannelSelect />}
        </header>
        <main className="flex-1 px-4 py-6 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
