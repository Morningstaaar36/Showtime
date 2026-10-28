/** Pure helpers that turn the JSON an analysis script printed into facts, a table and a bar chart.
 * Every value shown comes from the executed code; nothing is computed or rounded beyond display. */
import { t } from "@/i18n";

interface Fact { label: string; value: string }
interface Table { columns: string[]; rows: string[][] }
interface Bar { label: string; value: number; text: string }
export interface Chart { title: string; x: string; y: string; bars: Bar[]; max: number }
interface AnalysisView { facts: Fact[]; table: Table | null; chart: Chart | null; raw: string }

const MAX_FACTS = 12;
const MAX_ROWS = 30;
const MAX_COLUMNS = 6;
const MAX_RAW = 4000;

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const isPrimitive = (v: unknown) => v === null || ["string", "number", "boolean"].includes(typeof v);

/** A value as shown: numbers with at most 2 decimals and no trailing zeros. */
export function showValue(v: unknown): string {
  if (v === null || v === undefined) return "–";
  if (typeof v === "number") return Number.isFinite(v) ? v.toLocaleString("en-US", { maximumFractionDigits: 2 }) : "–";
  if (typeof v === "boolean") return t(v ? "analyst.yes" : "analyst.no");
  if (typeof v === "string") return v;
  return JSON.stringify(v);
}

function factsOf(output: unknown): Fact[] {
  if (isPrimitive(output) && output !== null) return [{ label: t("analyst.result"), value: showValue(output) }];
  if (!isObj(output)) return [];
  const source = isObj(output.facts) ? output.facts : output;
  return Object.entries(source)
    .filter(([k, v]) => isPrimitive(v) && !(source === output && ["table", "chart"].includes(k)))
    .slice(0, MAX_FACTS)
    .map(([label, v]) => ({ label: label.replaceAll("_", " "), value: showValue(v) }));
}

function rowsOf(output: unknown): Obj[] {
  const list = isObj(output) && Array.isArray(output.table) ? output.table : Array.isArray(output) ? output : [];
  return list.filter(isObj).slice(0, MAX_ROWS);
}

function tableOf(rows: Obj[]): Table | null {
  if (!rows.length) return null;
  const columns: string[] = [];
  for (const r of rows) for (const k of Object.keys(r)) if (!columns.includes(k) && columns.length < MAX_COLUMNS) columns.push(k);
  return { columns, rows: rows.map((r) => columns.map((c) => showValue(r[c]))) };
}

function chartOf(output: unknown, rows: Obj[]): Chart | null {
  if (!isObj(output) || !isObj(output.chart) || !rows.length) return null;
  const { x, y, title } = output.chart;
  if (typeof x !== "string" || typeof y !== "string") return null;
  const bars = rows
    .filter((r) => typeof r[y] === "number" && Number.isFinite(r[y]))
    .map((r) => ({ label: showValue(r[x]), value: r[y] as number, text: showValue(r[y]) }));
  if (!bars.length) return null;
  const max = Math.max(...bars.map((b) => Math.abs(b.value)), 0);
  return { title: typeof title === "string" ? title : `${y} by ${x}`, x, y, bars, max };
}

/** Facts, table, chart and the raw JSON of one analysis output. */
export function analysisView(output: unknown): AnalysisView {
  const rows = rowsOf(output);
  let raw = output === undefined ? "" : JSON.stringify(output, null, 2) ?? "";
  if (raw.length > MAX_RAW) raw = `${raw.slice(0, MAX_RAW)}\n…`;
  return { facts: factsOf(output), table: tableOf(rows), chart: chartOf(output, rows), raw };
}

/** Read an uploaded script as text; refuses files over the 8 KB the server accepts. */
export async function readScriptFile(file: File, maxBytes = 8192): Promise<string | null> {
  if (file.size > maxBytes) return null;
  return file.text();
}

/** A scenario script defines on_step(view, act); anything else is read as an analysis. */
export function guessKind(code: string): "analysis" | "scenario" {
  return /^\s*def\s+on_step\s*\(/m.test(code) ? "scenario" : "analysis";
}

/** A working starting point for a new script of each kind. */
export function starterScript(kind: "analysis" | "scenario", exitId: string | null): string {
  if (kind === "analysis") {
    return `import showtime_data as sd

# The most people waiting within 3 m of each exit during the run
rows = []
for _, e in sd.exits().iterrows():
    q = sd.people_near(e["id"], radius_m=3.0)
    rows.append({"exit": e["name"], "most waiting": int(q["people"].max()) if len(q) else 0})

output = {
    "facts": {"exits": len(rows)},
    "table": rows,
    "chart": {"x": "exit", "y": "most waiting", "title": "Most people waiting near each exit"},
}
`;
  }
  return `# Called every few seconds of simulated time.
# view: t, people and density per zone and exit, open exits, queues (read-only)
# act: close_exit, open_exit, redirect(from, to, fraction), add_people(zone, n),
#      slow_down(factor), note(text)
def on_step(view, act):
    if 60 <= view.t < 61:
        act.close_exit("${exitId ?? "EXIT_ID"}")
        act.note("One minute in, this exit jams")
`;
}
