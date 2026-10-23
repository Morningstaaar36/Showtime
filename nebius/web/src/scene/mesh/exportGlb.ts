/** Download the venue as a 3D model (.glb, binary glTF 2.0): opens in Blender or any 3D or BIM
 * viewer. Built from the same mesh generation as the live 3D view. */
import * as THREE from "three";
import { GLTFExporter } from "three/examples/jsm/exporters/GLTFExporter.js";
import type { Venue } from "@/api/types";
import { LIGHT_PALETTE } from "../palette";
import { buildVenueModel, disposeModel } from "./building";

/** The venue as GLB bytes. */
export async function venueGlb(venue: Venue): Promise<ArrayBuffer> {
  const scene = new THREE.Scene();
  scene.name = venue.name || "Venue";
  const model = buildVenueModel(venue, LIGHT_PALETTE);
  scene.add(model);
  try {
    const out = await new GLTFExporter().parseAsync(scene, { binary: true, onlyVisible: true });
    if (!(out instanceof ArrayBuffer)) throw new Error("The 3D model could not be written.");
    return out;
  } finally {
    disposeModel(model);
  }
}

/** "City hospital · 4 floors" -> "city-hospital-4-floors.glb" */
export function glbFileName(name: string): string {
  const slug = name.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase()
    .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80);
  return `${slug || "venue"}.glb`;
}

/** Build the model and hand it to the browser as a download. */
export async function downloadVenueGlb(venue: Venue, name: string): Promise<void> {
  const bytes = await venueGlb(venue);
  const url = URL.createObjectURL(new Blob([bytes], { type: "model/gltf-binary" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = glbFileName(name);
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
