/** Your plan › Hand over: big tiles for what goes to the team (the report, the evacuation map,
 * the checklist, the data bundle), how the plan was made, and what to do next. */
import { Braces, ClipboardCheck, Download, FileText, Map as MapIcon, Pencil, RotateCcw } from "lucide-react";
import type * as React from "react";
import { Link } from "react-router";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";

function Tile({ href, icon, title, body, label, tone, preview, download }: {
  href: string; icon: React.ReactNode; title: string; body: string; label: string; tone: string; preview?: React.ReactNode; download?: boolean;
}) {
  return (
    <li>
      <a href={href} target="_blank" rel="noreferrer" aria-label={label} download={download || undefined}
         className="group flex h-full flex-col overflow-hidden rounded-[var(--radius-panel)] border-2 border-transparent bg-surface shadow-sm transition hover:-translate-y-0.5 hover:border-signal focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-signal">
        <span className={cn("relative grid h-32 place-items-center overflow-hidden", tone)}>
          {preview ?? <span className="grid size-16 place-items-center rounded-full bg-surface/70 [&_svg]:size-8">{icon}</span>}
        </span>
        <span className="flex flex-1 flex-col gap-1 p-4">
          <span className="flex items-center gap-2 text-lg font-bold">{title}</span>
          <span className="text-sm text-muted">{body}</span>
          <span className="mt-auto inline-flex items-center gap-1.5 pt-2 text-sm font-semibold text-signal"><Download className="size-4" aria-hidden />{t("plan.ho_get")}</span>
        </span>
      </a>
    </li>
  );
}

export function HandOver({ sessionId, projectId, onTestAgain, testing, children }: {
  sessionId: string; projectId: string; onTestAgain: () => void; testing: boolean; children?: React.ReactNode;
}) {
  const url = (p: string) => api.url(`/sessions/${sessionId}${p}`);
  return (
    <div className="space-y-4">
      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Tile href={url("/report")} icon={<FileText />} title={t("plan.ho_report")} body={t("plan.ho_report_body")} label={t("plan.ho_report_label")}
              tone="bg-signal-soft text-signal" />
        <Tile href={url("/map.svg")} icon={<MapIcon />} title={t("plan.ho_map")} body={t("plan.ho_map_body")} label={t("report.export_map")} download
              tone="bg-egress-soft text-egress-strong"
              preview={<img src={url("/map.svg")} alt="" className="size-full bg-white object-contain p-2" loading="lazy" />} />
        <Tile href={url("/checklist")} icon={<ClipboardCheck />} title={t("plan.ho_checklist")} body={t("plan.ho_checklist_body")} label={t("checklist.download")}
              tone="bg-sky-soft text-sky-strong" />
        <Tile href={url("/bundle.json")} icon={<Braces />} title={t("plan.ho_data")} body={t("plan.ho_data_body")} label={t("report.export_json")} download
              tone="bg-surface-3 text-ink" />
      </ul>
      {children}
      <div className="flex flex-wrap gap-2">
        <Button size="lg" onClick={onTestAgain} disabled={testing}><RotateCcw />{t("yourplan.test_again")}</Button>
        <Button asChild variant="ghost" size="lg"><Link to={`/p/${projectId}/describe`}><Pencil />{t("yourplan.change_venue")}</Link></Button>
      </div>
    </div>
  );
}
