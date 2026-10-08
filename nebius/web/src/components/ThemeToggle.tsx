import { Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tip } from "@/components/ui/tooltip";
import { useUi } from "@/state/ui";

export function ThemeToggle() {
  const theme = useUi((s) => s.theme);
  const setTheme = useUi((s) => s.setTheme);
  const dark = theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  return (
    <Tip content={dark ? "Light theme" : "Dark theme"}>
      <Button variant="ghost" size="icon-sm" aria-label={dark ? "Light theme" : "Dark theme"}
              onClick={() => setTheme(dark ? "light" : "dark")}>
        {dark ? <Sun /> : <Moon />}
      </Button>
    </Tip>
  );
}
