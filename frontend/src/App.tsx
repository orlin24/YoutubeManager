import { Suspense, lazy, useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppLayout } from "./layouts/AppLayout";
import { useAuthStore } from "./stores/auth";
import { Spinner } from "./components/common/Button";
import OAuthNotice from "./components/common/OAuthNotice";

const LoginPage = lazy(() => import("./pages/auth/LoginPage"));
const NotFoundPage = lazy(() => import("./pages/NotFoundPage"));
const DashboardPage = lazy(() => import("./pages/dashboard/DashboardPage"));
const CalendarPage = lazy(() => import("./pages/calendar/CalendarPage"));
const CeoPage = lazy(() => import("./pages/ceo/CeoPage"));
const PortfolioPage = lazy(() => import("./pages/portfolio/PortfolioPage"));
const ChannelsPage = lazy(() => import("./pages/channels/ChannelsPage"));
const VideosPage = lazy(() => import("./pages/videos/VideosPage"));
const VideoDetailPage = lazy(() => import("./pages/videos/VideoDetailPage"));
const AnalyticsPage = lazy(() => import("./pages/analytics/AnalyticsPage"));
const ContentPlanPage = lazy(() => import("./pages/content-plan/ContentPlanPage"));
const AiAssistantPage = lazy(() => import("./pages/ai/AiAssistantPage"));
const AutonomousPage = lazy(() => import("./pages/ai/AutonomousPage"));
const LearningPage = lazy(() => import("./pages/learning/LearningPage"));
const CommentsPage = lazy(() => import("./pages/comments/CommentsPage"));
const PlaylistsPage = lazy(() => import("./pages/playlists/PlaylistsPage"));
const AuditPage = lazy(() => import("./pages/audit/AuditPage"));
const SettingsPage = lazy(() => import("./pages/settings/SettingsPage"));
const TutorialPage = lazy(() => import("./pages/tutorial/TutorialPage"));

function Loading() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 text-brand-400">
      <Spinner className="h-8 w-8" />
    </div>
  );
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user);
  const ensureLoaded = useAuthStore((s) => s.ensureLoaded);
  const location = useLocation();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    ensureLoaded().finally(() => setReady(true));
    const onExpired = () => {
      useAuthStore.getState().logout();
    };
    window.addEventListener("auth:expired", onExpired);
    return () => window.removeEventListener("auth:expired", onExpired);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!ready) return <Loading />;
  if (!user) {
    // Preserve the query string (e.g. ?error=google_auth_failed) through the redirect.
    return (
      <Navigate
        to={{ pathname: "/auth/login", search: location.search }}
        state={{ from: location.pathname + location.search }}
        replace
      />
    );
  }
  return <>{children}</>;
}

export default function App() {
  return (
    <Suspense fallback={<Loading />}>
      <OAuthNotice />
      <Routes>
        <Route path="/auth/login" element={<LoginPage />} />
        <Route
          element={
            <ProtectedRoute>
              <AppLayout />
            </ProtectedRoute>
          }
        >
          <Route path="/" element={<DashboardPage />} />
          <Route path="/calendar" element={<CalendarPage />} />
          <Route path="/ai/ceo" element={<CeoPage />} />
          <Route path="/portfolio" element={<PortfolioPage />} />
          <Route path="/channels" element={<ChannelsPage />} />
          <Route path="/videos" element={<VideosPage />} />
          <Route path="/videos/:id" element={<VideoDetailPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/content-plan" element={<ContentPlanPage />} />
          <Route path="/ai" element={<AiAssistantPage />} />
          <Route path="/ai/autonomous" element={<AutonomousPage />} />
          <Route path="/ai/learning" element={<LearningPage />} />
          <Route path="/comments" element={<CommentsPage />} />
          <Route path="/playlists" element={<PlaylistsPage />} />
          <Route path="/audit" element={<AuditPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/tutorial" element={<TutorialPage />} />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  );
}
