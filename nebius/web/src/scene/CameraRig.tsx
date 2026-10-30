/** Orbit camera with smooth fit-to-venue and fly-to-hotspot. */
import { CameraControls } from "@react-three/drei";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type { Venue } from "@/api/types";
import { useUi } from "@/state/ui";
import { floorBounds, floorY, venueBounds } from "./geom";

export function CameraRig({ venue, resetNonce, exploded, focusFloor = null }: {
  venue: Venue; resetNonce: number; exploded: boolean;
  /** one floor in focus: frame that floor at its height (the ghosted storeys stay around it) */
  focusFloor?: string | null;
}) {
  const ref = useRef<CameraControls>(null);
  const flyTo = useUi((s) => s.flyTo);
  const shot = useUi((s) => s.shot);
  // big open-air sites (parks, fields) need to zoom out further than a hall to fit in view
  const maxDistance = useMemo(() => {
    const [x0, y0, x1, y1] = venueBounds(venue);
    return Math.max(700, 2.2 * Math.hypot(x1 - x0, y1 - y0));
  }, [venue]);

  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const focus = focusFloor && venue.floors.some((f) => f.floor_id === focusFloor) ? focusFloor : null;
    const [x0, y0, x1, y1] = focus ? floorBounds(venue, focus) : venueBounds(venue);
    const bottom = focus ? floorY(venue, focus, exploded) : 0;
    const top = focus ? bottom : Math.max(...venue.floors.map((f) => floorY(venue, f.floor_id, exploded)));
    // the top storey's walls (and roof) stand about a storey over its floor
    const box = new THREE.Box3(new THREE.Vector3(x0, bottom, -y1), new THREE.Vector3(x1, top + 3.5, -y0));
    const sphere = box.getBoundingSphere(new THREE.Sphere());
    // the sphere is loose for a flat venue: tighten it so the venue fills the view; a tall stack of
    // floors fills its sphere, so it keeps the whole sphere (and its top stays in view)
    const tall = (top + 3.5 - bottom) / Math.max(x1 - x0, y1 - y0, 1);
    sphere.radius *= tall > 0.5 ? 1.0 : 0.86 + 0.28 * tall;
    void c.rotateTo(0.5, 0.9, false);
    void c.fitToSphere(sphere, true);
  }, [venue.venue_id, resetNonce, exploded, focusFloor]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const c = ref.current;
    if (!c || !flyTo) return;
    const y = floorY(venue, flyTo.floorId, exploded);
    void c.setLookAt(flyTo.x + 9, y + 13, -flyTo.y + 13, flyTo.x, y, -flyTo.y, true);
  }, [flyTo?.nonce]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const c = ref.current;
    if (!c || !shot) return;
    c.smoothTime = 1.1; // slow, cinematic move; restored when the user takes over
    void c.setLookAt(...shot.pos, ...shot.target, true).then(() => { c.smoothTime = 0.32; });
  }, [shot?.nonce]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <CameraControls ref={ref} makeDefault minDistance={4} maxDistance={maxDistance} maxPolarAngle={Math.PI * 0.48}
                    dollyToCursor smoothTime={0.32} />
  );
}
