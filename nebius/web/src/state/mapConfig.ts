/** The browser's map settings, sent by the server (GET /health → client.map): the place picker's
 * style, the raster tiles under the 3D view and where the picker opens. A zustand store, so the
 * 3D canvas reads it too. Empty until the server answers. */
import { create } from "zustand";

export interface MapConfig {
  style_url: string;
  raster_tiles_url: string;
  start: { lat: number; lon: number; zoom: number };
}

export const useMapConfig = create<{ config: MapConfig | null; set: (c: MapConfig | null | undefined) => void }>((set) => ({
  config: null,
  set: (c) => { if (c) set({ config: c }); },
}));

/** A raster tile URL from a "{z}/{x}/{y}" template. */
export function tileUrl(template: string, z: number, x: number, y: number): string {
  return template.replace("{z}", String(z)).replace("{x}", String(x)).replace("{y}", String(y));
}
