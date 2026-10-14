import { MapPinOff } from "lucide-react";
import { Link } from "react-router";
import { AppShell } from "@/app/AppHeader";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";

/** Unknown address: say so plainly and offer the two places people usually want. */
export function NotFound() {
  return (
    <AppShell className="bg-hero">
      <div className="mx-auto flex w-full max-w-xl flex-col items-center px-4 py-20 text-center">
        <span className="grid size-16 place-items-center rounded-full bg-orange-soft text-orange [&_svg]:size-8" aria-hidden><MapPinOff /></span>
        <p className="mt-5 text-sm font-semibold text-muted">{t("notfound.code")}</p>
        <h1 className="mt-1 text-3xl font-bold leading-tight tracking-tight">{t("notfound.title")}</h1>
        <p className="mt-2 text-lg text-muted">{t("notfound.body")}</p>
        <div className="mt-7 flex flex-wrap justify-center gap-2">
          <Button asChild variant="primary" size="lg"><Link to="/">{t("notfound.home")}</Link></Button>
          <Button asChild size="lg"><Link to="/projects">{t("notfound.projects")}</Link></Button>
        </div>
      </div>
    </AppShell>
  );
}
