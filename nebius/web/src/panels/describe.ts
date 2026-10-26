/** Plain-language labels for scenario events and edit operations. */
import { t } from "@/i18n";
import { fmtClock, fmtInt } from "@/lib/format";

type Dict = Record<string, unknown>;

/** A side of the venue ("east") in the reader's words; unknown values are shown as they are. */
export const sideName = (side: string) => {
  const name = t(`describe.side.${side}`);
  return name.startsWith("describe.") ? side : name;
};

export function describeEvent(e: Dict, label: (id: string) => string): string {
  const atS = Number(e.at_s ?? 0);
  const id = (k: string) => label(String(e[k] ?? ""));
  const what = (() => {
    switch (e.type) {
      case "block_exit": return t("describe.ev_block", { exit: id("exit_id") });
      case "unblock_exit": return t("describe.ev_unblock", { exit: id("exit_id") });
      case "surge": return t("describe.ev_surge", { n: fmtInt(Number(e.extra_people)), zone: id("zone_id") });
      case "slowdown": return t("describe.ev_slow", { p: Math.round(Number(e.factor) * 100) });
      case "counterflow": return t("describe.ev_counter", { n: fmtInt(Number(e.people)), exit: id("exit_id") });
      case "staggered_release": return t("describe.ev_hold", { zone: id("zone_id"), s: Math.round(Number(e.delay_s)) });
      case "marshal_redirect": {
        const p = Math.round(Number(e.fraction ?? 0.5) * 100);
        return e.from_exit_id ? t("describe.ev_marshal_from", { p, from: id("from_exit_id"), to: id("to_exit_id") }) : t("describe.ev_marshal", { p, to: id("to_exit_id") });
      }
      case "one_way": return t("describe.ev_one_way", { exit: id("exit_id") });
      case "script": return e.title ? t("describe.ev_script_titled", { title: String(e.title) }) : t("describe.ev_script");
      default: return String(e.type);
    }
  })();
  // a hold and a one-way rule last the whole run; other events happen at a time
  const timed = !["staggered_release", "one_way", "script"].includes(String(e.type));
  return timed && atS > 0 ? t("describe.at", { what, time: fmtClock(atS) }) : what;
}

export function describeOp(o: Dict, label: (id: string) => string): string {
  const name = (k: string) => label(String(o[k]));
  switch (o.op) {
    case "add_exit": return o.wall ? t("describe.op_add_exit_wall", { w: String(o.width_m), wall: sideName(String(o.wall)) }) : t("describe.op_add_exit", { w: String(o.width_m) });
    case "resize": return t("describe.op_resize", { name: name("target"), w: String(o.width_m) });
    case "add_barrier_line": return t("describe.op_barrier");
    case "move": return t("describe.op_move", { name: name("target") });
    case "remove_obstacle": return t("describe.op_remove", { name: name("obstacle_id") });
    case "block_exit": return t(o.blocked === false ? "describe.op_open" : "describe.op_close", { name: name("exit_id") });
    case "set_people": return t("describe.op_people", { name: name("zone_id"), n: fmtInt(Number(o.people)) });
    default: return String(o.op);
  }
}
