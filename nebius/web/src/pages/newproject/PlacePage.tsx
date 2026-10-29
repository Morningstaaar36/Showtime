/** "Pick it on the map" (route `/new/place`): a full-width map where the organizer finds their real
 * place, clicks the building or park, builds the venue and continues to step 1b (check it). */
import { Loader2 } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { useCreateProject } from "@/api/queries";
import type { VenueDraft } from "@/api/types";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { JourneyShell } from "@/journey/JourneyShell";
import { MapTab } from "./MapTab";

export function PlacePage() {
  const [draft, setDraft] = useState<VenueDraft | null>(null);
  const create = useCreateProject();
  const navigate = useNavigate();
  const use = () => {
    if (!draft?.venue) return;
    create.mutate({ name: draft.venue.name, venue: draft.venue, description: t("projects.from_map") }, {
      onSuccess: (p) => navigate(`/p/${p.id}/describe`),
      onError: (e) => toast.error(e.message),
    });
  };
  return (
    <JourneyShell step="describe" back={{ to: "/", label: t("journey.home") }}>
      <main id="main" className="mx-auto w-full max-w-6xl space-y-4 px-4 py-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{t("place.title")}</h1>
          <p className="mt-1 text-base text-muted">{t("place.lead")}</p>
        </div>
        <MapTab onDraft={setDraft} guided mapClassName="h-[58vh] min-h-[360px]" />
        {draft?.venue && (
          <div className="sticky bottom-3 z-10 flex flex-wrap items-center justify-between gap-3 rounded-[var(--radius-panel)] border-2 border-egress/40 bg-surface p-3 shadow-[var(--shadow-float)]">
            <p className="text-base"><span className="font-semibold">{t("place.ready", { name: draft.venue.name })}</span>
              <span className="block text-sm text-muted">{t("place.ready_lead")}</span></p>
            <Button variant="primary" size="lg" disabled={create.isPending} onClick={use}>
              {create.isPending ? <Loader2 className="animate-spin" /> : null}{t("place.use")}
            </Button>
          </div>
        )}
      </main>
    </JourneyShell>
  );
}
