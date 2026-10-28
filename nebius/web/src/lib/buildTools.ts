/** What a click (or Enter) does with each building tool: keep drawing, save ops, or explain why
 * not. Pure, so the editor screens and the tests share one set of rules. The ops come from the
 * tested builders in `venueOps.ts`. */
import type { PatchOpIn, Pt, Venue } from "@/api/types";
import { t } from "@/i18n";
import type { BuildTool } from "@/state/ui";
import {
  addRouteOp, addStairOp, addWallOp, cleanPolyline, type Direction, planDoor, planRoom, roomFromCorners,
  snapPoint, stairEnds,
} from "./venueOps";

export interface BuildOptions {
  wallThickness: number;
  doorWidth: number;
  roomDoorSide: Direction;
  roomDoorWidth: number;
  roomPeople: number | null;
  roomLabel: string;
  stairDirection: Direction;
  stairWidth: number;
  stairRun: number;
  routeWidth: number | null;
  routeLabel: string;
}

export const DEFAULT_BUILD_OPTIONS: BuildOptions = {
  wallThickness: 0.2, doorWidth: 1.0, roomDoorSide: "south", roomDoorWidth: 1.0, roomPeople: null, roomLabel: "",
  stairDirection: "north", stairWidth: 1.5, stairRun: 6, routeWidth: null, routeLabel: "",
};

type ErrorKey =
  | "door_no_wall" | "door_outer_wall" | "door_wall_short" | "room_too_small" | "room_door_wide"
  | "stair_needs_floor" | "route_short" | "wall_short";

export type BuildStep =
  | { kind: "draft"; draft: Pt[] }
  | { kind: "ops"; ops: PatchOpIn[]; message: string }
  | { kind: "error"; error: ErrorKey };

/** Tools that collect corners until Enter, double-click or "Finish". */
export const isPolylineTool = (tool: BuildTool): boolean => tool === "wall" || tool === "route";

const roomName = (o: BuildOptions) => o.roomLabel.trim() || t("editor.msg.room_default");
const routeName = (o: BuildOptions) => o.routeLabel.trim() || t("editor.routes.default");

/** A click at (x, y) on `floorId` with `tool`, given the corners drawn so far. */
export function clickStep(tool: BuildTool, venue: Venue, floorId: string, draft: Pt[], x: number, y: number, o: BuildOptions): BuildStep {
  const floor = venue.floors.find((f) => f.floor_id === floorId);
  if (!floor) return { kind: "draft", draft: [] };
  switch (tool) {
    case "wall":
      return { kind: "draft", draft: cleanPolyline([...draft, snapPoint(floor, x, y)]) };
    case "route":
      return { kind: "draft", draft: cleanPolyline([...draft, [x, y]]) };
    case "door": {
      const plan = planDoor(floor, x, y, o.doorWidth);
      return "error" in plan ? { kind: "error", error: plan.error } : { kind: "ops", ops: [plan.op], message: t("editor.msg.door") };
    }
    case "room": {
      const p = snapPoint(floor, x, y);
      if (!draft.length) return { kind: "draft", draft: [p] };
      return roomStep(floorId, roomFromCorners(draft[0], p), o);
    }
    case "stair":
      return stairStep(venue, floorId, x, y, o);
  }
}

/** Enter, double-click or "Finish": saves the wall or route drawn so far. */
export function finishStep(tool: BuildTool, floorId: string, draft: Pt[], o: BuildOptions): BuildStep | null {
  if (tool === "wall") {
    const op = addWallOp(floorId, draft, { thickness_m: o.wallThickness });
    return op ? { kind: "ops", ops: [op], message: t("editor.msg.wall") } : { kind: "error", error: "wall_short" };
  }
  if (tool === "route") {
    const op = addRouteOp(floorId, draft, { width_m: o.routeWidth, label: o.routeLabel || undefined });
    return op ? { kind: "ops", ops: [op], message: t("editor.msg.route", { name: routeName(o) }) } : { kind: "error", error: "route_short" };
  }
  return null;
}

/** A room from its south-west corner and size (typed, or from two clicks). */
export function roomStep(floorId: string, r: { x: number; y: number; width_m: number; depth_m: number }, o: BuildOptions): BuildStep {
  const plan = planRoom(floorId, r, {
    door_wall: o.roomDoorSide, door_width_m: o.roomDoorWidth, people: o.roomPeople, label: o.roomLabel,
  });
  return "error" in plan ? { kind: "error", error: plan.error } : { kind: "ops", ops: [plan.op], message: t("editor.msg.room", { name: roomName(o) }) };
}

/** Stairs centred at (x, y) on `floorId`, down to the floor below (or up, from the lowest floor). */
export function stairStep(venue: Venue, floorId: string, x: number, y: number, o: BuildOptions): BuildStep {
  const op = addStairOp(venue, floorId, x, y, { direction: o.stairDirection, width_m: o.stairWidth, run_m: o.stairRun });
  return op ? { kind: "ops", ops: [op], message: t("editor.msg.stair") } : { kind: "error", error: "stair_needs_floor" };
}

/** Removes the last corner of a wall or route being drawn. */
export const dropLastPoint = (draft: Pt[]): Pt[] => draft.slice(0, -1);

const DIR: Record<Direction, Pt> = { north: [0, 1], south: [0, -1], east: [1, 0], west: [-1, 0] };

/** Outline of a stairwell centred at (x, y), as the server builds it (`stair_shapes`). */
export function stairWell(x: number, y: number, direction: Direction, width: number, run: number): Pt[] {
  const [ux, uy] = DIR[direction];
  const [nx, ny] = [-uy * width / 2, ux * width / 2];
  const h = run / 2;
  return [[x - ux * h - nx, y - uy * h - ny], [x + ux * h - nx, y + uy * h - ny], [x + ux * h + nx, y + uy * h + ny], [x - ux * h + nx, y - uy * h + ny]];
}

/** The floors a stair placed on `floorId` joins, as display names (for "Connects {from} and {to}"). */
export function stairConnects(venue: Venue, floorId: string, label: (id: string) => string): { from: string; to: string } | null {
  const ends = stairEnds(venue, floorId);
  return ends ? { from: label(ends.from_floor), to: label(ends.to_floor) } : null;
}
