/** Home: events like yours, as illustrated tiles. A tile with a ready sample opens it (tested,
 * with results); the others fill in "Describe it" with a good description to start from. */
import { ArrowRight, Building2, Disc3, Flag, Hospital, Landmark, Music, Presentation, School, ShoppingBag, Trophy } from "lucide-react";
import type * as React from "react";
import type { ProjectSummary } from "@/api/types";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";

export interface UseCase {
  id: string;
  icon: React.ReactNode;
  /** tile background: soft decorative tokens only (safety colours carry meaning elsewhere) */
  tone: string;
  /** a sample project to open, matched by name */
  sample?: RegExp;
  floors?: number;
}

export const USE_CASES: UseCase[] = [
  { id: "concert", icon: <Music />, tone: "from-pink-soft to-orange-soft text-pink", sample: /festival|wellington/i },
  { id: "hospital", icon: <Hospital />, tone: "from-sky-soft to-signal-soft text-sky-strong", sample: /riverside|ward block/i, floors: 4 },
  { id: "school", icon: <School />, tone: "from-orange-soft to-pink-soft text-orange", floors: 3 },
  { id: "stadium", icon: <Trophy />, tone: "from-teal-soft to-sky-soft text-teal" },
  { id: "pandal", icon: <Landmark />, tone: "from-orange-soft to-signal-soft text-orange" },
  { id: "mall", icon: <ShoppingBag />, tone: "from-signal-soft to-pink-soft text-signal", floors: 4 },
  { id: "nightclub", icon: <Disc3 />, tone: "from-signal-soft to-sky-soft text-signal" },
  { id: "parade", icon: <Flag />, tone: "from-pink-soft to-signal-soft text-pink", sample: /halloween|alley/i },
  { id: "conference", icon: <Presentation />, tone: "from-sky-soft to-teal-soft text-sky-strong", sample: /summit|two-floor/i, floors: 2 },
];

export function sampleFor(uc: UseCase, projects: ProjectSummary[] | undefined): ProjectSummary | undefined {
  if (!uc.sample) return undefined;
  return (projects ?? []).find((p) => p.sample && uc.sample!.test(p.name));
}

export function UseCaseGallery({ projects, onSample, onDescribe }: {
  projects: ProjectSummary[] | undefined;
  onSample: (projectId: string) => void;
  onDescribe: (text: string) => void;
}) {
  return (
    <section aria-labelledby="uc-h" className="space-y-4">
      <div>
        <h2 id="uc-h" className="text-2xl font-bold tracking-tight">{t("home.uc_title")}</h2>
        <p className="text-muted">{t("home.uc_lead")}</p>
      </div>
      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {USE_CASES.map((uc, i) => {
          const sample = sampleFor(uc, projects);
          return (
            <li key={uc.id} className="animate-deal-in" style={{ animationDelay: `${i * 40}ms` }}>
              <button type="button" onClick={() => (sample ? onSample(sample.id) : onDescribe(t(`home.uc_${uc.id}_text`)))}
                      className="group flex h-full w-full flex-col overflow-hidden rounded-[var(--radius-panel)] border-2 border-transparent bg-surface text-left shadow-sm transition hover:-translate-y-0.5 hover:border-signal focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-signal">
                <span className={cn("relative grid h-24 place-items-center bg-gradient-to-br sm:h-28", uc.tone)}>
                  <span className="grid size-14 place-items-center rounded-full bg-surface/75 shadow-sm transition group-hover:scale-110 [&_svg]:size-7">{uc.icon}</span>
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
                  <span className="mt-auto inline-flex items-center gap-1 pt-1.5 text-xs font-semibold text-signal">
                    {sample ? t("home.uc_open") : t("home.uc_start")}<ArrowRight className="size-3.5 transition group-hover:translate-x-0.5" aria-hidden />
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
