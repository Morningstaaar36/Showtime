/** Pure helpers of the "Ask or change anything" box: labels, where to go, what-if rows. */
import { BarChart3, CircleHelp, Compass, FlaskConical, type LucideIcon, MessageCircleQuestion, PencilRuler } from "lucide-react";
import { api, ApiError } from "@/api/client";
import type { AskIntent, AskTarget, AskWhatIf, WhatIfParams } from "@/api/queries";
import type { WhatIfOut } from "@/api/types";
import { t } from "@/i18n";
import { fmtDuration, fmtInt, fmtNum } from "@/lib/format";

interface IntentMeta { label: string; icon: LucideIcon; tone: string }

const META: Record<AskIntent, { key: string; icon: LucideIcon; tone: string }> = {
  edit: { key: "ask.intent_edit", icon: PencilRuler, tone: "bg-signal-soft text-signal" },
  question: { key: "ask.intent_question", icon: MessageCircleQuestion, tone: "bg-sky-soft text-sky" },
  what_if: { key: "ask.intent_what_if", icon: FlaskConical, tone: "bg-orange-soft text-orange" },
  analyse: { key: "analyst.intent", icon: BarChart3, tone: "bg-egress-soft text-egress" },
  navigate: { key: "ask.intent_navigate", icon: Compass, tone: "bg-teal-soft text-teal" },
  other: { key: "ask.intent_other", icon: CircleHelp, tone: "bg-pink-soft text-pink" },
};

/** Label, icon and colour of the chip that says how a request was understood. */
export function intentMeta(intent: AskIntent): IntentMeta {
  const m = META[intent];
  return { label: t(m.key), icon: m.icon, tone: m.tone };
}

type NavAction = { kind: "route"; to: string } | { kind: "open"; href: string };

/** Where a navigation request goes: a screen of this project, or the report in a new tab. */
export function navAction(target: AskTarget, projectId: string, sessionId?: string | null): NavAction {
  const q = sessionId ? `?session=${encodeURIComponent(sessionId)}` : "";
  switch (target) {
    case "report":
      return { kind: "open", href: api.url(sessionId ? `/sessions/${sessionId}/report` : `/projects/${projectId}/report`) };
    case "expert": return { kind: "route", to: `/p/${projectId}/expert` };
    case "check": return { kind: "route", to: `/p/${projectId}/describe` };
    case "work": return { kind: "route", to: `/p/${projectId}/work${q}` };
    case "plan": return { kind: "route", to: `/p/${projectId}${q}` };
  }
}

interface WhatIfRow { key: string; label: string; before: string; after: string; worse: boolean }

function evacText(w: WhatIfOut): string {
  const s = w.metrics.evac_time_p95_s;
  if (s != null) return fmtDuration(s);
  const n = w.metrics.agents_not_evacuated ?? 0;
  return n > 0 ? t("ask.still_inside", { n: fmtInt(n) }) : "–";
}

/** The plan as it is next to the what-if, both from the instant estimate (computed in code). */
export function whatIfRows(r: AskWhatIf): WhatIfRow[] {
  const b = r.before;
  const eb = b.metrics.evac_time_p95_s ?? null;
  const ea = r.metrics.evac_time_p95_s ?? null;
  const pb = b.metrics.peak_density_ppm2 ?? 0;
  const pa = r.metrics.peak_density_ppm2 ?? 0;
  return [
    { key: "people", label: t("ask.row_people"), before: fmtInt(b.people), after: fmtInt(r.people), worse: false },
    { key: "evac", label: t("ask.row_evac"), before: evacText(b), after: evacText(r),
      worse: eb != null && (ea == null || ea > eb * 1.05) },
    { key: "peak", label: t("ask.row_peak"), before: t("ask.per_m2", { n: fmtNum(pb, 1) }),
      after: t("ask.per_m2", { n: fmtNum(pa, 1) }), worse: pa > pb + 0.05 },
    { key: "capacity", label: t("ask.row_capacity"), before: fmtInt(b.capacity.safe_people),
      after: fmtInt(r.capacity.safe_people), worse: r.people > r.capacity.safe_people },
    { key: "score", label: t("ask.row_score"), before: fmtInt(b.score.score), after: fmtInt(r.score.score),
      worse: Math.round(r.score.score) < Math.round(b.score.score) },
  ];
}

/** What the what-if changed, in plain words. */
export function whatIfChips(p: WhatIfParams): string[] {
  const chips: string[] = [];
  if (p.crowd_scale !== 1) chips.push(t("ask.chip_crowd", { pct: Math.round(p.crowd_scale * 100) }));
  if (p.weather === "rain") chips.push(t("ask.chip_rain", { pct: Math.round(p.speed_factor * 100) }));
  if (p.weather === "smoke") chips.push(t("ask.chip_smoke", { pct: Math.round(p.speed_factor * 100) }));
  for (const e of p.closed_exits) chips.push(t("ask.chip_closed", { name: e.name }));
  return chips;
}

/** The note shown when the crowd size asked for was outside what the estimate tries. */
export function cappedNote(p: WhatIfParams): string | null {
  if (!p.capped || p.crowd_scale_asked == null) return null;
  return t("ask.chip_capped", { asked: fmtNum(p.crowd_scale_asked, 2).replace(/\.?0+$/, ""), used: String(p.crowd_scale) });
}

export interface AskError { text: string; hint: string | null; intent: AskIntent | null; exits: string[]; unknown: string[] }

/** A failed request in plain words; an unknown exit name comes with the names that exist. */
export function askError(e: unknown): AskError {
  const base: AskError = { text: e instanceof Error ? e.message : String(e), hint: null, intent: null, exits: [], unknown: [] };
  if (!(e instanceof ApiError)) return base;
  const intent = (typeof e.details.intent === "string" ? e.details.intent : null) as AskIntent | null;
  const list = (v: unknown) => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);
  if (e.code === "llm_unavailable" || e.status === 503) {
    const text = intent === "edit" ? t("ask.ai_down_edit") : intent === "question" ? t("ask.ai_down_question")
      : intent === "analyse" ? t("analyst.ai_down") : t("ask.ai_down");
    return { ...base, text, intent };
  }
  if (e.code === "unknown_exit") {
    return { ...base, intent, hint: t("ask.pick_exit"), exits: list(e.details.valid), unknown: list(e.details.unknown) };
  }
  return { ...base, intent, hint: e.hint };
}

/** The request again with an exit that exists in place of the unknown name. */
export function retryWithExit(text: string, unknown: string[], name: string): string {
  for (const u of unknown) {
    const i = u ? text.toLowerCase().indexOf(u.toLowerCase()) : -1;
    if (i >= 0) return text.slice(0, i) + name + text.slice(i + u.length);
  }
  return t("ask.close_exit", { name });
}
