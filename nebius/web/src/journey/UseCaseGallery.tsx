/** Home: events like yours, as illustrated tiles, the tested samples first. A tile with a ready
 * sample opens it (tested, with results); the others fill in "Describe it" with a good description
 * to start from. This is Home's one gallery of samples. */
import { Building2, Disc3, Flag, Hospital, Landmark, Music, Presentation, School, ShoppingBag, Trophy } from "lucide-react";
import type * as React from "react";
import type { ProjectSummary } from "@/api/types";
import { t } from "@/i18n";
import { RealCaseRow } from "./RealCases";

interface UseCase {
  id: string;
  icon: React.ReactNode;
  floors?: number;
}

const USE_CASES: UseCase[] = [
  { id: "concert", icon: <Music /> },
  { id: "hospital", icon: <Hospital />, floors: 4 },
  { id: "school", icon: <School />, floors: 3 },
  { id: "stadium", icon: <Trophy /> },
  { id: "pandal", icon: <Landmark /> },
  { id: "mall", icon: <ShoppingBag />, floors: 4 },
  { id: "nightclub", icon: <Disc3 /> },
  { id: "parade", icon: <Flag /> },
  { id: "conference", icon: <Presentation />, floors: 2 },
];

/** The sample project each tile opens. A sample built from a template carries the template's id
 * (ProjectSummary.template_id), so that is what we match. The hospital sample was not built from
 * a template and the server tags samples with nothing else, so it is still found by its name
 * (the packs in cache/demos); rename that sample and this pattern must follow. */
const SAMPLE_OF: Record<string, { template: string } | { name: RegExp }> = {
  concert: { template: "festival_field" },
  hospital: { name: /riverside|ward block/i },
  parade: { template: "t_alley" },
  conference: { template: "conference_hall_2f" },
};

function sampleFor(uc: UseCase, projects: ProjectSummary[] | undefined): ProjectSummary | undefined {
  const match = SAMPLE_OF[uc.id];
  if (!match) return undefined;
  return (projects ?? []).find((p) => p.sample && ("template" in match ? p.template_id === match.template : match.name.test(p.name)));
}

export function UseCaseGallery({ projects, onSample, onDescribe }: {
  projects: ProjectSummary[] | undefined;
  onSample: (projectId: string) => void;
  onDescribe: (text: string) => void;
}) {
  // tested samples first: they open with results at once
  const tiles = USE_CASES.map((uc) => ({ uc, sample: sampleFor(uc, projects) }))
    .sort((a, b) => Number(!!b.sample) - Number(!!a.sample));
  return (
    <section aria-labelledby="uc-h" className="space-y-4">
      <div>
        <h2 id="uc-h" className="text-2xl font-bold tracking-tight">{t("home.uc_title")}</h2>
        <p className="text-muted">{t("home.uc_lead")}</p>
      </div>
      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {tiles.map(({ uc, sample }, i) => {
          return (
            <li key={uc.id} className="animate-deal-in" style={{ animationDelay: `${i * 40}ms` }}>
              <button type="button" onClick={() => (sample ? onSample(sample.id) : onDescribe(t(`home.uc_${uc.id}_text`)))}
                      className="group flex h-full w-full flex-col overflow-hidden rounded-[var(--radius-panel)] border-2 border-transparent bg-surface text-left shadow-sm transition hover:-translate-y-0.5 hover:border-signal focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-signal">
                <span className="relative grid h-24 place-items-center bg-surface-2 text-ink sm:h-28">
                  <span className="grid size-14 place-items-center rounded-full bg-surface shadow-sm transition group-hover:scale-110 [&_svg]:size-7">{uc.icon}</span>
                  {uc.floors && (
                    <span className="absolute left-2 top-2 inline-flex items-center gap-1 rounded-full bg-surface/85 px-2 py-0.5 text-2xs font-semibold text-ink tabular">
                      <Building2 className="size-3" aria-hidden />{t("home.uc_floors", { n: uc.floors })}
                    </span>
                  )}
                  {sample && <span className="absolute right-2 top-2 rounded-full bg-ink px-2 py-0.5 text-2xs font-semibold text-plan">{t("home.uc_tested")}</span>}
                </span>
                <span className="flex flex-1 flex-col gap-0.5 p-3">
                  <span className="font-semibold leading-snug">{t(`home.uc_${uc.id}`)}</span>
                  <span className="text-xs text-muted">{t(`home.uc_${uc.id}_lead`)}</span>
                  <span className="mt-auto pt-1.5 text-xs font-semibold text-signal">{sample ? t("home.uc_open") : t("home.uc_start")}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      <RealCaseRow />
    </section>
  );
}
