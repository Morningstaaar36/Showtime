import { Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tip } from "@/components/ui/tooltip";
import { t } from "@/i18n";
import { useUi } from "@/state/ui";

export function ThemeToggle() {
  const theme = useUi((s) => s.theme);
  const setTheme = useUi((s) => s.setTheme);
  const dark = theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  const label = dark ? t("nav.theme_light") : t("nav.theme_dark");
  return (
    <Tip content={label}>
      {/* a full 44 px touch target on phones, compact on desktop */}
      <Button variant="ghost" size="icon" aria-label={label} className="size-11 md:size-9"
              onClick={() => setTheme(dark ? "light" : "dark")}>
        {dark ? <Sun /> : <Moon />}
      </Button>
    </Tip>
  );
}
