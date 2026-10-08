import { Route, Routes } from "react-router";
import { Toaster } from "sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { HelpPage } from "@/pages/Help";
import { NotFound } from "@/pages/NotFound";
import { OnboardingPage } from "@/pages/Onboarding";
import { ProjectsPage } from "@/pages/Projects";
import { SettingsPage } from "@/pages/Settings";
import { WorkspacePage } from "@/pages/Workspace";
import { useApplyTheme } from "./useTheme";

export function App() {
  useApplyTheme();
  return (
    <TooltipProvider>
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2">
        Skip to content
      </a>
      <Routes>
        <Route path="/" element={<ProjectsPage />} />
        <Route path="/welcome" element={<OnboardingPage />} />
        <Route path="/p/:projectId" element={<WorkspacePage />} />
        <Route path="/p/:projectId/:mode" element={<WorkspacePage />} />
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
