/** Saves organizer edits as patches: every change is a new version with Undo one click away. */
import { useCallback } from "react";
import { toast } from "sonner";
import { usePatchProject, useUndo } from "@/api/queries";
import type { PatchOpIn } from "@/api/types";
import { t } from "@/i18n";

export function useVenueEdit(projectId: string) {
  const patch = usePatchProject(projectId);
  const undo = useUndo(projectId);
  const submit = useCallback((ops: PatchOpIn[], message: string, onDone?: () => void) => {
    patch.mutate({ patch: { ops }, message }, {
      onSuccess: (r) => {
        toast.success(t("check.saved", { what: message, n: r.version.version }), {
          action: { label: t("common.undo"), onClick: () => undo.mutate() },
        });
        onDone?.();
      },
      onError: (e) => toast.error(e.message, { description: (e as { hint?: string }).hint ?? undefined }),
    });
  }, [patch, undo]);
  return { submit, pending: patch.isPending };
}
