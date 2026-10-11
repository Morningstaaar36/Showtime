import { Navigate, Route, Routes, useParams } from "react-router";
import { Toaster } from "sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AiAtWorkPage } from "@/pages/AiAtWork";
import { CheckVenuePage } from "@/pages/CheckVenue";
import { HelpPage } from "@/pages/Help";
import { HomePage } from "@/pages/Home";
import { NotFound } from "@/pages/NotFound";
import { OnboardingPage } from "@/pages/Onboarding";
import { ProjectsPage } from "@/pages/Projects";
import { SettingsPage } from "@/pages/Settings";
import { WorkspacePage } from "@/pages/Workspace";
import { YourPlanPage } from "@/pages/YourPlan";
import { useApplyTheme } from "./useTheme";

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
        Skip to content
      </a>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/welcome" element={<OnboardingPage />} />
        <Route path="/p/:projectId" element={<YourPlanPage />} />
        <Route path="/p/:projectId/describe" element={<CheckVenuePage />} />
        <Route path="/p/:projectId/work" element={<AiAtWorkPage />} />
        <Route path="/p/:projectId/expert" element={<WorkspacePage />} />
        <Route path="/p/:projectId/expert/:mode" element={<WorkspacePage />} />
        <Route path="/p/:projectId/:mode" element={<LegacyMode />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/help" element={<HelpPage />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
      <Toaster position="bottom-right" closeButton toastOptions={{
        className: "!rounded-[10px] !border !border-border !bg-surface !text-ink !shadow-[var(--shadow-float)] !font-sans",
      }} />
    </TooltipProvider>
  );
}
