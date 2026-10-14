import "maplibre-gl/dist/maplibre-gl.css";
import * as maplibregl from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { Building2, Loader2, MapPin, MousePointerClick, Search, Square, Trees } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { useVenueFromMap } from "@/api/queries";
import type { OsmFeature, Place, VenueDraft } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { ErrorState } from "@/components/ui/states";
import { cn } from "@/lib/utils";
import { DraftPreview } from "./DraftPreview";

// MapLibre 6 loads its tile worker from a separate module; Vite bundles it and gives the URL.
maplibregl.setWorkerUrl(workerUrl);

type LatLon = [number, number];
interface Selection { id: string | null; name: string; outline: LatLon[]; kind: "building" | "area" | "box" }

/** OpenFreeMap: free vector tiles with 3D buildings, no key (https://openfreemap.org). */
const STYLE_URL = "https://tiles.openfreemap.org/styles/liberty";
const START: [number, number] = [90.3925, 23.7265]; // BUET, Dhaka (lon, lat)
const SIGNAL = "#5B4FF5";

const toGeo = (ring: LatLon[]) => ring.map(([la, lo]) => [lo, la]);
const emptyFC = { type: "FeatureCollection" as const, features: [] };

/** "Real place": search, click a building or an open area, or draw a box; build a venue from it. */
export function MapTab({ onDraft, mapClassName = "h-[380px]", guided = false }: {
  onDraft: (d: VenueDraft | null) => void;
  /** Height of the map; the full-page place picker makes it much taller. */
  mapClassName?: string;
  /** Show numbered steps (find, click, build) highlighting the one to do now. */
  guided?: boolean;
}) {
  const holder = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const corner = useRef<maplibregl.LngLat | null>(null);
  const drawingRef = useRef(false);
  const lookSeq = useRef(0); // newer clicks, searches, drawings and builds win over a slow lookup
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Place[]>([]);
  const [searching, setSearching] = useState(false);
  const [looking, setLooking] = useState(false);
  const [drawing, setDrawing] = useState(false);
  const [sel, setSel] = useState<Selection | null>(null);
  const [mode, setMode] = useState<"indoor" | "outdoor">("outdoor");
  const [people, setPeople] = useState("");
  const [mapError, setMapError] = useState<string | null>(null);
  const [found, setFound] = useState(false); // the map shows the searched place
  const build = useVenueFromMap();

  const select = (s: Selection) => {
    lookSeq.current += 1;
    setSel(s);
    setMode(s.kind === "building" ? "indoor" : "outdoor");
    build.reset();
    onDraft(null);
  };

  // highlight the selection on the map
  useEffect(() => {
    const m = map.current;
    const src = m?.getSource("selection") as maplibregl.GeoJSONSource | undefined;
    if (!src) return;
    src.setData(sel ? {
      type: "FeatureCollection",
      features: [{ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [toGeo(sel.outline)] } }],
    } : emptyFC);
  }, [sel]);

  useEffect(() => { drawingRef.current = drawing; if (map.current) map.current.getCanvas().style.cursor = drawing ? "crosshair" : ""; }, [drawing]);

  // create the map once
  useEffect(() => {
    if (!holder.current || map.current) return;
    let m: maplibregl.Map;
    try {
      m = new maplibregl.Map({
        container: holder.current, style: STYLE_URL, center: START, zoom: 15.6, pitch: 50, bearing: -17,
        attributionControl: { compact: true },
      });
    } catch (e) {
      setMapError((e as Error).message || "WebGL is not available in this browser.");
      return;
    }
    m.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
    m.on("error", (ev) => { if (String(ev.error?.message ?? "").includes("style")) setMapError("The map style could not load. Check the internet connection."); });
    m.on("load", () => {
      m.addSource("selection", { type: "geojson", data: emptyFC });
      m.addSource("draft-box", { type: "geojson", data: emptyFC });
      // under the labels (the usual place for highlights), above roads, parks and buildings
      const beforeLabels = m.getStyle().layers.find((l) => l.type === "symbol")?.id;
      m.addLayer({ id: "selection-fill", type: "fill", source: "selection", paint: { "fill-color": SIGNAL, "fill-opacity": 0.3 } }, beforeLabels);
      m.addLayer({ id: "selection-line", type: "line", source: "selection", paint: { "line-color": SIGNAL, "line-width": 4 } }, beforeLabels);
      m.addLayer({ id: "draft-box-line", type: "line", source: "draft-box", paint: { "line-color": SIGNAL, "line-width": 3, "line-dasharray": [2, 2] } }, beforeLabels);
    });
    m.on("mousemove", (e) => {
      if (!drawingRef.current || !corner.current) return;
      const a = corner.current, b = e.lngLat;
      (m.getSource("draft-box") as maplibregl.GeoJSONSource | undefined)?.setData({
        type: "FeatureCollection",
        features: [{ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: [[a.lng, a.lat], [b.lng, a.lat], [b.lng, b.lat], [a.lng, b.lat], [a.lng, a.lat]] } }],
      });
    });
    m.on("click", (e) => {
      if (drawingRef.current) {
        if (!corner.current) { corner.current = e.lngLat; return; }
        const a = corner.current, b = e.lngLat;
        corner.current = null;
        setDrawing(false);
        (m.getSource("draft-box") as maplibregl.GeoJSONSource | undefined)?.setData(emptyFC);
        const s = Math.min(a.lat, b.lat), n = Math.max(a.lat, b.lat), w = Math.min(a.lng, b.lng), ea = Math.max(a.lng, b.lng);
        select({ id: null, name: "Selected area", kind: "box", outline: [[s, w], [s, ea], [n, ea], [n, w], [s, w]] });
        return;
      }
      void lookAt(e.lngLat.lat, e.lngLat.lng);
    });
    map.current = m;
    const ro = new ResizeObserver(() => m.resize());
    ro.observe(holder.current);
    return () => { ro.disconnect(); m.remove(); map.current = null; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const lookAt = async (lat: number, lon: number) => {
    const seq = ++lookSeq.current;
    setLooking(true);
    try {
      const r = await api.get<{ selection: OsmFeature | null }>(`/places/at?lat=${lat.toFixed(6)}&lon=${lon.toFixed(6)}`);
      if (seq !== lookSeq.current) return; // the user has moved on
      const f = r.selection;
      if (!f) {
        toast.message("Nothing is mapped exactly here. Click a building or a park, or use “Draw an area”.");
        return;
      }
      const fallback = f.kind === "building" ? "Building" : f.tags.leisure ?? f.tags.amenity ?? f.tags.landuse ?? "Open area";
      select({ id: f.id, name: f.name || fallback.charAt(0).toUpperCase() + fallback.slice(1), kind: f.kind as "building" | "area", outline: f.coords });
    } catch (e) {
      if (seq === lookSeq.current) toast.error((e as Error).message, { description: "You can always use “Draw an area”." });
    } finally {
      if (seq === lookSeq.current) setLooking(false);
    }
  };

  const search = async () => {
    if (q.trim().length < 2) return;
    setSearching(true);
    try {
      const r = await api.get<Place[]>(`/places/search?q=${encodeURIComponent(q.trim())}`);
      setResults(r);
      if (!r.length) toast.message("No place found. Try a fuller address or a nearby landmark.");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSearching(false);
    }
  };

  const goTo = (p: Place) => {
    setResults([]);
    setFound(true);
    const [s, w, n, e] = p.bbox;
    map.current?.fitBounds([[w, s], [e, n]], { maxZoom: 17.5, padding: 40, pitch: 45, duration: 1200 });
    if (p.outline && p.outline.length >= 4) select({ id: null, name: p.name, kind: "area", outline: p.outline });
  };

  const make = () => {
    if (!sel) return;
    lookSeq.current += 1; // a pending click lookup must not replace what is being built
    setLooking(false);
    const n = Number(people.replace(/[, ]/g, ""));
    build.mutate(
      { outline: sel.outline, mode, name: sel.name, people: people.trim() && Number.isFinite(n) ? Math.round(n) : null, selected_id: sel.id },
      { onSuccess: (d) => onDraft(d.venue ? d : null) },
    );
  };

  // 1 find, 2 click it, 3 build; 4 means everything is done
  const stage = build.data?.venue ? 4 : sel ? 3 : found ? 2 : 1;
  return (
    <div className="space-y-3">
      {guided && (
        <ol className="grid gap-2 sm:grid-cols-3" aria-label="Steps">
          {["Find your place", "Click the building or park", "Build your venue"].map((label, i) => (
            <li key={label} aria-current={stage === i + 1 ? "step" : undefined}
                className={cn("flex items-center gap-2 rounded-[var(--radius-control)] border px-3 py-2 text-sm transition",
                  stage === i + 1 ? "border-signal bg-signal-soft font-semibold text-ink" : stage > i + 1 ? "border-egress/40 bg-egress-soft text-ink" : "border-border bg-surface text-muted")}>
              <span className={cn("grid size-6 shrink-0 place-items-center rounded-full text-xs font-bold",
                stage === i + 1 ? "bg-signal text-signal-ink" : stage > i + 1 ? "bg-egress text-white" : "bg-surface-3")}>{stage > i + 1 ? "✓" : i + 1}</span>
              {label}
            </li>
          ))}
        </ol>
      )}
      <div className="relative">
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void search(); }}>
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
            <Input aria-label="Search for a place" placeholder="Search a place: “Ramna Park Dhaka”, “BUET”, an address…" value={q}
                   onChange={(e) => setQ(e.target.value)} className="h-11 pl-9 text-base" />
          </div>
          <Button type="submit" variant="primary" disabled={searching || q.trim().length < 2}>{searching ? <Loader2 className="animate-spin" /> : <MapPin />}Find</Button>
        </form>
        {results.length > 0 && (
          <ul className="absolute inset-x-0 top-full z-20 mt-1 max-h-64 overflow-auto rounded-[10px] border border-border bg-surface p-1 shadow-[var(--shadow-float)]">
            {results.map((r, i) => (
              <li key={i}>
                <button type="button" onClick={() => goTo(r)} className="w-full rounded-[6px] px-3 py-2 text-left text-sm hover:bg-plan">
                  <span className="font-medium">{r.name}</span>
                  <span className="block truncate text-xs text-muted">{r.display_name}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="relative overflow-hidden rounded-[var(--radius-panel)] border border-border shadow-sm">
        <div ref={holder} className={cn(mapClassName, "w-full bg-plan")} />
        {mapError && (
          <div className="absolute inset-0 grid place-items-center bg-surface/90 p-6 text-center text-sm">
            <p>{mapError} <br /><span className="text-muted">Search still works, and you can describe the venue in words instead.</span></p>
          </div>
        )}
        <div className="absolute left-2.5 top-2.5 flex flex-wrap gap-1.5">
          <span className="inline-flex h-8 items-center gap-1.5 rounded-[var(--radius-control)] border border-border bg-surface/95 px-2.5 text-xs shadow-sm">
            {looking ? <Loader2 className="size-3.5 animate-spin text-signal" /> : <MousePointerClick className="size-3.5 text-signal" />}
            {looking ? "Finding what’s here…" : drawing ? "Click the second corner" : "Click a building or a park"}
          </span>
          <Button size="sm" className={cn("bg-surface shadow-sm", drawing && "ring-2 ring-signal")}
                  onClick={() => { corner.current = null; setDrawing((d) => !d); }}>
            <Square />{drawing ? "Cancel drawing" : "Draw an area"}
          </Button>
        </div>
      </div>

      {sel ? (
        <div className="grid gap-3 rounded-[var(--radius-panel)] border-2 border-signal/40 bg-surface p-3 shadow-sm sm:grid-cols-[1fr_auto_auto_auto] sm:items-end">
          <div className="min-w-0">
            <p className="text-xs text-muted">Selected</p>
            <p className="truncate font-medium">{sel.name}</p>
          </div>
          <div className="grid gap-1">
            <Label>Treat as</Label>
            <div className="inline-flex rounded-[var(--radius-control)] border border-border p-0.5">
              {(["indoor", "outdoor"] as const).map((m) => (
                <button key={m} type="button" onClick={() => setMode(m)}
                        className={cn("inline-flex items-center gap-1 rounded-[4px] px-2.5 py-1 text-xs", mode === m ? "bg-signal text-white" : "text-muted hover:text-ink")}>
                  {m === "indoor" ? <Building2 className="size-3.5" /> : <Trees className="size-3.5" />}
                  {m === "indoor" ? "Building (indoor)" : "Open-air area"}
                </button>
              ))}
            </div>
          </div>
          <div className="grid gap-1">
            <Label htmlFor="mpeople">People (optional)</Label>
            <Input id="mpeople" inputMode="numeric" placeholder="auto" value={people} onChange={(e) => setPeople(e.target.value)} className="w-28" />
          </div>
          <Button variant="primary" size="lg" disabled={build.isPending} onClick={make}>
            {build.isPending ? <Loader2 className="animate-spin" /> : null}{build.isPending ? "Building…" : "Build venue"}
          </Button>
        </div>
      ) : (
        <p className="text-xs text-muted">
          Search a place, then click the building (indoor event) or the park, square or campus (open-air event).
          Or <b>Draw an area</b> with two clicks around the part you will use. Map © OpenFreeMap, data © OpenStreetMap contributors.
        </p>
      )}

      {build.isError && (
        <ErrorState title="The venue couldn't be built" message={(build.error as Error).message}
                    hint={(build.error as { hint?: string }).hint} onRetry={make} />
      )}
      {build.data?.venue && <DraftPreview draft={build.data} />}
    </div>
  );
}
