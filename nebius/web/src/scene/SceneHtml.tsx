/** drei <Html> mounted into one label layer owned by SceneRoot.
 *
 * drei appends each label to `events.connected` (or the canvas parent). When the canvas unmounts,
 * R3F clears `events.connected`, the target changes, and drei re-mounts every label onto a new
 * root mid-teardown; React then removes a node twice ("removeChild ... not a child of this node")
 * when leaving any 3D page. A stable portal keeps the target fixed.
 */
import { Html } from "@react-three/drei";
import { type ComponentProps, createContext, type RefObject, useContext } from "react";

export const LabelLayer = createContext<RefObject<HTMLDivElement | null> | null>(null);

export function SceneHtml(props: ComponentProps<typeof Html>) {
  const layer = useContext(LabelLayer);
  return <Html portal={layer?.current ? (layer as RefObject<HTMLElement>) : undefined} {...props} />;
}
