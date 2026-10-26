import { Navigate, Route, Routes, useParams } from "react-router";
import { Toaster } from "sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AiAtWorkPage } from "@/pages/AiAtWork";
import { AutopilotRunPage } from "@/pages/AutopilotRun";
import { CheckVenuePage } from "@/pages/CheckVenue";
import { HelpPage } from "@/pages/Help";
import { TeamPage } from "@/pages/Team";
import { HomePage } from "@/pages/Home";
import { NotFound } from "@/pages/NotFound";
import { PlacePage } from "@/pages/newproject/PlacePage";
import { OnboardingPage } from "@/pages/Onboarding";
import { ProjectsPage } from "@/pages/Projects";
import { ScriptsPage } from "@/pages/Scripts";
import { SettingsPage } from "@/pages/Settings";
import { WorkspacePage } from "@/pages/Workspace";
import { YourPlanPage } from "@/pages/YourPlan";
import { useApplyTheme } from "./useTheme";
import { t } from "@/i18n";

const EXPERT_MODES = ["plan", "simulate", "redteam", "report"];

/** Old workspace URLs (/p/:id/simulate …) open the same mode in Expert view. */
function LegacyMode() {
  const { projectId = "", mode = "" } = useParams();
  if (!EXPERT_MODES.includes(mode)) return <NotFound />;
  return <Navigate to={`/p/${projectId}/expert/${mode}${window.location.search}`} replace />;
}

export function App() {
  useApplyTheme();
  return (
    <TooltipProvider>
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2">
        {t("ui.app.skip_to_content")}</a>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/new/place" element={<PlacePage />} />
        <Route path="/autopilot/:runId" element={<AutopilotRunPage />} />
        <Route path="/welcome" element={<OnboardingPage />} />
        <Route path="/p/:projectId" element={<YourPlanPage />} />
        <Route path="/p/:projectId/describe" element={<CheckVenuePage />} />
        <Route path="/p/:projectId/work" element={<AiAtWorkPage />} />
        <Route path="/p/:projectId/expert" element={<WorkspacePage />} />
        <Route path="/p/:projectId/expert/:mode" element={<WorkspacePage />} />
        <Route path="/p/:projectId/scripts" element={<ScriptsPage />} />
        <Route path="/p/:projectId/:mode" element={<LegacyMode />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/help" element={<HelpPage />} />
        <Route path="/team" element={<TeamPage />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
      {/* bottom-left: the primary actions ("Test this plan", "Run stress test") sit on the right, and a
          "saved as version N" toast over them swallowed the click (G3-06) */}
      <Toaster position="bottom-left" closeButton toastOptions={{
        className: "!rounded-[10px] !border !border-border !bg-surface !text-ink !shadow-[var(--shadow-float)] !font-sans",
      }} />
    </TooltipProvider>
  );
}
