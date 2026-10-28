/** What the editors add before the organizer changes it (a new exit's width, a new crowd's
 * size…) and the largest crowd an input accepts: the server's settings (`effective.editor` and
 * `max_people`), so the page, the agents and the simulator start from the same values. */

export interface EditorDefaults {
  /** a new exit or gate */
  exitWidth: number;
  /** a door cut into an inner wall, or into a new room */
  doorWidth: number;
  /** people placed per m² of a new area */
  zoneDensity: number;
  /** a crowd dragged from the palette */
  crowdPeople: number;
  stairWidth: number;
  stairRun: number;
  wallThickness: number;
  floorHeight: number;
  /** narrower than this is not a way through: the smallest exit, door or passage width */
  minWidth: number;
  /** the most people one run simulates, so no input asks for more */
  maxPeople: number;
}

/** Used only until the settings arrive: the server's defaults (api/core/settings.py). */
const FALLBACK: EditorDefaults = {
  exitWidth: 2, doorWidth: 1, zoneDensity: 2, crowdPeople: 200, stairWidth: 1.5, stairRun: 6,
  wallThickness: 0.2, floorHeight: 3.5, minWidth: 0.6, maxPeople: 8000,
};

/** Editor defaults from the effective settings (`GET /settings`). */
export function editorDefaultsOf(eff: Record<string, unknown>): EditorDefaults {
  const ed = typeof eff.editor === "object" && eff.editor !== null ? (eff.editor as Record<string, unknown>) : {};
  const num = (from: Record<string, unknown>, key: string, fallback: number) => (typeof from[key] === "number" ? (from[key] as number) : fallback);
  return {
    exitWidth: num(ed, "exit_width_m", FALLBACK.exitWidth),
    doorWidth: num(ed, "door_width_m", FALLBACK.doorWidth),
    zoneDensity: num(ed, "zone_density_ppm2", FALLBACK.zoneDensity),
    crowdPeople: num(ed, "crowd_people", FALLBACK.crowdPeople),
    stairWidth: num(ed, "stair_width_m", FALLBACK.stairWidth),
    stairRun: num(ed, "stair_run_m", FALLBACK.stairRun),
    wallThickness: num(ed, "wall_thickness_m", FALLBACK.wallThickness),
    floorHeight: num(ed, "floor_height_m", FALLBACK.floorHeight),
    minWidth: num(ed, "min_width_m", FALLBACK.minWidth),
    maxPeople: num(eff, "max_people", FALLBACK.maxPeople),
  };
}
