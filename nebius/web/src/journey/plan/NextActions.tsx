/** The next steps at the bottom of Your plan: the report, the handover checklist, a new test. */
import { ClipboardCheck, Download, Pencil, RotateCcw } from "lucide-react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";

export function NextActions({ reportUrl, checklistUrl, projectId, onTestAgain, testing, primary }: {
  reportUrl: string;
  checklistUrl: string;
  projectId: string;
  onTestAgain: () => void;
  testing: boolean;
  /** the one obvious next step, or none when the page's primary action is elsewhere */
  primary: "report" | "test" | null;
}) {
  return (
    <section aria-labelledby="next-h" className="space-y-2 rounded-[var(--radius-panel)] border border-border bg-surface p-4 shadow-sm">
      <h2 id="next-h" className="font-semibold">{t("yourplan.next")}</h2>
      <div className="flex flex-wrap gap-2">
        <Button asChild variant={primary === "report" ? "primary" : "secondary"} size="lg">
          <a href={reportUrl} target="_blank" rel="noreferrer"><Download />{t("yourplan.report")}</a>
        </Button>
        <Button asChild variant="secondary" size="lg">
          <a href={checklistUrl} target="_blank" rel="noreferrer" title={t("checklist.hint")}><ClipboardCheck />{t("checklist.download")}</a>
        </Button>
        <Button variant={primary === "test" ? "primary" : "secondary"} size="lg" onClick={onTestAgain} disabled={testing}><RotateCcw />{t("yourplan.test_again")}</Button>
        <Button asChild variant="ghost" size="lg"><Link to={`/p/${projectId}/describe`}><Pencil />{t("yourplan.change_venue")}</Link></Button>
      </div>
      <p className="text-xs text-muted">{t("checklist.hint")}</p>
    </section>
  );
}
