/** Which objects get a 3D label. Stacked floors would print every storey's labels on top of each
 * other, and a big site would bury its exits under hundreds of names, so labels follow the floor in
 * view and a budget per kind (exits first: they are what an organizer checks). */
import type { Floor, Venue } from "@/api/types";
import { floorsBottomUp, polygonArea } from "./geom";

interface LabelBudget { exits: number; zones: number; features: number }

const LABEL_BUDGET: LabelBudget = { exits: 30, zones: 16, features: 10 };
/** Below this many labelled objects nothing is dropped. */
const LABEL_DECLUTTER_FROM = 40;
/** A phone screen holds far fewer names before they overlap: the widest exits and biggest crowds. */
export const PHONE_LABELS = { budget: { exits: 8, zones: 5, features: 3 } as LabelBudget, from: 12 };
/** Stacked views with this many floors label one floor at a time. */
const STACKED_FROM = 3;

const generic = (label: string | null | undefined) => /^building \d+$/i.test(label ?? "");

/** Ids allowed a label, or null for "all". `view` is the resolved floor view; `focusFloor` is the
 * floor whose labels show when several floors are stacked ("all"). */
export function labelledIds(venue: Venue, view: string, focusFloor: string | null, budget: LabelBudget = LABEL_BUDGET,
  declutterFrom: number = LABEL_DECLUTTER_FROM): Set<string> | null {
  // two floors (a hall and its mezzanine) read fine; from three storeys up the names of every
  // floor pile on top of each other, stacked or spread apart, so only the focus floor keeps its
  // labels (and every exit)
  const stacked = (view === "all" || view === "exploded") && venue.floors.length >= STACKED_FROM;
  const focus = venue.floors.some((f) => f.floor_id === focusFloor) ? focusFloor : floorsBottomUp(venue)[0]?.floor_id;
  const floors = stacked ? venue.floors.filter((f) => f.floor_id === focus)
    : view === "all" || view === "exploded" ? venue.floors : venue.floors.filter((f) => f.floor_id === view);
  const exits = (stacked ? venue.floors : floors).flatMap((f) => f.exits);
  const zones = floors.flatMap((f) => f.zones);
  const features = floors.flatMap((f) => f.obstacles.filter((o) => o.kind !== "wall" && !generic(o.label)));
  const total = exits.length + zones.length + features.length;
  if (!stacked && total < declutterFrom) return null;
  if (total < declutterFrom) return new Set([...exits, ...zones, ...features].map((x) => x.id).concat(stairIds(venue, floors)));
  const top = <T,>(xs: T[], n: number, key: (x: T) => number) => [...xs].sort((a, b) => key(b) - key(a)).slice(0, n);
  return new Set([
    ...top(exits, budget.exits, (e) => e.width_m),
    ...top(zones, budget.zones, (z) => z.people),
    ...top(features, budget.features, (o) => polygonArea(o.polygon)),
  ].map((x) => x.id).concat(stairIds(venue, floors)));
}

const stairIds = (venue: Venue, floors: Floor[]) => {
  const ids = new Set(floors.map((f) => f.floor_id));
  return (venue.stairs ?? []).filter((s) => ids.has(s.from_floor) || ids.has(s.to_floor)).map((s) => s.id);
};
