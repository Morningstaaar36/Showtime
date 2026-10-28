/** Real surroundings for venues imported from the map: street-map ground tiles and the
 *  neighbouring buildings at their mapped heights. Drawn only; never part of the simulation. */
import { useEffect, useMemo, useState } from "react";
import * as THREE from "three";
import { tileUrl, useMapConfig } from "@/state/mapConfig";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import type { Pt, Venue } from "@/api/types";
import { centroid, pointInPolygon, shapeOf, venueBounds } from "./geom";
import type { ScenePalette } from "./palette";

interface OsmSite {
  origin: [number, number]; // lat0, lon0
  scale: [number, number]; // metres per degree lon, lat
  context?: { polygon: Pt[]; height_m: number; name?: string }[];
}

/** The site info stored on venues imported from OpenStreetMap (null otherwise). */
export function osmSite(venue: Venue): OsmSite | null {
  const o = (venue.extensions as Record<string, unknown> | undefined)?.osm as OsmSite | undefined;
  return o && Array.isArray(o.origin) && Array.isArray(o.scale) ? o : null;
}

const lon2x = (lon: number, z: number) => ((lon + 180) / 360) * 2 ** z;
const lat2y = (lat: number, z: number) => ((1 - Math.asinh(Math.tan((lat * Math.PI) / 180)) / Math.PI) / 2) * 2 ** z;
const x2lon = (x: number, z: number) => (x / 2 ** z) * 360 - 180;
const y2lat = (y: number, z: number) => (Math.atan(Math.sinh(Math.PI * (1 - (2 * y) / 2 ** z))) * 180) / Math.PI;

interface Tile { key: string; url: string; x0: number; x1: number; y0: number; y1: number }

function tilesFor(site: OsmSite, venue: Venue, template: string): Tile[] {
  const [lat0, lon0] = site.origin;
  const [kx, ky] = site.scale;
  const [bx0, by0, bx1, by1] = venueBounds(venue);
  const margin = Math.max(150, Math.max(bx1 - bx0, by1 - by0) * 0.6);
  const w = lon0 + (bx0 - margin) / kx, e = lon0 + (bx1 + margin) / kx;
  const s = lat0 + (by0 - margin) / ky, n = lat0 + (by1 + margin) / ky;
  for (let z = 18; z >= 14; z--) {
    const tx0 = Math.floor(lon2x(w, z)), tx1 = Math.floor(lon2x(e, z));
    const ty0 = Math.floor(lat2y(n, z)), ty1 = Math.floor(lat2y(s, z));
    if ((tx1 - tx0 + 1) * (ty1 - ty0 + 1) > 64) continue;
    const out: Tile[] = [];
    for (let x = tx0; x <= tx1; x++) {
      for (let y = ty0; y <= ty1; y++) {
        out.push({
          key: `${z}/${x}/${y}`,
          url: tileUrl(template, z, x, y), // the configured raster tiles (MAP_RASTER_TILES_URL)
          x0: (x2lon(x, z) - lon0) * kx, x1: (x2lon(x + 1, z) - lon0) * kx,
          y0: (y2lat(y + 1, z) - lat0) * ky, y1: (y2lat(y, z) - lat0) * ky,
        });
      }
    }
    return out;
  }
  return [];
}

function MapTile({ tile, dark }: { tile: Tile; dark: boolean }) {
  const [tex, setTex] = useState<THREE.Texture | null>(null);
  useEffect(() => {
    let alive = true;
    const loader = new THREE.TextureLoader();
    loader.setCrossOrigin("anonymous");
    loader.load(tile.url, (t) => {
      if (!alive) { t.dispose(); return; }
      t.colorSpace = THREE.SRGBColorSpace;
      t.anisotropy = 4;
      setTex(t);
    }, undefined, () => { /* offline: the plain ground stays */ });
    return () => { alive = false; };
  }, [tile.url]);
  useEffect(() => () => { tex?.dispose(); }, [tex]);
  if (!tex) return null;
  const w = tile.x1 - tile.x0, h = tile.y1 - tile.y0;
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[(tile.x0 + tile.x1) / 2, -0.025, -(tile.y0 + tile.y1) / 2]} receiveShadow>
      <planeGeometry args={[w + 0.05, h + 0.05]} />
      <meshStandardMaterial map={tex} roughness={1} metalness={0} color={dark ? "#4a545c" : "#f3f5f7"} />
    </mesh>
  );
}

/** Does a mapped building stand on the venue itself (its own footprint, drawn again by the map)? */
function onVenue(polygon: Pt[], venue: Venue): boolean {
  const rings = venue.floors.map((f) => f.walkable as Pt[]);
  const [cx, cy] = centroid(polygon);
  return rings.some((r) => pointInPolygon(cx, cy, r) || polygon.some(([x, y]) => pointInPolygon(x, y, r)));
}

function Neighbours({ site, venue, palette }: { site: OsmSite; venue: Venue; palette: ScenePalette }) {
  const geo = useMemo(() => {
    const parts: THREE.BufferGeometry[] = [];
    for (const b of site.context ?? []) {
      if (!b.polygon || b.polygon.length < 3 || onVenue(b.polygon, venue)) continue;
      const g = new THREE.ExtrudeGeometry(shapeOf(b.polygon), { depth: Math.max(2.5, b.height_m), bevelEnabled: false });
      g.rotateX(-Math.PI / 2);
      parts.push(g.index ? g.toNonIndexed() : g);
    }
    if (!parts.length) return null;
    const merged = mergeGeometries(parts, false);
    parts.forEach((p) => p.dispose());
    return merged;
  }, [site, venue]);
  useEffect(() => () => geo?.dispose(), [geo]);
  if (!geo) return null;
  return (
    <mesh geometry={geo} castShadow receiveShadow>
      <meshStandardMaterial color={palette.dark ? "#3a4650" : "#d4dbe0"} roughness={0.9} transparent opacity={0.72} depthWrite={false} />
    </mesh>
  );
}

/** Ground map and neighbours for a map-imported venue; nothing for other venues. */
export function SiteContext({ venue, palette, show }: { venue: Venue; palette: ScenePalette; show: { map: boolean; neighbours: boolean } }) {
  const site = osmSite(venue);
  const template = useMapConfig((s) => s.config?.raster_tiles_url ?? null);
  const tiles = useMemo(() => (site && template ? tilesFor(site, venue, template) : []), [site, venue, template]);
  if (!site) return null;
  return (
    <group>
      {show.map && tiles.map((t) => <MapTile key={t.key} tile={t} dark={palette.dark} />)}
      {show.neighbours && <Neighbours site={site} venue={venue} palette={palette} />}
    </group>
  );
}
