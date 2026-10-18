/** Follows a red-team session's SSE stream and folds events into view state. */
import { useEffect, useReducer, useRef } from "react";
import { reconnectDelay } from "./reconnect";
import type { FailureMap } from "@/types/generated";
import type { Attack, Countdown, Fix, SessionEvent } from "./types";

export interface RunInfo {
  run_id: string;
  node_id?: string;
  status: string;
  tier: number;
  provider?: string;
  engine?: string;
  metrics: Record<string, number | null>;
  is_break: boolean;
  break_reasons: string[];
  accepted?: boolean | null;
}

export interface TreeNode {
  node_id: string;
  parent_id: string | null;
  kind: "baseline" | "attack" | "fix" | "final";
  label: string;
  run_id: string;
  status: "pending" | "running" | "break" | "ok" | "failed" | "rejected";
  attack_id?: string | null;
  fix_id?: string | null;
  accepted?: boolean;
  gain?: number;
  metrics?: Record<string, number | null>;
}

export interface AgentLine {
  seq: number;
  ts: string;
  type: "agent_call" | "tool_call" | "log";
  agent?: string;
  model?: string;
  summary: string;
  tokens?: number;
  ms?: number;
  ok?: boolean;
  level?: string;
}

export interface SessionView {
  lastSeq: number;
  status: string;
  phase: string;
  /** every phase entered, with the time it started (for step durations) */
  phases: { phase: string; ts: string }[];
  round: number;
  message: string;
  /** cell = the failure-map cell (hazard kind × where) the attack lands in */
  attacks: { attack: Attack; round: number; tier1: Record<string, number | null>; cell?: { kind: string; where: string } | null }[];
  fixes: { fix: Fix; round: number; attack_id: string }[];
  nodes: Record<string, TreeNode>;
  runs: Record<string, RunInfo>;
  scoreboard: { round: number; breaks: number; attacks: number; coverage?: number; qd_score?: number }[];
  fixesAccepted: number;
  cost: { tokens_total: number; cost_usd: number; budget_tokens: number } | null;
  feed: AgentLine[];
  countdown: Countdown | null;
  /** the red team's failure map (latest `archive` event; docs/RAINBOW.md) */
  archive: FailureMap | null;
  connected: boolean;
  ended: boolean;
}

export const EMPTY: SessionView = {
  lastSeq: 0, status: "queued", phase: "", phases: [], round: 0, message: "", attacks: [], fixes: [], nodes: {},
  runs: {}, scoreboard: [], fixesAccepted: 0, cost: null, feed: [], countdown: null, archive: null, connected: false,
  ended: false,
};

export type Action = { kind: "event"; ev: SessionEvent } | { kind: "reset" } | { kind: "conn"; v: boolean } | { kind: "end" };

/** Folds one stream action into the view (exported for tests). */
export function reduce(s: SessionView, a: Action): SessionView {
  if (a.kind === "reset") return EMPTY;
  if (a.kind === "conn") return { ...s, connected: a.v };
  if (a.kind === "end") return { ...s, ended: true, connected: false };
  const ev = a.ev;
  if (ev.seq <= s.lastSeq) return s;
  const p = ev.payload as Record<string, unknown>;
  const next: SessionView = { ...s, lastSeq: ev.seq };
  switch (ev.type) {
    case "status":
      next.status = String(p.status);
      next.phase = String(p.phase);
      if (s.phases[s.phases.length - 1]?.phase !== next.phase) next.phases = [...s.phases, { phase: next.phase, ts: ev.ts }];
      next.round = Number(p.round ?? 0);
      next.message = String(p.message ?? "");
      break;
    case "attack_card":
      next.attacks = [...s.attacks, { attack: p.attack as Attack, round: Number(p.round), tier1: (p.tier1 ?? {}) as Record<string, number | null>,
        cell: (p.cell ?? null) as SessionView["attacks"][number]["cell"] }];
      break;
    case "fix_card":
      next.fixes = [...s.fixes, { fix: p.fix as Fix, round: Number(p.round), attack_id: String(p.attack_id) }];
      break;
    case "branch_node": {
      const id = String(p.node_id);
      next.nodes = { ...s.nodes, [id]: { ...(s.nodes[id] ?? {}), ...(p as unknown as TreeNode) } };
      break;
    }
    case "run_finished":
      next.runs = { ...s.runs, [String(p.run_id)]: p as unknown as RunInfo };
      break;
    case "score":
      next.scoreboard = (p.scoreboard as SessionView["scoreboard"]) ?? s.scoreboard;
      next.fixesAccepted = Number(p.fixes_accepted ?? s.fixesAccepted);
      break;
    case "cost":
      next.cost = p as unknown as SessionView["cost"];
      break;
    case "archive":
      if (p.archive && Array.isArray((p.archive as FailureMap).cells)) next.archive = p.archive as FailureMap;
      break;
    case "countdown":
      next.countdown = p.countdown as Countdown;
      break;
    case "agent_call":
      next.feed = [...s.feed, { seq: ev.seq, ts: ev.ts, type: "agent_call" as const, agent: String(p.agent), model: String(p.model ?? ""),
        summary: String(p.summary ?? ""), tokens: Number(p.tokens_in ?? 0) + Number(p.tokens_out ?? 0), ms: Number(p.ms ?? 0), ok: Boolean(p.ok) }].slice(-200);
      break;
    case "tool_call":
      next.feed = [...s.feed, { seq: ev.seq, ts: ev.ts, type: "tool_call" as const, agent: String(p.tool), summary: String(p.summary ?? "") }].slice(-200);
      break;
    case "log":
      next.feed = [...s.feed, { seq: ev.seq, ts: ev.ts, type: "log" as const, summary: String(p.message ?? ""), level: String(p.level ?? "info") }].slice(-200);
      break;
    default:
      break;
  }
  return next;
}

/** Subscribe to /sessions/{id}/events; reconnects from the last seen event. */
export function useSessionStream(sessionId: string | null | undefined): SessionView {
  const [state, dispatch] = useReducer(reduce, EMPTY);
  const lastSeq = useRef(0);
  lastSeq.current = state.lastSeq;

  useEffect(() => {
    dispatch({ kind: "reset" });
    lastSeq.current = 0;
    if (!sessionId) return;
    let es: EventSource | null = null;
    let closed = false;
    let retry: number | undefined;
    let failures = 0;
    const open = () => {
      es = new EventSource(`/api/v1/sessions/${sessionId}/events?after=${lastSeq.current}`);
      es.onopen = () => { failures = 0; dispatch({ kind: "conn", v: true }); };
      es.onmessage = (m) => {
        failures = 0;
        try {
          dispatch({ kind: "event", ev: JSON.parse(m.data) as SessionEvent });
        } catch {
          /* ignore malformed lines */
        }
      };
      es.addEventListener("end", () => {
        closed = true;
        es?.close();
        dispatch({ kind: "end" });
      });
      es.onerror = () => {
        es?.close();
        dispatch({ kind: "conn", v: false });
        const wait = closed ? null : reconnectDelay(++failures);
        if (wait != null) retry = window.setTimeout(open, wait);
      };
    };
    open();
    return () => {
      closed = true;
      if (retry) window.clearTimeout(retry);
      es?.close();
    };
  }, [sessionId]);
  return state;
}
