/** Plain-language labels for scenario events and edit operations. */
import { fmtClock } from "@/lib/format";

type Dict = Record<string, unknown>;

export function describeEvent(e: Dict, label: (id: string) => string): string {
  const t = Number(e.at_s ?? 0);
  const at = t > 0 ? ` at ${fmtClock(t)}` : "";
  const id = (k: string) => label(String(e[k] ?? ""));
  switch (e.type) {
    case "block_exit": return `${id("exit_id")} blocked${at}`;
    case "unblock_exit": return `${id("exit_id")} reopened${at}`;
    case "surge": return `${Number(e.extra_people).toLocaleString()} more people into ${id("zone_id")}${at}`;
    case "slowdown": return `Everyone slows to ${Math.round(Number(e.factor) * 100)}% speed${at}`;
    case "counterflow": return `${Number(e.people).toLocaleString()} people push in through ${id("exit_id")}${at}`;
    case "staggered_release": return `Hold ${id("zone_id")} for ${Math.round(Number(e.delay_s))} s`;
    case "marshal_redirect": return `Marshals send ${Math.round(Number(e.fraction ?? 0.5) * 100)}% ${e.from_exit_id ? `from ${id("from_exit_id")} ` : ""}to ${id("to_exit_id")}${at}`;
    case "one_way": return `One-way flow at ${id("exit_id")}`;
    case "script": return `Scenario written as code${e.title ? `: ${String(e.title)}` : ""}`;
    default: return String(e.type);
  }
}

export function describeOp(o: Dict, label: (id: string) => string): string {
  switch (o.op) {
    case "add_exit": return `New ${o.width_m} m exit${o.wall ? ` on the ${o.wall} wall` : ""}`;
    case "resize": return `Widen ${label(String(o.target))} to ${o.width_m} m`;
    case "add_barrier_line": return "New barrier line";
    case "move": return `Move ${label(String(o.target))}`;
    case "remove_obstacle": return `Remove ${label(String(o.obstacle_id))}`;
    case "block_exit": return `${o.blocked === false ? "Open" : "Close"} ${label(String(o.exit_id))}`;
    case "set_people": return `${label(String(o.zone_id))}: ${o.people} people`;
    default: return String(o.op);
  }
}
