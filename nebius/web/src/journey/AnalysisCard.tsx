/** What an analysis script computed: the facts, a small table, a bar chart and the code behind it.
 * Used by "Ask or change anything" (the analyst's answer) and the Scripts page (your own scripts).
 * Numbers come only from the code's output; the written answer is shown only when it passed the
 * number check on the server. */
import { AlertTriangle, ChevronDown, Code2, Cpu, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import { type Chart, analysisView } from "./analysis";

interface AnalysisCardProps {
  status: "ok" | "error" | "timeout" | "rejected";
  output: unknown;
  code?: string;
  /** The analyst's number-checked answer (absent for your own scripts). */
  answer?: string;
  numbersChecked?: boolean;
  plan?: string;
  runtimeS?: number;
  sandbox?: string;
  basis?: string;
  stdoutTail?: string;
  stderrTail?: string;
  problems?: string[];
}

export function AnalysisCard(p: AnalysisCardProps) {
  const view = useMemo(() => analysisView(p.output), [p.output]);
  const failed = p.status !== "ok";
  return (
    <div className="space-y-3">
      {p.answer && <p className="text-base leading-relaxed">{p.answer}</p>}
      {p.numbersChecked !== undefined && p.status === "ok" && (
        <p className="flex items-center gap-1.5 text-xs text-muted">
          <ShieldCheck className="size-3.5 shrink-0 text-egress" />{p.numbersChecked ? t("analyst.checked") : t("analyst.unchecked")}
        </p>
      )}
      {failed && (
        <div role="alert" className="space-y-1">
          <p className="flex gap-2 font-medium"><AlertTriangle className="mt-0.5 size-4 shrink-0 text-caution" />{t(`analyst.${p.status}`)}</p>
          {p.problems?.map((x) => <p key={x} className="text-muted">{x}</p>)}
          {p.stderrTail && <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-[8px] bg-surface-2 p-2 font-mono text-xs">{p.stderrTail}</pre>}
        </div>
      )}
      {!failed && <Results view={view} />}
      {p.stdoutTail && !failed && (
        <details className="text-xs">
          <summary className="cursor-pointer text-muted">{t("analyst.stdout")}</summary>
          <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded-[8px] bg-surface-2 p-2 font-mono">{p.stdoutTail}</pre>
        </details>
      )}
      <div className="space-y-0.5 text-xs text-muted">
        <p className="flex items-center gap-1.5"><Cpu className="size-3.5 shrink-0" />{t("analyst.computed")}
          {p.runtimeS !== undefined && <> · {t("analyst.runtime", { s: p.runtimeS.toFixed(1), sandbox: p.sandbox ?? "sandbox" })}</>}
        </p>
        {p.basis && <p>{t("analyst.based_on", { basis: p.basis })}</p>}
      </div>
      {p.code && <CodeBlock code={p.code} plan={p.plan} />}
    </div>
  );
}

function Results({ view }: { view: ReturnType<typeof analysisView> }) {
  const empty = !view.facts.length && !view.table && !view.chart;
  if (empty && !view.raw) return <p className="text-muted">{t("analyst.no_output")}</p>;
  return (
    <div className="space-y-3">
      {view.facts.length > 0 && (
        <dl aria-label={t("analyst.facts")} className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {view.facts.map((f) => (
            <div key={f.label} className="rounded-[8px] border border-border px-3 py-2">
              <dt className="text-xs text-muted">{f.label}</dt>
              <dd className="tabular text-lg font-semibold">{f.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {view.chart && <BarChart chart={view.chart} />}
      {view.table && (
        <div className="max-h-56 overflow-auto rounded-[8px] border border-border">
          <table className="w-full text-sm">
            <caption className="sr-only">{t("analyst.table")}</caption>
            <thead className="sticky top-0 bg-surface-2 text-xs text-muted">
              <tr>{view.table.columns.map((c) => <th key={c} scope="col" className="px-2 py-1 text-left font-medium">{c}</th>)}</tr>
            </thead>
            <tbody>
              {view.table.rows.map((r, i) => (
                <tr key={`row-${i}`} className="border-t border-border">
                  {r.map((v, j) => <td key={view.table?.columns[j]} className="tabular px-2 py-1">{v}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {empty && view.raw && (
        <pre className="max-h-48 overflow-auto rounded-[8px] bg-surface-2 p-2 font-mono text-xs">{view.raw}</pre>
      )}
    </div>
  );
}

/** One series, so no legend: the title names it. Thin bars from a shared baseline, the value in
 * ink beside each bar, a hover/focus title per bar, and the table above as the accessible view. */
function BarChart({ chart }: { chart: Chart }) {
  return (
    <figure className="space-y-1.5">
      <figcaption className="text-xs font-medium text-muted">{chart.title}</figcaption>
      <ul className="space-y-0.5">
        {chart.bars.map((b, i) => {
          const pct = chart.max > 0 ? Math.max(0.5, (Math.abs(b.value) / chart.max) * 100) : 0;
          return (
            <li key={`bar-${i}`} title={`${chart.x} ${b.label}: ${chart.y} ${b.text}`}
                className="group grid grid-cols-[minmax(2.5rem,auto)_1fr_auto] items-center gap-2 rounded-[4px] text-xs hover:bg-surface-2">
              <span className="truncate text-right text-muted">{b.label}</span>
              <span className="h-2.5" aria-hidden>
                <span className="block h-full rounded-r-[4px] bg-signal group-hover:brightness-110" style={{ width: `${pct}%` }} />
              </span>
              <span className="tabular text-ink">{b.text}</span>
            </li>
          );
        })}
      </ul>
    </figure>
  );
}

function CodeBlock({ code, plan }: { code: string; plan?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
              className="inline-flex min-h-11 items-center gap-1.5 text-sm font-medium text-signal hover:underline">
        <Code2 className="size-4" />{open ? t("analyst.hide_code") : t("analyst.show_code")}
        <ChevronDown className={cn("size-4 transition", open && "rotate-180")} />
      </button>
      {open && (
        <div className="space-y-1">
          {plan && <p className="text-xs text-muted">{t("analyst.plan", { plan })}</p>}
          <pre className="max-h-72 overflow-auto rounded-[8px] bg-surface-2 p-3 font-mono text-xs leading-relaxed"><code>{code}</code></pre>
        </div>
      )}
    </div>
  );
}
