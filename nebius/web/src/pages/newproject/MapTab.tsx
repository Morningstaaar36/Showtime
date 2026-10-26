import "maplibre-gl/dist/maplibre-gl.css";
import * as maplibregl from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { Building2, Loader2, MapPin, Minus, MousePointerClick, Plus, Search, Square, Trees } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { api } from "@/api/client";
import { useVenueFromMap } from "@/api/queries";
import type { OsmFeature, Place, VenueDraft } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { ErrorState } from "@/components/ui/states";
import { t } from "@/i18n";
import { useEventKinds } from "@/lib/eventKinds";
import { cn } from "@/lib/utils";
import { DraftPreview } from "./DraftPreview";

/** "Include the surroundings": how far around the building (G2-06 accepts 0–200 m). */
const SURROUND_DEFAULT_M = 50;
const SURROUND_MAX_M = 200;

// MapLibre 6 loads its tile worker from a separate module; Vite bundles it and gives the URL.
maplibregl.setWorkerUrl(workerUrl);

type LatLon = [number, number];
interface Selection {
  id: string | null;
  name: string;
  outline: LatLon[];
  kind: "building" | "area" | "box";
  /** buildings: storeys and use from the map, when it lists them */
  levels?: number | null;
  use?: string | null;
}

const MAX_LEVELS = 40;
const SELECT_CLS = "h-9 rounded-[var(--radius-control)] border border-border bg-surface px-2 text-sm";

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
  const [levels, setLevels] = useState(1);
  const [use, setUse] = useState(""); // "" = guess from the map
  const [interior, setInterior] = useState<"" | "open" | "rooms">(""); // "" = usual for the use
  const [eventKind, setEventKind] = useState("");
  const [surround, setSurround] = useState(false);
  const [surroundM, setSurroundM] = useState(SURROUND_DEFAULT_M);
  const { kinds } = useEventKinds();
  const [mapError, setMapError] = useState<string | null>(null);
  const [found, setFound] = useState(false); // the map shows the searched place
  const build = useVenueFromMap();

  const select = (s: Selection) => {
    lookSeq.current += 1;
    setSel(s);
    setMode(s.kind === "building" ? "indoor" : "outdoor");
    setLevels(s.levels ?? 1);
    setUse(s.use ?? "");
    setInterior("");
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
        toast.message(t("ui.maptab.nothing_is_mapped_exactly_here"));
        return;
      }
      const fallback = f.kind === "building" ? "Building" : f.tags.leisure ?? f.tags.amenity ?? f.tags.landuse ?? "Open area";
      select({ id: f.id, name: f.name || fallback.charAt(0).toUpperCase() + fallback.slice(1), kind: f.kind as "building" | "area",
               outline: f.coords, levels: f.levels ?? null, use: f.use ?? null });
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
      if (!r.length) toast.message(t("ui.maptab.no_place_found_try_a"));
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
      { outline: sel.outline, mode,
        // a drawn box has no map name: call it what it is used as, when that is chosen
        name: sel.kind === "box" && mode === "indoor" && use ? kinds.find((k) => k.id === use)?.label ?? sel.name : sel.name, people: people.trim() && Number.isFinite(n) ? Math.round(n) : null, selected_id: sel.id,
        ...(mode === "indoor"
          ? { levels, use: use || null, interior: interior || null, ...(surround ? { surroundings_m: surroundM } : {}) }
          : { event_kind: eventKind || null }) },
      { onSuccess: (d) => onDraft(d.venue ? d : null) },
    );
  };

  // 1 find, 2 click it, 3 build; 4 means everything is done
  const stage = build.data?.venue ? 4 : sel ? 3 : found ? 2 : 1;
  return (
    <div className="space-y-3">
      {guided && (
        <ol className="grid gap-2 sm:grid-cols-3" aria-label={t("ui.maptab.steps")}>
          {["Find your place", "Click the building or park", "Build your venue"].map((label, i) => (
            <li key={label} aria-current={stage === i + 1 ? "step" : undefined}
                className={cn("flex items-center gap-2 rounded-[var(--radius-control)] border px-3 py-2 text-sm transition",
                  stage === i + 1 ? "border-signal bg-signal-soft font-semibold text-ink" : stage > i + 1 ? "border-egress/40 bg-egress-soft text-ink" : "border-border bg-surface text-muted")}>
              <span className={cn("grid size-6 shrink-0 place-items-center rounded-full text-xs font-bold",
                stage === i + 1 ? "bg-signal text-signal-ink" : stage > i + 1 ? "bg-egress-strong text-on-strong" : "bg-surface-3")}>{stage > i + 1 ? "✓" : i + 1}</span>
              {label}
            </li>
          ))}
        </ol>
      )}
      <div className="relative">
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void search(); }}>
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
            <Input aria-label={t("ui.maptab.search_for_a_place")} placeholder={t("ui.maptab.search_a_place_ramna_park")} value={q}
                   onChange={(e) => setQ(e.target.value)} className="h-11 pl-9 text-base" />
          </div>
          <Button type="submit" variant="primary" disabled={searching || q.trim().length < 2}>{searching ? <Loader2 className="animate-spin" /> : <MapPin />}{t("ui.maptab.find")}</Button>
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
            <p>{mapError} <br /><span className="text-muted">{t("ui.maptab.search_still_works_and_you")}</span></p>
          </div>
        )}
        <div className="absolute left-2.5 top-2.5 flex flex-wrap gap-1.5">
          <span className="inline-flex h-8 items-center gap-1.5 rounded-[var(--radius-control)] border border-border bg-surface/95 px-2.5 text-xs shadow-sm">
            {looking ? <Loader2 className="size-3.5 animate-spin text-signal" /> : <MousePointerClick className="size-3.5 text-signal" />}
            {looking ? t("ui.maptab.finding_whats_here") : drawing ? t("ui.maptab.click_the_second_corner") : t("ui.maptab.click_a_building_or_a")}
          </span>
          <Button size="sm" className={cn("bg-surface shadow-sm", drawing && "ring-2 ring-signal")}
                  onClick={() => { corner.current = null; setDrawing((d) => !d); }}>
            <Square />{drawing ? t("ui.maptab.cancel_drawing") : t("ui.maptab.draw_an_area")}
          </Button>
        </div>
      </div>

      {sel ? (
        <div className="grid gap-3 rounded-[var(--radius-panel)] border-2 border-signal/40 bg-surface p-3 shadow-sm sm:flex sm:flex-wrap sm:items-end [&>*:first-child]:min-w-[10rem] [&>*:first-child]:flex-1">
          <div className="min-w-0">
            <p className="text-xs text-muted">{t("ui.maptab.selected")}</p>
            <p className="truncate font-medium">{sel.name}</p>
          </div>
          <div className="grid gap-1">
            <Label>{t("ui.maptab.treat_as")}</Label>
            <div className="inline-flex rounded-[var(--radius-control)] border border-border p-0.5">
              {(["indoor", "outdoor"] as const).map((m) => (
                <button key={m} type="button" onClick={() => setMode(m)}
                        className={cn("inline-flex items-center gap-1 rounded-[4px] px-2.5 py-1 text-xs", mode === m ? "bg-signal text-white" : "text-muted hover:text-ink")}>
                  {m === "indoor" ? <Building2 className="size-3.5" /> : <Trees className="size-3.5" />}
                  {m === "indoor" ? t("ui.maptab.building_indoor") : t("ui.maptab.open_air_area")}
                </button>
              ))}
            </div>
          </div>
          {mode === "indoor" ? (
            <>
              <div className="grid gap-1">
                <Label htmlFor="mfloors">{t("editor.map.floors")}</Label>
                <div className="inline-flex items-center gap-1">
                  <Button variant="secondary" size="icon" aria-label={t("editor.map.fewer")} disabled={levels <= 1}
                          onClick={() => setLevels((n) => Math.max(1, n - 1))}><Minus /></Button>
                  <Input id="mfloors" inputMode="numeric" className="w-14 text-center tabular-nums" value={levels}
                         onChange={(e) => { const n = Number(e.target.value); if (Number.isFinite(n)) setLevels(Math.max(1, Math.min(MAX_LEVELS, Math.round(n)))); }} />
                  <Button variant="secondary" size="icon" aria-label={t("editor.map.more")} disabled={levels >= MAX_LEVELS}
                          onClick={() => setLevels((n) => Math.min(MAX_LEVELS, n + 1))}><Plus /></Button>
                </div>
                <p className="text-[11px] text-muted">{sel.levels ? t("editor.map.floors_from_map") : t("editor.map.floors_not_on_map")}</p>
              </div>
              <div className="grid gap-1">
                <Label htmlFor="muse">{t("editor.map.use")}</Label>
                <select id="muse" className={SELECT_CLS} value={use} onChange={(e) => setUse(e.target.value)}>
                  <option value="">{t("editor.map.use_guess")}</option>
                  {kinds.map((k) => <option key={k.id} value={k.id}>{k.label}</option>)}
                </select>
              </div>
              <div className="grid gap-1">
                <Label htmlFor="minterior">{t("editor.map.interior")}</Label>
                <select id="minterior" className={SELECT_CLS} value={interior} onChange={(e) => setInterior(e.target.value as "" | "open" | "rooms")}>
                  <option value="">{t("editor.map.use_guess")}</option>
                  <option value="rooms">{t("editor.map.interior_rooms")}</option>
                  <option value="open">{t("editor.map.interior_open")}</option>
                </select>
              </div>
              <div className="grid min-w-[14rem] gap-1.5 sm:basis-full" data-testid="surroundings">
                <div className="flex items-center gap-2">
                  <Switch id="msurround" checked={surround} onCheckedChange={setSurround} aria-describedby="msurround-hint" />
                  <Label htmlFor="msurround">{t("editor.map.surroundings")}</Label>
                </div>
                <p id="msurround-hint" className="text-[11px] text-muted">{t("editor.map.surroundings_hint")}</p>
                {surround && (
                  <div className="flex max-w-md items-center gap-3">
                    <span id="msurround-d" className="shrink-0 text-xs text-muted">{t("editor.map.distance")}</span>
                    <Slider min={10} max={SURROUND_MAX_M} step={10} value={[surroundM]} onValueChange={([v]) => setSurroundM(v)}
                            thumbLabel={t("editor.map.distance")} aria-labelledby="msurround-d" />
                    <span className="w-14 shrink-0 text-right text-sm tabular-nums" aria-live="polite">{surroundM} m</span>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="grid gap-1">
              <Label htmlFor="mevent">{t("editor.map.event")}</Label>
              <select id="mevent" className={SELECT_CLS} value={eventKind} onChange={(e) => setEventKind(e.target.value)}>
                <option value="">{t("editor.kinds.none")}</option>
                {kinds.map((k) => <option key={k.id} value={k.id}>{k.label}</option>)}
              </select>
            </div>
          )}
          <div className="grid gap-1">
            <Label htmlFor="mpeople">{t("ui.maptab.people_optional")}</Label>
            <Input id="mpeople" inputMode="numeric" placeholder={t("ui.maptab.auto")} value={people} onChange={(e) => setPeople(e.target.value)} className="w-28" />
          </div>
          <Button variant="primary" size="lg" disabled={build.isPending} onClick={make}>
            {build.isPending ? <Loader2 className="animate-spin" /> : null}{build.isPending ? t("ui.maptab.building") : t("ui.maptab.build_venue")}
          </Button>
        </div>
      ) : (
        <p className="text-xs text-muted">
          {t("ui.maptab.how_to_pick")} {t("ui.maptab.or")} <b>{t("ui.maptab.draw_an_area")}</b> {t("ui.maptab.draw_how")} {t("ui.maptab.attribution")}
        </p>
      )}

      {build.isError && (
        <ErrorState title={t("ui.maptab.the_venue_couldnt_be_built")} message={(build.error as Error).message}
                    hint={(build.error as { hint?: string }).hint} onRetry={make} />
      )}
      {build.data?.venue && <DraftPreview draft={build.data} surroundingsAsked={mode === "indoor" && surround ? surroundM : 0} />}
    </div>
  );
}
