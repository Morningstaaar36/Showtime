import { Braces, Download, FileText, Map, Printer, RefreshCw } from "lucide-react";
import { useRef, useState } from "react";
import { api } from "@/api/client";
import { useRuns, useSessions } from "@/api/queries";
import type { ProjectDetail } from "@/api/types";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/states";
import { t } from "@/i18n";
import { fmtRelative } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Report preview and exports. */
export function ReportView({ project }: { project: ProjectDetail }) {
  const sessions = useSessions(project.id);
  const runs = useRuns(project.id);
  const finished = (sessions.data ?? []).filter((s) => s.status === "finished" || s.status === "stopped");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const frame = useRef<HTMLIFrameElement>(null);
  const sid = sessionId ?? finished[0]?.id ?? null;
  const q = sid ? `?session=${sid}` : "";
  const hasStress = (runs.data ?? []).some((r) => r.tier === 3 && (r.status === "ok" || r.status === "partial"));
  const ready = !!sid || hasStress;
  const reportUrl = api.url(`/projects/${project.id}/report${q}`);

  return (
    <div className="flex h-full min-h-0">
      <aside className="w-80 shrink-0 space-y-5 overflow-y-auto border-r border-border bg-surface p-5 scrollbar-thin">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">{t("report.title")}</h2>
          <p className="mt-1 text-sm text-muted">A document for your safety team and the permit office: verdict, countdown, evacuation map, red-team results, assumptions and sources.</p>
        </div>
        {finished.length > 0 && (
          <section>
            <p className="text-sm font-semibold">Based on</p>
            <ul className="mt-2 space-y-1.5">
              {finished.map((s) => (
                <li key={s.id}>
                  <button type="button" onClick={() => setSessionId(s.id)}
                          className={cn("w-full rounded-[8px] border px-3 py-2 text-left text-sm",
                            s.id === sid ? "border-signal bg-signal-soft/50" : "border-border hover:bg-surface-2")}>
                    <span className="font-medium">Red Team Night</span>
                    <span className="block text-xs text-muted">{fmtRelative(s.created_at)} · {(s.summary?.accepted_fixes ?? []).length} {(s.summary?.accepted_fixes ?? []).length === 1 ? "fix" : "fixes"} kept</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}
        <section className="space-y-2">
          <Button variant="primary" size="lg" className="w-full" disabled={!ready}
                  onClick={() => frame.current?.contentWindow?.print()}>
            <Printer />{t("report.export_pdf")}
          </Button>
          <p className="text-xs text-muted">{t("report.print_hint")}</p>
          <Button className="w-full justify-start" disabled={!ready} asChild={ready}>
            {ready ? <a href={api.url(`/projects/${project.id}/map.svg${q}`)} download><Map />{t("report.export_map")}</a> : <span><Map />{t("report.export_map")}</span>}
          </Button>
          <Button className="w-full justify-start" disabled={!ready} asChild={ready}>
            {ready ? <a href={api.url(`/projects/${project.id}/bundle.json${q}`)} download><Braces />{t("report.export_json")}</a> : <span><Braces />{t("report.export_json")}</span>}
          </Button>
          <Button className="w-full justify-start" asChild>
            <a href={api.url(`/projects/${project.id}/export`)} download><Download />{t("report.export_project")}</a>
          </Button>
        </section>
        <Button variant="ghost" size="sm" onClick={() => setNonce((n) => n + 1)}><RefreshCw />Refresh preview</Button>
        <p className="text-xs text-muted">{t("app.disclaimer")}</p>
      </aside>
      <div className="min-w-0 flex-1 bg-plan">
        {ready ? (
          <iframe key={`${sid}:${nonce}:${project.current_version}`} ref={frame} title="Report preview" src={reportUrl}
                  className="size-full border-0" />
        ) : (
          <div className="mx-auto max-w-xl p-10">
            <EmptyState icon={<FileText />} title={t("report.empty")} body="The report uses confirmed simulation results only." />
          </div>
        )}
      </div>
    </div>
  );
}
