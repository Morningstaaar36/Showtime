/** Your plan › Scenarios: every source the attacks were grounded in, in two labelled groups:
 * live web results (Tavily) and the incident dataset. The web group appears only when it has
 * results; without a key the panel says web search is off. */
import { Database, ExternalLink, Globe } from "lucide-react";
import { useHealth } from "@/api/queries";
import type { Attack } from "@/api/types";
import { t } from "@/i18n";
import { type EvidenceItem, evidenceGroups, withYear } from "./evidence";

function Group({ id, icon, title, items }: { id: string; icon: React.ReactNode; title: string; items: EvidenceItem[] }) {
  return (
    <section aria-labelledby={id} className="space-y-2" data-testid={`evidence-${id}`}>
      <h3 id={id} className="flex items-center gap-1.5 text-sm font-semibold [&_svg]:size-4">{icon}{title} <span className="font-normal text-muted">· {items.length}</span></h3>
      <ul className="space-y-2">
        {items.map((e) => (
          <li key={e.url} className="rounded-[var(--radius-control)] border border-border bg-surface p-3 text-sm">
            <a href={e.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-medium text-signal hover:underline">
              {withYear(e.title, e.year)}<ExternalLink className="size-3" aria-hidden />
            </a>
            {e.sentence && <p className="mt-1 text-muted">“{e.sentence}”</p>}
            <p className="mt-1 text-xs text-muted">{t("evidence_panel.supports", { attacks: e.attacks.join("; ") })}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function EvidencePanel({ attacks, human }: { attacks: Attack[]; human: (s: string) => string }) {
  const health = useHealth();
  const search = health.data?.providers.search;
  const g = evidenceGroups(attacks, human);
  if (!g.tavily.length && !g.dataset.length) return null;
  return (
    <section aria-labelledby="evidence-h" className="space-y-3" data-testid="evidence-panel">
      <div>
        <h2 id="evidence-h" className="text-lg font-semibold">{t("evidence_panel.title")}</h2>
        <p className="text-sm text-muted">{t("evidence_panel.lead")}</p>
      </div>
      {g.tavily.length > 0 && <Group id="web" icon={<Globe />} title={t("evidence_panel.web")} items={g.tavily} />}
      {g.dataset.length > 0 && <Group id="dataset" icon={<Database />} title={t("evidence_panel.dataset")} items={g.dataset} />}
      {!g.tavily.length && search && !search.live && <p className="text-xs text-muted" data-testid="search-off">{t("evidence_panel.search_off")}</p>}
    </section>
  );
}
