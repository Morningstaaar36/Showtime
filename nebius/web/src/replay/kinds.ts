/** Who each simulated person is (GET /runs/{id}/agents): `{"schema": 1, "kinds": {"<agent
 * id>": "<kind>"}}`, listing only people who are not general adults. Agent ids are the uint16 ids
 * of traj.bin, so a flat lookup table answers "what kind is agent i" in the frame loop. */

/** Kind codes, in legend order. 0 = general adults (everyone not listed). */
export const PEOPLE_KINDS = ["general", "elderly", "child", "wheelchair", "bed", "staff"] as const;
export type PeopleKindId = (typeof PEOPLE_KINDS)[number];

export interface AgentKinds {
  /** code per agent id (index into PEOPLE_KINDS) */
  lookup: Uint8Array;
  /** people listed per kind (general = not counted here; the trajectory knows the total) */
  listed: Record<PeopleKindId, number>;
}

const CODE = new Map<string, number>(PEOPLE_KINDS.map((k, i) => [k, i]));

/** Parses the endpoint's answer; null when nobody is other than a general adult (or the answer is
 * malformed or from an older run), so the replay keeps its plain look. */
export function parseAgentKinds(raw: unknown): AgentKinds | null {
  if (!raw || typeof raw !== "object") return null;
  const kinds = (raw as { kinds?: unknown }).kinds;
  if (!kinds || typeof kinds !== "object") return null;
  const lookup = new Uint8Array(65536);
  const listed = Object.fromEntries(PEOPLE_KINDS.map((k) => [k, 0])) as Record<PeopleKindId, number>;
  let any = false;
  for (const [id, kind] of Object.entries(kinds as Record<string, unknown>)) {
    const n = Number(id);
    const code = typeof kind === "string" ? CODE.get(kind) : undefined;
    if (!Number.isInteger(n) || n < 0 || n > 65535 || code == null || code === 0) continue;
    lookup[n] = code;
    listed[PEOPLE_KINDS[code]] += 1;
    any = true;
  }
  return any ? { lookup, listed } : null;
}

/** Kinds present in a run, in legend order (general adults first when anyone else is listed). */
export function kindsPresent(k: AgentKinds | null): PeopleKindId[] {
  if (!k) return [];
  return PEOPLE_KINDS.filter((id) => id === "general" || k.listed[id] > 0);
}
