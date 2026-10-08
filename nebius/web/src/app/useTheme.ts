import { useEffect } from "react";
import { useUi } from "@/state/ui";

/** Applies the theme class on <html>; "system" follows prefers-color-scheme. */
export function useApplyTheme(): void {
  const theme = useUi((s) => s.theme);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const dark = theme === "dark" || (theme === "system" && mq.matches);
      document.documentElement.classList.toggle("dark", dark);
    };
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [theme]);
}
