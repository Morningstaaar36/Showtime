import { useMemo } from "react";
import { useSettings } from "@/api/queries";
import { type EditorDefaults, editorDefaultsOf } from "./editorDefaults";

/** What the editors add, from the server's settings. One object per settings response, so it
 * can sit in an effect's dependencies. */
export function useEditorDefaults(): EditorDefaults {
  const eff = useSettings().data?.effective;
  return useMemo(() => editorDefaultsOf(eff ?? {}), [eff]);
}
