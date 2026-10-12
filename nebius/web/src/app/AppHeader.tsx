import { HelpCircle, Settings } from "lucide-react";
import { Link, NavLink } from "react-router";
import { Logo } from "@/components/Logo";
import { ProviderBadge } from "@/components/ProviderBadge";
import { ThemeToggle } from "@/components/ThemeToggle";
import { cn } from "@/lib/utils";

const nav = [
  { to: "/", label: "Plan an event", end: true },
  { to: "/projects", label: "Your plans" },
  { to: "/settings", label: "Settings", icon: Settings },
  { to: "/help", label: "Help", icon: HelpCircle },
];

/** Header for the Projects, Settings and Help screens. */
export function AppHeader() {
  return (
    <header className="sticky top-0 z-30 border-b border-border bg-plan/85 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-4">
        <Link to="/" aria-label="Showtime home"><Logo /></Link>
        <nav className="flex items-center gap-1">
          {nav.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end}
                     className={({ isActive }) => cn("rounded-[var(--radius-control)] px-3 py-1.5 text-sm font-medium transition-colors",
                       isActive ? "bg-surface-3 text-ink" : "text-muted hover:text-ink")}>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <ProviderBadge />
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
