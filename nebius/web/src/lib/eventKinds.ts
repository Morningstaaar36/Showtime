/** Event kinds (GET /event-kinds) with a built-in fallback from en.json, so the picker works
 * against an older server or offline. The API is the source of truth when it answers. */
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { t } from "@/i18n";
import type { PeopleGroup } from "@/types/generated";
import { defaultInterior, EVENT_KINDS, type EventKindId, type Interior } from "./venueOps";

export interface EventKindInfo {
  id: EventKindId;
  label: string;
  description: string;
  default_pre_movement_s: number | null;
  default_groups: PeopleGroup[];
  interior: Interior;
  icon?: string;
}

export function fallbackEventKinds(): EventKindInfo[] {
  return EVENT_KINDS.map((id) => ({
    id,
    label: t(`editor.event.${id}.label`),
    description: t(`editor.event.${id}.description`),
    default_pre_movement_s: null,
    default_groups: [],
    interior: defaultInterior(id),
  }));
}

/** Keeps the server's entries that name a known kind; anything malformed falls back. */
export function parseEventKinds(raw: unknown): EventKindInfo[] | null {
  if (!Array.isArray(raw)) return null;
  const known = new Set<string>(EVENT_KINDS);
  const out: EventKindInfo[] = [];
  for (const r of raw as Partial<EventKindInfo>[]) {
    if (!r || typeof r.id !== "string" || !known.has(r.id)) continue;
    out.push({
      id: r.id,
      label: typeof r.label === "string" && r.label ? r.label : t(`editor.event.${r.id}.label`),
      description: typeof r.description === "string" ? r.description : t(`editor.event.${r.id}.description`),
      default_pre_movement_s: typeof r.default_pre_movement_s === "number" ? r.default_pre_movement_s : null,
      default_groups: Array.isArray(r.default_groups) ? r.default_groups.filter((g) => g && typeof g.share === "number") : [],
      interior: r.interior === "rooms" || r.interior === "open" ? r.interior : defaultInterior(r.id),
      icon: typeof r.icon === "string" ? r.icon : undefined,
    });
  }
  return out.length ? out : null;
}

/** The list of event kinds and whether it came from the server. */
export function useEventKinds(): { kinds: EventKindInfo[]; fromServer: boolean; loading: boolean } {
  const q = useQuery({
    queryKey: ["event-kinds"],
    queryFn: () => api.get<unknown>("/event-kinds"),
    staleTime: Infinity,
    retry: false,
  });
  const parsed = q.data ? parseEventKinds(q.data) : null;
  return { kinds: parsed ?? fallbackEventKinds(), fromServer: !!parsed, loading: q.isLoading };
}

export const peopleKindLabel = (kind: string): string => t(`editor.people.${kind}`);

/** "30% older people, 10% staff" */
export function mixText(groups: PeopleGroup[]): string {
  return groups.filter((g) => g.share > 0).map((g) => `${Math.round(g.share * 100)}% ${peopleKindLabel(g.kind).toLowerCase()}`).join(", ");
}
