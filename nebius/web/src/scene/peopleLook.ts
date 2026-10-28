/** How each kind of person looks in a replay: a shape (so colour is never the only signal) and a
 * colour from a colour-blind-safe set that avoids the safety colours (green, amber, red). */
import * as THREE from "three";
import type { PeopleKindId } from "@/replay/kinds";

interface PersonLook {
  /** geometry standing on y = 0 */
  geometry: () => THREE.BufferGeometry;
  /** colour when the venue is drawn in light or dark (null = the palette's agent colour) */
  color: string | null;
  /** SVG path for the legend, in a 16×16 box */
  icon: string;
}

const standing = (g: THREE.BufferGeometry, h: number) => { g.translate(0, h / 2, 0); return g; };

export const PEOPLE_LOOK: Record<PeopleKindId, PersonLook> = {
  // a pill: the default marker
  general: { geometry: () => standing(new THREE.CapsuleGeometry(0.18, 0.72, 2, 10), 1.08), color: null,
             icon: "M6 2h4a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" },
  elderly: { geometry: () => standing(new THREE.CylinderGeometry(0.22, 0.22, 0.9, 6), 0.9), color: "#CC79A7",
             icon: "M8 1.5l5.5 3.2v6.6L8 14.5l-5.5-3.2V4.7z" },
  child: { geometry: () => standing(new THREE.SphereGeometry(0.24, 12, 8), 0.48), color: "#56B4E9",
           icon: "M8 3.5a4.5 4.5 0 1 1 0 9a4.5 4.5 0 1 1 0-9z" },
  // a wheel standing on edge
  wheelchair: { geometry: () => { const g = new THREE.TorusGeometry(0.34, 0.09, 8, 18); return standing(g, 0.86); }, color: "#0072B2",
                icon: "M8 2a6 6 0 1 1 0 12A6 6 0 1 1 8 2zm0 3a3 3 0 1 0 0 6a3 3 0 1 0 0-6z" },
  bed: { geometry: () => standing(new THREE.BoxGeometry(1.9, 0.5, 0.9), 0.5), color: "#E8D44D",
         icon: "M1 6h14v5H1z" },
  staff: { geometry: () => standing(new THREE.BoxGeometry(0.36, 1.15, 0.36), 1.15), color: "#7E57C2",
           icon: "M4 4h8v8H4z" },
};
