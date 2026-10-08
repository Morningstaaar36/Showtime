import { Link } from "react-router";
import { AppHeader } from "@/app/AppHeader";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";

export function NotFound() {
  return (
    <div className="min-h-full">
      <AppHeader />
      <main id="main" className="mx-auto max-w-xl px-4 py-24">
        <p className="text-sm font-medium text-signal">404</p>
        <h1 className="mt-2 text-2xl font-semibold">{t("errors.not_found")}</h1>
        <Button asChild variant="primary" className="mt-6"><Link to="/">{t("errors.back")}</Link></Button>
      </main>
    </div>
  );
}
