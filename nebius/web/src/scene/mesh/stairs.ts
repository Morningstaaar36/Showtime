/** Stairs as built things: where a flight sits, its stepped body with landings, and its rails
 * (closed stringers, posts and a handrail on both sides). */
import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import type { Pt, Stair, Venue } from "@/api/types";
import { floorY, shapeOf, stairProfile, stairRun } from "../geom";
import { dropSlivers, MeshBuilder, type V3 } from "./builder";

const HANDRAIL_M = 0.9;
/** Clearance around a flight where the slab above is cut away. */
const OPENING_MARGIN_M = 0.08;

interface StairPlacement {
  /** foot of the flight (venue metres) and the heading of the climb (radians from east) */
  foot: Pt;
  angle: number;
  run: number;
  rise: number;
  /** world heights of the lower and upper ends */
  yBot: number;
  yTop: number;
  width: number;
  /** floor ids at the upper and lower end */
  upperFloor: string;
  lowerFloor: string;
}

/** Where a stair's flight sits. A basement stair is walked upward: its upper end is on to_floor. */
export function stairPlacement(venue: Venue, stair: Stair, exploded = false): StairPlacement {
  const yFrom = floorY(venue, stair.from_floor, exploded);
  const yTo = floorY(venue, stair.to_floor, exploded);
  const up = yFrom < yTo;
  const [yTop, yBot] = up ? [yTo, yFrom] : [yFrom, yTo];
  const upper = (up ? stair.bottom_polygon : stair.top_polygon) as Pt[];
  const lower = (up ? stair.top_polygon : stair.bottom_polygon) as Pt[];
  const c = stairRun(upper, lower);
  return {
    foot: [c.bx, c.by], angle: c.angle, run: c.run, rise: yTop - yBot, yBot, yTop, width: stair.width_m,
    upperFloor: up ? stair.to_floor : stair.from_floor, lowerFloor: up ? stair.from_floor : stair.to_floor,
  };
}

/** Plan rectangle of a flight (foot to head, across its width plus `margin`), counter-clockwise. */
export function flightFootprint(p: StairPlacement, margin = 0, s0 = 0, s1 = p.run): Pt[] {
  const ux = Math.cos(p.angle), uy = Math.sin(p.angle);
  const nx = -uy, ny = ux; // left of the climb
  const h = p.width / 2 + margin;
  const at = (s: number, k: number): Pt => [p.foot[0] + ux * s + nx * k, p.foot[1] + uy * s + ny * k];
  return [at(s0, -h), at(s1, -h), at(s1, h), at(s0, h)];
}

/** Plan rectangles cut out of a floor's slab so its stairs pass through: every flight whose upper
 * end is on this floor, or that passes this floor's level on the way. */
export function stairOpenings(venue: Venue, floorId: string): Pt[][] {
  const elev = venue.floors.find((f) => f.floor_id === floorId)?.elevation_m ?? 0;
  const out: Pt[][] = [];
  for (const s of venue.stairs ?? []) {
    const p = stairPlacement(venue, s);
    if (p.rise <= 0.3) continue;
    const through = p.upperFloor === floorId || (elev > p.yBot + 0.3 && elev < p.yTop - 0.05);
    if (through) out.push(flightFootprint(p, OPENING_MARGIN_M));
  }
  return out;
}

/** Feet of the flights that start on this floor (the way on up or down), venue metres. */
export function flightFeet(venue: Venue, floorId: string): Pt[] {
  return (venue.stairs ?? []).map((s) => stairPlacement(venue, s)).filter((p) => p.lowerFloor === floorId).map((p) => p.foot);
}

interface StairGeometry {
  /** steps over a soffit, with a landing plate at each end */
  body: THREE.BufferGeometry;
  /** stringers, posts and handrails */
  rails: THREE.BufferGeometry;
}

/** A flight in its own frame: x along the climb (0 at the foot), y up, z across (centred). */
export function stairGeometry(run: number, rise: number, width: number): StairGeometry {
  const flight = new THREE.ExtrudeGeometry(shapeOf(stairProfile(run, rise)), { depth: width, bevelEnabled: false });
  flight.translate(0, 0, -width / 2);
  flight.deleteAttribute("uv");
  dropSlivers(flight);
  const flat = rise <= 0.3;
  const land = new MeshBuilder();
  if (!flat) {
    const depth = Math.min(1.2, Math.max(0.6, width * 0.8));
    // plates x0..x1 along the climb, the flight's width across, 6 cm under to 2 cm over the floor
    const plate = (x0: number, x1: number, y: number) => land.bar([x0, y - 0.02, 0], [x1, y - 0.02, 0], width, 0.08);
    plate(-depth, 0, 0);
    plate(run, run + depth, rise);
  }
  const landing = land.geometry();
  let body: THREE.BufferGeometry = flight;
  if (landing.getAttribute("position").count) {
    flight.clearGroups();
    body = mergeGeometries([flight, landing]) ?? flight;
    if (body !== flight) flight.dispose();
  }
  if (body !== landing) landing.dispose();

  const rails = new MeshBuilder();
  if (!flat) {
    const slope = rise / run;
    const pitch = (x: number) => x * slope + 0.05;
    for (const side of [-1, 1]) {
      const z = side * (width / 2 + 0.03);
      // closed stringer along the pitch line, deep enough to hide the step ends
      rails.bar([0, pitch(0), z], [run, pitch(run), z], 0.05, 0.36);
      // handrail on posts
      const top = (x: number): V3 => [x, pitch(x) + HANDRAIL_M, z];
      rails.bar(top(0), top(run), 0.05);
      const n = Math.max(2, Math.round(run / 1.2) + 1);
      for (let i = 0; i < n; i++) {
        const x = 0.12 + ((run - 0.24) * i) / (n - 1);
        rails.bar([x, pitch(x), z], [x, pitch(x) + HANDRAIL_M, z], 0.035);
      }
    }
  }
  return { body, rails: rails.geometry() };
}
